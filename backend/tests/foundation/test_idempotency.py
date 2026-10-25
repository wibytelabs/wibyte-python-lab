"""Actual runtime-role idempotency, business writes, audit and concurrency."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.jobs.idempotency import execute_idempotent,MutationResult,TenantOperation,InvalidIdempotencyInput
from backend.app.domains.organizations.service import set_member_status,replace_roles
from backend.app.domains.cohorts.service import set_instructors
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.migrate import migrate
from backend.app.foundation.settings import FoundationSettings,postgres_url
from test_schema import connect,seed_org
from test_guards import add_member

REASON='Synthetic idempotent mutation'
COLUMNS='actor_id,operation,scope_kind,scope_id,org_id,request_key,request_hash,response_status,response'


class IdempotencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture idempotency target.')
        cls.settings=FoundationSettings(enabled=True,application_database_url=url,pool_size=2)
        cls.database=FoundationDatabase(cls.settings)

    @classmethod
    def tearDownClass(cls):cls.database.close()

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.student,self.member=add_member(owner,self.a['org'],('student',))
            self.other_student,self.other_member=add_member(owner,self.a['org'],('student',))
            self.second_actor,self.second_actor_member=add_member(owner,self.a['org'],('admin',))
            self.b_student,self.b_member=add_member(owner,self.b['org'],('student',))
            bridge=uuid4()
            owner.execute("INSERT INTO wpl.organization_memberships(id,org_id,user_id,status) VALUES (%s,%s,%s,'active')",(bridge,self.b['org'],self.a['user']))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'admin')",(self.b['org'],bridge))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'instructor')",(self.a['org'],self.a['member']))
            for fixture in (self.a,self.b):owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            self.version=owner.execute('SELECT version FROM wpl.organization_memberships WHERE id=%s',(self.member,)).fetchone()[0]
            self.other_version=owner.execute('SELECT version FROM wpl.organization_memberships WHERE id=%s',(self.other_member,)).fetchone()[0]
            self.b_version=owner.execute('SELECT version FROM wpl.organization_memberships WHERE id=%s',(self.b_member,)).fetchone()[0]
        self.context=RequestContext(VerifiedIdentity(self.a['user']),RequestScope.TENANT,self.a['org'])
        self.body={'member_id':str(self.member),'status':'suspended','version':self.version,'reason':REASON}

    def mutation(self,context,body):
        def callback(session):
            from uuid import UUID
            result=set_member_status(session,context.identity,context.org_id,UUID(body['member_id']),body['status'],body['version'],body['reason'])
            return MutationResult(200,{'membership_id':str(result['id']),'status':result['status'],'version':result['version']})
        return callback

    def run_request(self,key='fixture-request',*,context=None,body=None,callback=None,database=None):
        context=context or self.context;body=self.body if body is None else body
        callback=callback or self.mutation(context,body)
        with (database or self.database).request_transaction(context) as session:
            return execute_idempotent(session,context,TenantOperation.MEMBER_STATUS,key,body,callback)

    def counts(self):
        with connect() as owner:
            records=owner.execute('SELECT count(*) FROM wpl.idempotency_records WHERE org_id=%s',(self.a['org'],)).fetchone()[0]
            audit=owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(self.a['org'],)).fetchone()[0]
            state=owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.member,)).fetchone()[0]
        return records,audit,state

    def test_same_body_replay_survives_new_pool_and_does_not_repeat_business_action(self):
        first=self.run_request()
        self.assertFalse(first.replayed)
        other=FoundationDatabase(self.settings)
        self.addCleanup(other.close)
        def forbidden_callback(session):raise AssertionError('Cached result executed its callback')
        again=self.run_request(database=other,callback=forbidden_callback,body=dict(reversed(list(self.body.items()))))
        self.assertTrue(again.replayed)
        self.assertEqual(again.result,first.result)
        self.assertEqual(self.counts(),(1,1,'suspended'))

    def test_concurrent_same_key_and_body_commit_one_action_and_return_same_result(self):
        barrier=threading.Barrier(2)
        def run():
            barrier.wait(timeout=5)
            return self.run_request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run) for _ in range(2)]
            outcomes=[future.result(timeout=15) for future in futures]
        self.assertCountEqual([outcome.replayed for outcome in outcomes],[False,True])
        self.assertEqual(outcomes[0].result,outcomes[1].result)
        self.assertEqual(self.counts(),(1,1,'suspended'))
        print('Actual concurrent wpl_app same-key requests: one mutation/audit/receipt; same result replayed.',flush=True)

    def test_changed_body_conflicts_without_second_mutation(self):
        self.run_request()
        changed={**self.body,'reason':'Synthetic different body'}
        with self.assertRaises(TenantConflict) as result:self.run_request(body=changed)
        self.assertEqual(result.exception.code,'idempotency_conflict')
        self.assertEqual(self.counts(),(1,1,'suspended'))

    def test_actor_and_org_are_separate_key_namespaces(self):
        self.run_request()
        other_context=RequestContext(VerifiedIdentity(self.second_actor),RequestScope.TENANT,self.a['org'])
        other_body={**self.body,'member_id':str(self.other_member),'version':self.other_version}
        self.assertFalse(self.run_request(context=other_context,body=other_body).replayed)
        b_context=RequestContext(self.context.identity,RequestScope.TENANT,self.b['org'])
        b_body={**self.body,'member_id':str(self.b_member),'version':self.b_version}
        self.assertFalse(self.run_request(context=b_context,body=b_body).replayed)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.idempotency_records WHERE request_key=%s AND actor_id IN (%s,%s)',
                ('fixture-request',self.context.identity.subject,self.second_actor)).fetchone()[0],3)
        with self.database.request_transaction(other_context) as session:
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.idempotency_records WHERE actor_id=:other'),{'other':self.context.identity.subject}).scalar_one(),0)

    def test_operation_namespace_and_all_current_receipt_shapes(self):
        self.run_request()
        with self.database.request_transaction(self.context) as session:
            version=session.execute(text('SELECT version FROM wpl.organization_memberships WHERE id=:id'),{'id':self.member}).scalar_one()
            def roles_callback(s):
                result=replace_roles(s,self.context.identity,self.a['org'],self.member,['student','instructor'],version,REASON)
                return MutationResult(200,{'membership_id':str(result['membership_id']),'roles':result['roles'],'version':result['version']})
            result=execute_idempotent(session,self.context,TenantOperation.MEMBER_ROLES,'fixture-request',{'member_id':str(self.member),'roles':['student','instructor'],'version':version},roles_callback)
            self.assertFalse(result.replayed)
        with self.database.request_transaction(self.context) as session:
            version=session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.a['cohort']}).scalar_one()
            def instructors_callback(s):
                result=set_instructors(s,self.context.identity,self.a['org'],self.a['cohort'],[self.a['member']],version,REASON)
                return MutationResult(200,{'cohort_id':str(result['id']),'version':result['version']})
            result=execute_idempotent(session,self.context,TenantOperation.COHORT_INSTRUCTORS,'fixture-request',{'cohort_id':str(self.a['cohort']),'version':version},instructors_callback)
            self.assertFalse(result.replayed)
        self.assertEqual(self.counts()[:2],(3,3))

    def test_outer_rollback_discards_receipt_business_and_audit(self):
        with self.assertRaisesRegex(RuntimeError,'synthetic outer rollback'):
            with self.database.request_transaction(self.context) as session:
                execute_idempotent(session,self.context,TenantOperation.MEMBER_STATUS,'fixture-request',self.body,self.mutation(self.context,self.body))
                raise RuntimeError('synthetic outer rollback')
        self.assertEqual(self.counts(),(0,0,'active'))
        self.assertFalse(self.run_request().replayed)
        self.assertEqual(self.counts(),(1,1,'suspended'))

    def test_invalid_secret_receipt_rolls_back_savepoint_even_when_caller_catches(self):
        with self.database.request_transaction(self.context) as session:
            def unsafe_callback(s):
                result=self.mutation(self.context,self.body)(s)
                return MutationResult(200,{**result.body,'activation_token':'synthetic-private-marker'})
            with self.assertRaises(InvalidIdempotencyInput):
                execute_idempotent(session,self.context,TenantOperation.MEMBER_STATUS,'fixture-request',self.body,unsafe_callback)
            self.assertEqual(session.execute(text('SELECT status FROM wpl.organization_memberships WHERE id=:id'),{'id':self.member}).scalar_one(),'active')
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.idempotency_records WHERE org_id=:org'),{'org':self.a['org']}).scalar_one(),0)
        self.assertEqual(self.counts(),(0,0,'active'))

    def test_permission_is_rechecked_before_returning_cached_receipt(self):
        context=RequestContext(VerifiedIdentity(self.second_actor),RequestScope.TENANT,self.a['org'])
        self.run_request(context=context)
        with connect() as owner:
            owner.execute("DELETE FROM wpl.organization_roles WHERE membership_id=%s AND role='admin'",(self.second_actor_member,))
        with self.assertRaises(AuthorizationDenied):self.run_request(context=context)
        with self.database.request_transaction(context) as session:
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.idempotency_records WHERE org_id=:org'),{'org':self.a['org']}).scalar_one(),0)
        self.assertEqual(self.counts(),(1,1,'suspended'))

    def test_unique_constraint_immutability_and_database_receipt_redaction_are_enforced(self):
        self.run_request()
        statements=(
            ('INSERT INTO wpl.idempotency_records('+COLUMNS+') SELECT '+COLUMNS+' FROM wpl.idempotency_records WHERE org_id=:org','23505'),
            ("UPDATE wpl.idempotency_records SET request_hash=repeat('0',64)",'42501'),
            ('DELETE FROM wpl.idempotency_records','42501'),
        )
        for statement,state in statements:
            with self.subTest(state=state),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(self.context) as session:
                    session.execute(text(statement),{'org':self.a['org']})
            self.assertEqual(result.exception.orig.sqlstate,state)
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(self.context) as session:
                response={'membership_id':str(self.member),'status':'active','version':1,'activation_token':'synthetic-private-marker'}
                session.execute(text("""INSERT INTO wpl.idempotency_records(actor_id,operation,scope_kind,scope_id,org_id,request_key,request_hash,response_status,response)
                    VALUES (:actor,'set_member_status','tenant',:org,:org,'unsafe-receipt',repeat('0',64),200,CAST(:body AS jsonb))"""),
                    {'actor':self.context.identity.subject,'org':self.a['org'],'body':json.dumps(response)})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
        self.assertEqual(self.counts(),(1,1,'suspended'))

    def test_bad_input_and_unbound_context_do_not_create_receipts(self):
        for key in ('','bad key','bad\nkey','x'*129):
            with self.subTest(length=len(key)),self.assertRaises(InvalidIdempotencyInput):self.run_request(key=key)
        for body in ([],{'v':float('nan')},{'v':'x'*33000}):
            with self.assertRaises(InvalidIdempotencyInput):self.run_request(body=body)
        with self.assertRaises(AuthorizationDenied):
            with self.database.transaction() as session:
                execute_idempotent(session,self.context,TenantOperation.MEMBER_STATUS,'fixture-request',self.body,self.mutation(self.context,self.body))
        with self.database.request_transaction(self.context) as session:
            with self.assertRaises(InvalidIdempotencyInput):
                execute_idempotent(session,self.context,'set_member_status','fixture-request',self.body,self.mutation(self.context,self.body))
        self.assertEqual(self.counts(),(0,0,'active'))
