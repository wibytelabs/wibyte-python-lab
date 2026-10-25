"""Actual wpl_app domain writes using production policy and trusted request UOWs.

Owner connections seed/read back fixture state only, never execute the actions
under test. No fixture grants, SET ROLE, bypass headers or provider calls.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.organizations.service import set_member_status,replace_roles
from backend.app.domains.cohorts.service import set_instructors
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.migrate import migrate
from backend.app.foundation.settings import FoundationSettings,postgres_url
from test_schema import connect,seed_org
from test_guards import add_member

REASON='Synthetic runtime mutation test'


class MutationRLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':
            raise RuntimeError('Refusing non-fixture mutation target.')
        cls.database=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=url,pool_size=2))

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.admin,self.admin_member=add_member(owner,self.a['org'],('admin',))
            self.student,self.student_member=add_member(owner,self.a['org'],('student',))
            self.teacher,self.teacher_member=add_member(owner,self.a['org'],('instructor',))
            self.replacement,self.replacement_member=add_member(owner,self.a['org'],('instructor',))
            for fixture in (self.a,self.b):
                owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(self.a['org'],self.a['cohort'],self.teacher_member))
            owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(self.a['cohort'],))
        self.identity=VerifiedIdentity(self.a['user'])
        self.context=RequestContext(self.identity,RequestScope.TENANT,self.a['org'])

    def member_version(self,session,member=None):
        return session.execute(text('SELECT version FROM wpl.organization_memberships WHERE id=:id'),
                               {'id':member or self.student_member}).scalar_one()

    def cohort_version(self,session):
        return session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.a['cohort']}).scalar_one()

    def test_runtime_status_commit_rollback_epoch_and_actor_bound_audit(self):
        with self.database.request_transaction(self.context) as session:
            self.assertEqual(session.execute(text('SELECT current_user')).scalar_one(),'wpl_app')
            before=session.execute(text('SELECT access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student_member}).scalar_one()
            result=set_member_status(session,self.identity,self.a['org'],self.student_member,'suspended',self.member_version(session),REASON)
            self.assertEqual(result['status'],'suspended')
        with self.assertRaisesRegex(RuntimeError,'synthetic rollback'):
            with self.database.request_transaction(self.context) as session:
                set_member_status(session,self.identity,self.a['org'],self.student_member,'active',self.member_version(session),REASON)
                raise RuntimeError('synthetic rollback')
        with self.database.request_transaction(self.context) as session:
            row=session.execute(text('SELECT status,access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student_member}).one()
            self.assertEqual(row[0],'suspended')
            self.assertGreater(row[1],before)
            events=session.execute(text('SELECT actor_id,action FROM wpl.audit_events WHERE org_id=:org'),{'org':self.a['org']}).all()
            self.assertEqual(events,[(self.identity.subject,'membership_status_changed')])
        self.assertEqual(self.database.engine.pool.checkedout(),0)

    def test_runtime_role_change_retains_scoped_versions_and_no_platform_grant(self):
        with self.database.request_transaction(self.context) as session:
            before=self.member_version(session)
            receipt=replace_roles(session,self.identity,self.a['org'],self.student_member,['instructor','student'],before,REASON)
            self.assertEqual(receipt['roles'],['instructor','student'])
            self.assertGreater(receipt['version'],before)
        with self.database.request_transaction(self.context) as session:
            receipt=replace_roles(session,self.identity,self.a['org'],self.student_member,['student'],self.member_version(session),REASON)
            self.assertEqual(receipt['roles'],['student'])
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.audit_events WHERE org_id=:org'),{'org':self.a['org']}).scalar_one(),2)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.platform_roles WHERE user_id=%s',(self.student,)).fetchone()[0],0)

    def test_runtime_instructor_replacement_upsert_retains_removed_history(self):
        with self.database.request_transaction(self.context) as session:
            set_instructors(session,self.identity,self.a['org'],self.a['cohort'],[self.replacement_member],self.cohort_version(session),REASON)
        with self.database.request_transaction(self.context) as session:
            rows=session.execute(text("SELECT membership_id,status FROM wpl.cohort_memberships WHERE cohort_id=:cohort AND role='instructor'"),{'cohort':self.a['cohort']}).all()
            self.assertEqual(set(rows),{(self.teacher_member,'removed'),(self.replacement_member,'active')})
            set_instructors(session,self.identity,self.a['org'],self.a['cohort'],[self.teacher_member],self.cohort_version(session),REASON)
        with self.database.request_transaction(self.context) as session:
            self.assertEqual(session.execute(text("SELECT status FROM wpl.cohort_memberships WHERE cohort_id=:c AND membership_id=:m AND role='instructor'"),{'c':self.a['cohort'],'m':self.teacher_member}).scalar_one(),'active')

    def test_service_actor_org_context_mismatch_and_nonadmins_fail_without_side_effect(self):
        cases=(
            (RequestContext(VerifiedIdentity(self.student),RequestScope.TENANT,self.a['org']),VerifiedIdentity(self.student),self.a['org']),
            (RequestContext(VerifiedIdentity(self.teacher),RequestScope.TENANT,self.a['org']),VerifiedIdentity(self.teacher),self.a['org']),
            (self.context,VerifiedIdentity(self.admin),self.a['org']),
            (self.context,self.identity,self.b['org']),
            (RequestContext(self.identity,RequestScope.GLOBAL),self.identity,self.a['org']),
        )
        for context,identity,org in cases:
            with self.subTest(scope=context.scope),self.assertRaises(AuthorizationDenied):
                with self.database.request_transaction(context) as session:
                    set_member_status(session,identity,org,self.student_member,'suspended',1,REASON)
        with self.assertRaises(AuthorizationDenied):
            with self.database.transaction() as session:
                set_member_status(session,self.identity,self.a['org'],self.student_member,'suspended',1,REASON)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.student_member,)).fetchone()[0],'active')
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_actual_runtime_primary_and_final_instructor_guards_reject_direct_writes(self):
        statements=(
            ("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=:id",self.a['member']),
            ("DELETE FROM wpl.organization_roles WHERE membership_id=:id AND role='admin'",self.a['member']),
            ("UPDATE wpl.cohort_memberships SET status='removed' WHERE membership_id=:id AND role='instructor'",self.teacher_member),
        )
        for statement,identifier in statements:
            with self.subTest(operation=statement.split()[0]),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(self.context) as session:
                    session.execute(text(statement),{'id':identifier})
            self.assertEqual(result.exception.orig.sqlstate,'23514')
        with self.assertRaises(TenantConflict) as result:
            with self.database.request_transaction(self.context) as session:
                set_member_status(session,self.identity,self.a['org'],self.teacher_member,'removed',self.member_version(session,self.teacher_member),REASON)
        self.assertEqual(result.exception.code,'last_instructor')

    def test_direct_cross_org_update_insert_and_privileged_columns_are_denied(self):
        with self.database.request_transaction(self.context) as session:
            result=session.execute(text("UPDATE wpl.organizations SET name='Synthetic own metadata' WHERE id=:id"),{'id':self.a['org']})
            self.assertEqual(result.rowcount,1)
            result=session.execute(text("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=:id"),{'id':self.b['member']})
            self.assertEqual(result.rowcount,0)
        for statement,params in (
            ("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (:org,:member,'student')",{'org':self.b['org'],'member':self.b['member']}),
            ('UPDATE wpl.organization_memberships SET user_id=:user WHERE id=:member',{'user':uuid4(),'member':self.student_member}),
            ('UPDATE wpl.organizations SET primary_admin_membership_id=:member WHERE id=:org',{'member':self.admin_member,'org':self.a['org']}),
            ("UPDATE wpl.users SET global_state='active' WHERE id=:user",{'user':self.student}),
            ('DELETE FROM wpl.audit_events',{}),
            ('SELECT * FROM wpl.secret_payloads',{}),
        ):
            with self.subTest(operation=statement.split()[0]),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(self.context) as session:
                    session.execute(text(statement),params)
            self.assertEqual(result.exception.orig.sqlstate,'42501')

    def test_nonadmin_direct_writes_and_forged_audit_actor_are_denied(self):
        context=RequestContext(VerifiedIdentity(self.student),RequestScope.TENANT,self.a['org'])
        with self.database.request_transaction(context) as session:
            self.assertEqual(session.execute(text("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=:m"),{'m':self.student_member}).rowcount,0)
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(context) as session:
                session.execute(text("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (:org,:member,'admin')"),{'org':self.a['org'],'member':self.student_member})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(self.context) as session:
                session.execute(text("""INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id)
                    VALUES (:id,:actor,:org,'membership_status_changed',:reason,'membership',:target)"""),
                    {'id':uuid4(),'actor':self.admin,'org':self.a['org'],'reason':REASON,'target':self.student_member})
        self.assertEqual(result.exception.orig.sqlstate,'42501')

    def test_self_admin_authority_loss_fails_closed_without_partial_changes(self):
        identity=VerifiedIdentity(self.admin)
        context=RequestContext(identity,RequestScope.TENANT,self.a['org'])
        for operation in ('roles','status'):
            with self.subTest(operation=operation),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(context) as session:
                    version=self.member_version(session,self.admin_member)
                    if operation=='roles':
                        replace_roles(session,identity,self.a['org'],self.admin_member,['student'],version,REASON)
                    else:
                        set_member_status(session,identity,self.a['org'],self.admin_member,'suspended',version,REASON)
            self.assertEqual(result.exception.orig.sqlstate,'42501')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.admin_member,)).fetchone()[0],'active')
            self.assertEqual(owner.execute('SELECT role FROM wpl.organization_roles WHERE membership_id=%s',(self.admin_member,)).fetchall(),[('admin',)])
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_audit_failure_rolls_back_prior_business_change(self):
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(self.context) as session:
                session.execute(text("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=:id"),{'id':self.student_member})
                session.execute(text("""INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id)
                    VALUES (:id,:actor,:org,'unsupported_action',:reason,'membership',:target)"""),
                    {'id':uuid4(),'actor':self.identity.subject,'org':self.a['org'],'reason':REASON,'target':self.student_member})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.student_member,)).fetchone()[0],'active')
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_two_actual_app_admins_serialize_and_recheck_expected_member_version(self):
        with self.database.request_transaction(self.context) as session:
            version=self.member_version(session)
        barrier=threading.Barrier(2)
        def operation(actor,status):
            identity=VerifiedIdentity(actor)
            barrier.wait(timeout=5)
            try:
                with self.database.request_transaction(RequestContext(identity,RequestScope.TENANT,self.a['org'])) as session:
                    set_member_status(session,identity,self.a['org'],self.student_member,status,version,REASON)
                return 'applied'
            except TenantConflict as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            first=executor.submit(operation,self.identity.subject,'suspended')
            second=executor.submit(operation,self.admin,'removed')
            outcomes=[first.result(timeout=15),second.result(timeout=15)]
        self.assertCountEqual(outcomes,['applied','version_conflict'])
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(self.a['org'],)).fetchone()[0],1)
        print('Actual wpl_app administrators: one committed mutation and one version conflict.',flush=True)
