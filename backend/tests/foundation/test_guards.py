"""Actual database invariants/races. Policy/API authority is a later P02 gate."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import unittest
from uuid import uuid4
import psycopg
from psycopg import IsolationLevel
from test_schema import connect, seed_org


def add_member(connection, org_id, roles=('admin',)):
    user, member = uuid4(), uuid4()
    connection.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')", (user,))
    connection.execute("INSERT INTO wpl.organization_memberships(id,org_id,user_id,status) VALUES (%s,%s,%s,'active')", (member,org_id,user))
    for role in roles:
        connection.execute('INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,%s)', (org_id,member,role))
    return user, member


def concurrent(operations, isolation=IsolationLevel.READ_COMMITTED):
    barrier = threading.Barrier(len(operations))
    def run(operation):
        with connect() as connection:
            connection.isolation_level = isolation
            connection.execute("SET LOCAL lock_timeout='3s'")
            connection.execute("SET LOCAL statement_timeout='5s'")
            barrier.wait(timeout=5)
            try:
                result = operation(connection)
                connection.commit()
                return result
            except (psycopg.errors.CheckViolation, psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
                connection.rollback()
                return 'blocked'
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(run,operations))


class GuardTests(unittest.TestCase):
    def test_primary_ordinary_removal_demotion_and_suspension_are_rejected(self):
        with connect() as owner:
            fixture = seed_org(owner)
            operations = [
                ("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(fixture['member'],),psycopg.errors.CheckViolation),
                ("UPDATE wpl.organization_memberships SET status='removed' WHERE id=%s",(fixture['member'],),psycopg.errors.CheckViolation),
                ("DELETE FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s AND role='admin'",(fixture['org'],fixture['member']),psycopg.errors.CheckViolation),
                ('DELETE FROM wpl.organization_memberships WHERE id=%s',(fixture['member'],),psycopg.errors.ForeignKeyViolation),
            ]
            for statement, params, error in operations:
                with self.subTest(operation=statement.split('(')[0]), self.assertRaises(error):
                    with owner.transaction():
                        owner.execute(statement,params)
                        owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            owner.rollback()

    def test_pending_invitation_cannot_be_activated_without_verified_binding(self):
        with connect() as owner:
            organization, member, invitation, user = (uuid4() for _ in range(4))
            owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(user,))
            owner.execute("""INSERT INTO wpl.organizations(id,name,organization_type,contact_email,home_region,
                primary_admin_membership_id,provisioning_identity) VALUES (%s,'Guard fixture','other',
                'contact@example.invalid','fixture',%s,%s)""", (organization,member,str(uuid4())))
            owner.execute("INSERT INTO wpl.organization_memberships(id,org_id,status,invitation_id) VALUES (%s,%s,'invite_pending',%s)", (member,organization,invitation))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'admin')",(organization,member))
            owner.execute("""INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,token_hash,expires_at)
                VALUES (%s,%s,%s,'primary@example.invalid',ARRAY['admin'],%s,now()+interval '1 day')""",
                (invitation,organization,member,hashlib.sha256(uuid4().bytes).digest()))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            with self.assertRaises(psycopg.errors.CheckViolation):
                with owner.transaction():
                    owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(organization,))
            with self.assertRaises(psycopg.errors.CheckViolation):
                with owner.transaction():
                    owner.execute("UPDATE wpl.organization_memberships SET status='active',user_id=%s WHERE id=%s",(user,member))
            owner.execute('SET CONSTRAINTS ALL DEFERRED')
            owner.execute("UPDATE wpl.invitations SET status='accepted',accepted_user_id=%s,accepted_at=now() WHERE id=%s",(user,invitation))
            owner.execute("UPDATE wpl.organization_memberships SET status='active',user_id=%s WHERE id=%s",(user,member))
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(organization,))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            self.assertEqual(owner.execute('SELECT status FROM wpl.organizations WHERE id=%s',(organization,)).fetchone()[0],'active')
            owner.rollback()

    def test_primary_transfer_requires_eligible_target_and_retains_old_admin(self):
        with connect() as owner:
            fixture = seed_org(owner)
            _, target = add_member(owner,fixture['org'])
            _, student = add_member(owner,fixture['org'],('student',))
            with self.assertRaises(psycopg.errors.CheckViolation):
                with owner.transaction():
                    owner.execute('UPDATE wpl.organizations SET primary_admin_membership_id=%s WHERE id=%s',(student,fixture['org']))
                    owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            owner.execute('UPDATE wpl.organizations SET primary_admin_membership_id=%s WHERE id=%s',(target,fixture['org']))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            self.assertEqual(owner.execute("SELECT role FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s",(fixture['org'],fixture['member'])).fetchone()[0],'admin')
            owner.rollback()

    def test_expected_version_fences_two_competing_transfers(self):
        with connect() as owner:
            fixture = seed_org(owner)
            targets = [add_member(owner,fixture['org'])[1] for _ in range(2)]
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            version = owner.execute('SELECT version FROM wpl.organizations WHERE id=%s',(fixture['org'],)).fetchone()[0]
        def operation(target):
            def apply(connection):
                result=connection.execute('UPDATE wpl.organizations SET primary_admin_membership_id=%s WHERE id=%s AND version=%s RETURNING id',(target,fixture['org'],version)).fetchone()
                return 'applied' if result else 'version_conflict'
            return apply
        outcomes = concurrent([operation(target) for target in targets])
        self.assertCountEqual(outcomes,['applied','version_conflict'])
        with connect() as owner:
            self.assertIn(owner.execute('SELECT primary_admin_membership_id FROM wpl.organizations WHERE id=%s',(fixture['org'],)).fetchone()[0],targets)
        print('Actual competing transfers:',outcomes,flush=True)

    def test_concurrent_target_removal_and_transfer_leave_valid_primary(self):
        with connect() as owner:
            fixture = seed_org(owner)
            _, target = add_member(owner,fixture['org'])
            version = owner.execute('SELECT version FROM wpl.organizations WHERE id=%s',(fixture['org'],)).fetchone()[0]
        def transfer(connection):
            row=connection.execute('UPDATE wpl.organizations SET primary_admin_membership_id=%s WHERE id=%s AND version=%s RETURNING id',(target,fixture['org'],version)).fetchone()
            return 'transferred' if row else 'version_conflict'
        def remove(connection):
            connection.execute("UPDATE wpl.organization_memberships SET status='removed' WHERE id=%s",(target,))
            return 'removed'
        outcomes=concurrent([transfer,remove])
        self.assertIn(outcomes,[['transferred','blocked'],['version_conflict','removed']])
        with connect() as owner:
            state=owner.execute("""SELECT m.status FROM wpl.organizations o JOIN wpl.organization_memberships m
                ON m.org_id=o.id AND m.id=o.primary_admin_membership_id WHERE o.id=%s""",(fixture['org'],)).fetchone()[0]
            self.assertEqual(state,'active')
        print('Actual transfer/removal race:',outcomes,flush=True)

    def test_final_instructor_membership_and_role_changes_are_rejected(self):
        with connect() as owner:
            fixture=seed_org(owner)
            _, teacher=add_member(owner,fixture['org'],('instructor',))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(fixture['org'],fixture['cohort'],teacher))
            owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(fixture['cohort'],))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for statement,params in [
                ("DELETE FROM wpl.cohort_memberships WHERE org_id=%s AND membership_id=%s",(fixture['org'],teacher)),
                ("DELETE FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s AND role='instructor'",(fixture['org'],teacher)),
                ("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(teacher,)),
            ]:
                with self.subTest(operation=statement.split('(')[0]), self.assertRaises(psycopg.errors.CheckViolation):
                    with owner.transaction():
                        owner.execute(statement,params)
            owner.rollback()

    def test_final_instructor_race_read_committed_and_repeatable_read(self):
        for isolation in (IsolationLevel.READ_COMMITTED,IsolationLevel.REPEATABLE_READ):
            with self.subTest(isolation=isolation):
                with connect() as owner:
                    fixture=seed_org(owner)
                    teachers=[add_member(owner,fixture['org'],('instructor',))[1] for _ in range(2)]
                    for teacher in teachers:
                        owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(fixture['org'],fixture['cohort'],teacher))
                    owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(fixture['cohort'],))
                def remove(teacher):
                    def apply(connection):
                        connection.execute('DELETE FROM wpl.cohort_memberships WHERE org_id=%s AND cohort_id=%s AND membership_id=%s',(fixture['org'],fixture['cohort'],teacher))
                        return 'removed'
                    return apply
                outcomes=concurrent([remove(teacher) for teacher in teachers],isolation)
                self.assertCountEqual(outcomes,['removed','blocked'])
                with connect() as owner:
                    self.assertEqual(owner.execute("SELECT count(*) FROM wpl.cohort_memberships WHERE org_id=%s AND cohort_id=%s AND role='instructor' AND status='active'",(fixture['org'],fixture['cohort'])).fetchone()[0],1)
                print('Actual final-instructor race:',isolation.name,outcomes,flush=True)

    def test_global_suspension_advances_epochs_and_enters_audited_recovery(self):
        with connect() as owner:
            fixture=seed_org(owner)
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'instructor')",(fixture['org'],fixture['member']))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(fixture['org'],fixture['cohort'],fixture['member']))
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(fixture['cohort'],))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            # Validate final state after the user mutation, not its intermediate trigger work.
            owner.execute('SET CONSTRAINTS ALL DEFERRED')
            old=owner.execute('SELECT access_epoch FROM wpl.users WHERE id=%s',(fixture['user'],)).fetchone()[0]
            owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(fixture['user'],))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            self.assertEqual(owner.execute('SELECT access_epoch FROM wpl.users WHERE id=%s',(fixture['user'],)).fetchone()[0],old+1)
            for table,identifier in (('organizations',fixture['org']),('cohorts',fixture['cohort'])):
                self.assertEqual(owner.execute(f'SELECT status FROM wpl.{table} WHERE id=%s',(identifier,)).fetchone()[0],'recovery_required')
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='global_security_recovery'",(fixture['org'],)).fetchone()[0],2)
            owner.rollback()

    def test_guard_functions_are_private_and_security_definers_have_safe_search_path(self):
        with connect() as owner:
            rows=owner.execute("""SELECT p.proname,p.prosecdef,p.proconfig,
                has_function_privilege('wpl_app',p.oid,'EXECUTE'),has_function_privilege('wpl_worker',p.oid,'EXECUTE')
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='wpl'""").fetchall()
            self.assertTrue(rows)
            for name,definer,config,app,worker in rows:
                self.assertFalse(app,name)
                self.assertFalse(worker,name)
                self.assertIn('search_path=pg_catalog, wpl',config,name)
            self.assertTrue(any(row[1] for row in rows))
            fixture=seed_org(owner)
            other=uuid4()
            owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(other,))
            with self.assertRaises(psycopg.errors.CheckViolation):
                with owner.transaction():
                    owner.execute('UPDATE wpl.organization_memberships SET user_id=%s WHERE id=%s',(other,fixture['member']))
            owner.rollback()
