"""Scoped SELECT tests under actual wpl_app; owner connections only seed fixtures.

No fixture policies/grants are added by these authorization tests. Production
read policies apply. Mutation policies and HTTP authority are separate gates.
"""
import os
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext, RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.migrate import migrate
from backend.app.foundation.settings import FoundationSettings, postgres_url
from test_schema import connect, seed_org
from test_guards import add_member


class ReadRLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':
            raise RuntimeError('Refusing non-fixture RLS target.')
        cls.database=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=url))

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.teacher,self.teacher_member=add_member(owner,self.a['org'],('instructor',))
            self.student,self.student_member=add_member(owner,self.a['org'],('student',))
            self.other_student,self.other_member=add_member(owner,self.a['org'],('student',))
            self.multi,self.multi_member=add_member(owner,self.a['org'],('instructor','student'))
            self.second_cohort,self.pending_cohort=uuid4(),uuid4()
            for cohort in (self.second_cohort,self.pending_cohort):
                owner.execute("INSERT INTO wpl.cohorts(id,org_id,name,slug) VALUES (%s,%s,'Synthetic class',%s)",
                              (cohort,self.a['org'],'fixture-'+uuid4().hex))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'instructor')",
                          (self.a['org'],self.a['member']))
            for cohort,member,role in (
                (self.a['cohort'],self.teacher_member,'instructor'),
                (self.a['cohort'],self.multi_member,'instructor'),
                (self.a['cohort'],self.student_member,'student'),
                (self.second_cohort,self.a['member'],'instructor'),
                (self.second_cohort,self.other_member,'student'),
                (self.second_cohort,self.multi_member,'student'),
            ):
                owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,%s,'active')",
                              (self.a['org'],cohort,member,role))
            for fixture in (self.a,self.b):
                owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            for cohort in (self.a['cohort'],self.second_cohort):
                owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(cohort,))
            self.executive,self.pending,self.unaffiliated=uuid4(),uuid4(),uuid4()
            for user,state in ((self.executive,'active'),(self.pending,'pending'),(self.unaffiliated,'active')):
                owner.execute('INSERT INTO wpl.users(id,global_state) VALUES (%s,%s)',(user,state))
            self.pending_member=uuid4()
            owner.execute("INSERT INTO wpl.organization_memberships(id,org_id,user_id,status) VALUES (%s,%s,%s,'active')",
                          (self.pending_member,self.a['org'],self.pending))
            owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Synthetic explicit directory grant')",(self.executive,))

    def context(self,user=None,scope=RequestScope.TENANT,org=None):
        return RequestContext(VerifiedIdentity(user or self.a['user']),scope,
                              self.a['org'] if scope is RequestScope.TENANT and org is None else org)

    def ids(self,session,table,column='id'):
        # All identifiers below are fixed test literals, never request data.
        return set(session.execute(text(f'SELECT {column} FROM wpl.{table}')).scalars())

    def test_admin_reads_all_own_cohorts_and_no_other_org_rows(self):
        with self.database.request_transaction(self.context()) as session:
            self.assertEqual(self.ids(session,'organizations'),{self.a['org']})
            self.assertEqual(self.ids(session,'cohorts'),{self.a['cohort'],self.second_cohort,self.pending_cohort})
            self.assertNotIn(self.b['member'],self.ids(session,'organization_memberships'))
            self.assertNotIn(self.b['user'],self.ids(session,'users'))
            self.assertEqual(session.execute(text('SELECT current_user')).scalar_one(),'wpl_app')

    def test_instructor_sees_only_assigned_cohort_and_its_roster(self):
        with self.database.request_transaction(self.context(self.teacher)) as session:
            self.assertEqual(self.ids(session,'cohorts'),{self.a['cohort']})
            self.assertEqual(self.ids(session,'organization_memberships'),{self.teacher_member,self.multi_member,self.student_member})
            self.assertEqual(self.ids(session,'users'),{self.teacher,self.multi,self.student})
            self.assertEqual(self.ids(session,'cohort_memberships','cohort_id'),{self.a['cohort']})

    def test_student_sees_own_membership_and_assignment_only(self):
        with self.database.request_transaction(self.context(self.student)) as session:
            self.assertEqual(self.ids(session,'cohorts'),{self.a['cohort']})
            self.assertEqual(self.ids(session,'organization_memberships'),{self.student_member})
            self.assertEqual(self.ids(session,'organization_roles','membership_id'),{self.student_member})
            self.assertEqual(self.ids(session,'cohort_memberships','membership_id'),{self.student_member})
            self.assertEqual(self.ids(session,'users'),{self.student})

    def test_multiple_roles_do_not_turn_student_assignment_into_instructor_access(self):
        with self.database.request_transaction(self.context(self.multi)) as session:
            self.assertEqual(self.ids(session,'cohorts'),{self.a['cohort'],self.second_cohort})
            self.assertEqual(set(session.execute(text('SELECT membership_id FROM wpl.cohort_memberships WHERE cohort_id=:c'),
                                                {'c':self.second_cohort}).scalars()),{self.multi_member})
            self.assertNotIn(self.other_member,self.ids(session,'organization_memberships'))
            self.assertNotIn(self.other_student,self.ids(session,'users'))

    def test_unaffiliated_and_cross_org_actor_get_no_tenant_data(self):
        for user,org in ((self.unaffiliated,self.a['org']),(self.a['user'],self.b['org'])):
            with self.subTest(user=user),self.database.request_transaction(self.context(user,org=org)) as session:
                for table in ('organizations','organization_memberships','organization_roles','cohorts','cohort_memberships'):
                    self.assertEqual(session.execute(text(f'SELECT count(*) FROM wpl.{table}')).scalar_one(),0)
                self.assertEqual(self.ids(session,'users'),{user})

    def test_pending_identity_has_only_own_global_summary_without_capabilities(self):
        with self.database.request_transaction(self.context(self.pending,RequestScope.GLOBAL)) as session:
            self.assertEqual(self.ids(session,'users'),{self.pending})
            self.assertEqual(self.ids(session,'organization_memberships'),{self.pending_member})
            self.assertEqual(self.ids(session,'organizations'),{self.a['org']})
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.platform_roles')).scalar_one(),0)
        with self.database.request_transaction(self.context(self.pending)) as session:
            self.assertEqual(self.ids(session,'cohorts'),set())
            self.assertEqual(self.ids(session,'organization_memberships'),set())

    def test_explicit_executive_directory_does_not_impersonate_tenant_or_get_roster(self):
        with self.database.request_transaction(self.context(self.executive,RequestScope.PLATFORM)) as session:
            self.assertTrue({self.a['org'],self.b['org']} <= self.ids(session,'organizations'))
            self.assertEqual(self.ids(session,'organization_memberships'),set())
            self.assertEqual(self.ids(session,'cohorts'),set())
            self.assertEqual(self.ids(session,'users'),{self.executive})
        with self.database.request_transaction(self.context(self.executive)) as session:
            self.assertEqual(self.ids(session,'organizations'),set())
        with self.database.request_transaction(self.context(self.executive,RequestScope.PLATFORM,self.a['org'])) as session:
            self.assertEqual(self.ids(session,'organizations'),{self.a['org']})

    def test_recovery_requires_explicit_grant_and_target_org_and_respects_expiry(self):
        with connect() as owner:
            owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'recovery','Synthetic scoped recovery grant')",(self.executive,))
        with self.database.request_transaction(self.context(self.executive,RequestScope.PLATFORM)) as session:
            self.assertEqual(self.ids(session,'organization_memberships'),set())
        with self.database.request_transaction(self.context(self.executive,RequestScope.PLATFORM,self.a['org'])) as session:
            self.assertIn(self.a['member'],self.ids(session,'organization_memberships'))
            self.assertNotIn(self.b['member'],self.ids(session,'organization_memberships'))
            self.assertEqual(self.ids(session,'cohorts'),set())
        with connect() as owner:
            owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s",(self.executive,))
        with self.database.request_transaction(self.context(self.executive,RequestScope.PLATFORM,self.a['org'])) as session:
            self.assertEqual(self.ids(session,'organizations'),set())
            self.assertEqual(self.ids(session,'organization_memberships'),set())
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.platform_roles')).scalar_one(),0)

    def test_current_global_and_member_suspension_block_next_transaction(self):
        for kind in ('membership','global'):
            with self.subTest(kind=kind):
                # The previous subcase intentionally suspended this membership.
                # Restore it before proving access for the global-suspension case.
                if kind=='global':
                    with connect() as owner:
                        owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.teacher_member,))
                with self.database.request_transaction(self.context(self.teacher)) as session:
                    self.assertEqual(self.ids(session,'cohorts'),{self.a['cohort']})
                with connect() as owner:
                    if kind=='membership':
                        owner.execute("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(self.teacher_member,))
                    else:
                        owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.teacher,))
                with self.database.request_transaction(self.context(self.teacher)) as session:
                    self.assertEqual(self.ids(session,'cohorts'),set())
                    self.assertEqual(self.ids(session,'organization_memberships'),set())

    def test_missing_malformed_and_unknown_scope_context_fails_closed(self):
        with self.database.transaction() as session:
            self.assertEqual(self.ids(session,'organizations'),set())
            self.assertEqual(self.ids(session,'users'),set())
        for actor,scope,org in ((str(self.a['user']),'tenant','bad-org'),('bad-actor','tenant',str(self.a['org'])),
                                 (str(self.a['user']),'arbitrary-role',str(self.a['org'])),
                                 (str(self.executive),'platform','bad-org'),(str(self.a['user']),'global',str(self.a['org']))):
            with self.subTest(scope=scope),self.database.transaction() as session:
                session.execute(text("SELECT set_config('wpl.actor_id',:a,true),set_config('wpl.scope_kind',:s,true),set_config('wpl.org_id',:o,true)"),
                                {'a':actor,'s':scope,'o':org})
                self.assertEqual(self.ids(session,'organizations'),set())
                self.assertEqual(self.ids(session,'users'),set())

    def test_read_policies_grant_no_privileged_mutation_or_private_payload_access(self):
        for statement in (
            "UPDATE wpl.users SET global_state='active'",
            "INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (:actor,'users','Synthetic attempt')",
            "UPDATE wpl.organizations SET status='active'",
            'DELETE FROM wpl.organization_roles',
            'SELECT * FROM wpl.secret_payloads',
            'SELECT * FROM wpl.migration_mappings',
            'SELECT verified_email FROM wpl.users',
            'ALTER TABLE wpl.organizations DISABLE ROW LEVEL SECURITY',
            'SELECT wpl.tenant_admin(:org)',
        ):
            with self.subTest(operation=statement.split()[0]),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(self.context()) as session:
                    session.execute(text(statement),{'actor':self.a['user'],'org':self.a['org']})
            self.assertEqual(result.exception.orig.sqlstate,'42501')

    def test_own_pending_identity_insert_cannot_remap_subject_or_approve(self):
        subject=uuid4()
        context=self.context(subject,RequestScope.GLOBAL)
        with self.database.request_transaction(context) as session:
            statement=text('INSERT INTO wpl.users(id) VALUES (:id) ON CONFLICT (id) DO NOTHING')
            session.execute(statement,{'id':subject})
            session.execute(statement,{'id':subject})
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.users WHERE id=:id'),{'id':subject}).scalar_one(),1)
            self.assertEqual(session.execute(text('SELECT global_state FROM wpl.users WHERE id=:id'),{'id':subject}).scalar_one(),'pending')
        for statement,identifier in (
            ('INSERT INTO wpl.users(id) VALUES (:id) ON CONFLICT (id) DO NOTHING',uuid4()),
            ("INSERT INTO wpl.users(id,global_state) VALUES (:id,'active')",uuid4()),
            ("UPDATE wpl.users SET global_state='active' WHERE id=:id",subject),
        ):
            with self.subTest(operation=statement.split()[0]),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(context) as session:
                    session.execute(text(statement),{'id':identifier})
            self.assertEqual(result.exception.orig.sqlstate,'42501')

    def test_policy_helpers_have_minimal_execute_safe_search_path_and_no_worker_grants(self):
        entries={'read_org','read_member','read_user','read_cohort','read_assignment','read_platform_role','identity_insert_allowed'}
        with connect() as owner:
            rows=owner.execute("""SELECT p.proname,p.prosecdef,p.proconfig,
                has_function_privilege('wpl_app',p.oid,'EXECUTE'),has_function_privilege('wpl_worker',p.oid,'EXECUTE'),
                pg_get_userbyid(p.proowner)
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='wpl'""").fetchall()
            self.assertTrue(entries <= {row[0] for row in rows})
            for name,definer,config,app,worker,owner_name in rows:
                self.assertEqual(app,name in entries,name)
                self.assertFalse(worker,name)
                self.assertEqual(owner_name,'wpl_migrator')
                self.assertIn('search_path=pg_catalog, wpl',config,name)
                if name in entries: self.assertTrue(definer,name)
        print('Actual wpl_app read RLS: scoped rows; private helpers/worker authority remain denied.',flush=True)
