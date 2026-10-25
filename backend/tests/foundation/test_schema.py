"""P02.2 schema slice: actual FK/check/uniqueness/default-denial evidence."""
import hashlib
import os
import unittest
from uuid import uuid4
import psycopg
from psycopg import sql
from backend.app.foundation.migrate import migrate
from backend.app.foundation.settings import postgres_url


def connect(kind='MIGRATION'):
    url = postgres_url(os.environ[f'WPL_{kind}_DATABASE_URL'], 'fixture')
    if url.host != 'fixture-db' or url.database != 'wpl_fixture':
        raise RuntimeError('Refusing non-fixture database target.')
    return psycopg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False))


def seed_org(connection):
    ids = {key: uuid4() for key in ('org', 'member', 'user', 'cohort')}
    connection.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')", (ids['user'],))
    connection.execute("""INSERT INTO wpl.organizations(id,name,organization_type,contact_email,
        home_region,primary_admin_membership_id,provisioning_identity)
        VALUES (%s,'Synthetic school','school','contact@example.invalid','fixture',%s,%s)""",
        (ids['org'], ids['member'], str(uuid4())))
    connection.execute("""INSERT INTO wpl.organization_memberships(id,org_id,user_id,status)
        VALUES (%s,%s,%s,'active')""", (ids['member'], ids['org'], ids['user']))
    connection.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'admin')", (ids['org'], ids['member']))
    connection.execute("INSERT INTO wpl.cohorts(id,org_id,name,slug) VALUES (%s,%s,'Fixture cohort',%s)",
                       (ids['cohort'], ids['org'], 'fixture-' + uuid4().hex))
    return ids


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])

    def test_private_tables_have_rls_and_runtime_gets_no_implicit_access(self):
        with connect() as owner:
            rows = owner.execute("""SELECT c.relname,c.relrowsecurity FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='wpl' AND c.relkind='r' AND c.relname<>'alembic_version'""").fetchall()
            self.assertTrue(rows)
            self.assertTrue(all(row[1] for row in rows))
        for kind in ('APPLICATION', 'WORKER'):
            with connect(kind) as runtime:
                for name, _ in rows:
                    with self.subTest(role=kind, table=name):
                        try:
                            visible = runtime.execute(sql.SQL('SELECT * FROM wpl.{}').format(sql.Identifier(name))).fetchall()
                        except psycopg.errors.InsufficientPrivilege:
                            runtime.rollback()
                        else:
                            self.assertEqual(visible, [], 'Unbound runtime must see no private rows')

    def test_pending_primary_circular_binding_and_single_designation(self):
        with connect() as owner:
            organization, member, invitation = uuid4(), uuid4(), uuid4()
            owner.execute("""INSERT INTO wpl.organizations(id,name,organization_type,contact_email,home_region,
                primary_admin_membership_id,provisioning_identity) VALUES (%s,'Pending fixture','other',
                'contact@example.invalid','fixture',%s,%s)""", (organization, member, str(uuid4())))
            owner.execute("""INSERT INTO wpl.organization_memberships(id,org_id,invitation_id,status)
                VALUES (%s,%s,%s,'invite_pending')""", (member, organization, invitation))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'admin')", (organization, member))
            owner.execute("""INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,
                token_hash,expires_at) VALUES (%s,%s,%s,'primary@example.invalid',ARRAY['admin'],%s,now()+interval '1 day')""",
                (invitation, organization, member, hashlib.sha256(uuid4().bytes).digest()))
            owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            self.assertEqual(owner.execute("SELECT user_id,status FROM wpl.organization_memberships WHERE id=%s", (member,)).fetchone(), (None,'invite_pending'))
            with self.assertRaises(psycopg.errors.NotNullViolation):
                with owner.transaction():
                    owner.execute('UPDATE wpl.organizations SET primary_admin_membership_id=NULL WHERE id=%s', (organization,))
            owner.rollback()

    def test_actual_runtime_composite_fks_reject_cross_org_children(self):
        # Role/assignment writes now use actual production tenant policies. Only
        # transfer/invitation tables retain temporary constraint-only fixture grants;
        # their production mutation workflows are still a later checkpoint.
        tables = ('primary_admin_transfers','invitations')
        with connect() as owner:
            # Preserve the production read grants across this constraint-only fixture.
            prior_select = {name: owner.execute(
                "SELECT has_table_privilege('wpl_app',%s,'SELECT')", ('wpl.'+name,)).fetchone()[0]
                for name in tables}
            first, second = seed_org(owner), seed_org(owner)
            for fixture in (first,second):
                owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            for name in tables:
                owner.execute(sql.SQL('GRANT SELECT,INSERT ON wpl.{} TO wpl_app').format(sql.Identifier(name)))
                owner.execute(sql.SQL('CREATE POLICY p022_constraint_fixture ON wpl.{} TO wpl_app '
                    'USING (org_id IN ({},{})) WITH CHECK (org_id IN ({},{}))').format(sql.Identifier(name),
                    sql.Literal(first['org']),sql.Literal(second['org']),sql.Literal(first['org']),sql.Literal(second['org'])))
        from backend.app.domains.authorization.context import RequestContext,RequestScope
        from backend.app.domains.identity.types import VerifiedIdentity
        context=RequestContext(VerifiedIdentity(first['user']),RequestScope.TENANT,first['org'])
        def bind(runtime):
            runtime.execute("SELECT set_config('wpl.actor_id',%s,true),set_config('wpl.scope_kind',%s,true),set_config('wpl.org_id',%s,true),set_config('wpl.auth_time','',true)",
                            (str(context.identity.subject),context.scope.value,str(context.org_id)))
        try:
            with connect('APPLICATION') as runtime:
                bind(runtime)
                self.assertEqual(runtime.execute('SELECT current_user').fetchone()[0], 'wpl_app')
                runtime.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'instructor')", (first['org'],first['member']))
                runtime.commit()
                cases = [
                    ("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'student')", (first['org'],second['member'])),
                    ("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'student','active')", (first['org'],second['cohort'],first['member'])),
                    ("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'student','active')", (first['org'],first['cohort'],second['member'])),
                    ("""INSERT INTO wpl.primary_admin_transfers(id,org_id,actor_id,from_membership_id,to_membership_id,
                        expected_version,confirmation_hash,status,expires_at) VALUES (%s,%s,%s,%s,%s,1,%s,'preview',now()+interval '5 minutes')""",
                     (uuid4(),first['org'],first['user'],first['member'],second['member'],hashlib.sha256(b'fixture').digest())),
                    ("""INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,token_hash,expires_at)
                        VALUES (%s,%s,%s,'fixture@example.invalid',ARRAY['student'],%s,now()+interval '1 day')""",
                     (uuid4(),first['org'],second['member'],hashlib.sha256(uuid4().bytes).digest())),
                ]
                for statement, params in cases:
                    with self.subTest(operation=statement.split('(')[0]):
                        bind(runtime)
                        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                            runtime.execute(statement,params)
                            runtime.execute('SET CONSTRAINTS ALL IMMEDIATE')
                        runtime.rollback()
                print('Actual wpl_app: positive same-org insert; five cross-org child writes rejected by FKs.', flush=True)
        finally:
            with connect() as owner:
                for name in tables:
                    owner.execute(sql.SQL('DROP POLICY p022_constraint_fixture ON wpl.{}').format(sql.Identifier(name)))
                    owner.execute(sql.SQL('REVOKE ALL ON wpl.{} FROM wpl_app').format(sql.Identifier(name)))
                    if prior_select[name]:
                        owner.execute(sql.SQL('GRANT SELECT ON wpl.{} TO wpl_app').format(sql.Identifier(name)))

    def test_primary_reference_and_membership_placeholder_checks(self):
        with connect() as owner:
            first, second = seed_org(owner), seed_org(owner)
            cases = [
                ('UPDATE wpl.organizations SET primary_admin_membership_id=%s WHERE id=%s', (second['member'],first['org']), psycopg.errors.ForeignKeyViolation),
                ("INSERT INTO wpl.organization_memberships(id,org_id,status) VALUES (%s,%s,'active')", (uuid4(),first['org']), psycopg.errors.CheckViolation),
                ("INSERT INTO wpl.organization_memberships(id,org_id,status) VALUES (%s,%s,'invite_pending')", (uuid4(),first['org']), psycopg.errors.CheckViolation),
            ]
            for statement, params, error in cases:
                with self.subTest(operation=statement.split('(')[0]), self.assertRaises(error):
                    with owner.transaction():
                        owner.execute(statement,params)
                        owner.execute('SET CONSTRAINTS ALL IMMEDIATE')
            owner.rollback()

    def test_payload_outbox_scopes_and_dedup_are_constrained(self):
        with connect() as owner:
            first, second = seed_org(owner), seed_org(owner)
            payload, job = uuid4(), uuid4()
            # Placeholder bytes prove only schema shape, not cryptographic encryption.
            owner.execute("""INSERT INTO wpl.secret_payloads(id,scope_kind,scope_id,org_id,key_reference,ciphertext)
                VALUES (%s,'tenant',%s,%s,'synthetic-key-reference',%s)""", (payload,first['org'],first['org'],b'ciphertext-fixture-32-bytes-only!!'))
            insert = """INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key,private_payload_id)
                VALUES (%s,'tenant',%s,%s,%s,'deliver_invitation','fixture-dedup',%s)"""
            owner.execute(insert,(job,first['org'],first['org'],first['user'],payload))
            cases = [
                (insert,(uuid4(),second['org'],second['org'],second['user'],payload),psycopg.errors.ForeignKeyViolation),
                (insert,(uuid4(),first['org'],first['org'],first['user'],payload),psycopg.errors.UniqueViolation),
                ("INSERT INTO wpl.outbox(id,scope_kind,scope_id,job_id,event_kind,dedup_key) VALUES (%s,'tenant',%s,%s,'invite_queued','fixture')", (uuid4(),second['org'],job),psycopg.errors.ForeignKeyViolation),
                ("UPDATE wpl.jobs SET state='running' WHERE id=%s", (job,),psycopg.errors.CheckViolation),
                ("UPDATE wpl.jobs SET lease_owner=%s WHERE id=%s", (uuid4(),job),psycopg.errors.CheckViolation),
            ]
            for statement, params, error in cases:
                with self.subTest(operation=statement.split('(')[0]), self.assertRaises(error):
                    with owner.transaction():
                        owner.execute(statement,params)
            owner.rollback()

    def test_audit_is_append_only_and_identity_has_no_implicit_grants(self):
        with connect() as owner:
            fixture, event = seed_org(owner), uuid4()
            owner.execute("""INSERT INTO wpl.audit_events(id,actor_id,org_id,action,target_type,target_id)
                VALUES (%s,%s,%s,'fixture_created','organization',%s)""", (event,fixture['user'],fixture['org'],fixture['org']))
            for statement in ("UPDATE wpl.audit_events SET reason='changed' WHERE id=%s", 'DELETE FROM wpl.audit_events WHERE id=%s'):
                with self.subTest(operation=statement[:6]), self.assertRaises(psycopg.errors.CheckViolation):
                    with owner.transaction():
                        owner.execute(statement,(event,))
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.platform_roles WHERE user_id=%s',(fixture['user'],)).fetchone()[0],0)
            owner.rollback()
