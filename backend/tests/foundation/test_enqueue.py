"""Real wpl_app queue intent, encrypted persistence, outbox and atomicity tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading
import unittest
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadKeyUnavailable,EncryptedPayload
from backend.app.domains.jobs.enqueue import prepare_invitation,enqueue_invitation
from backend.app.domains.jobs.idempotency import execute_idempotent,TenantOperation,MutationResult
from backend.app.domains.organizations.service import set_member_status
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings,postgres_url
from backend.app.foundation.migrate import migrate
from test_schema import connect,seed_org
from test_guards import add_member


class SyntheticKeys:
    def __init__(self,database):
        self.key=AESGCM.generate_key(bit_length=256)
        self.database=database
        self.calls=0
        self.blocked=False
    def current_reference(self):return 'fixture/delivery-key'
    def resolve(self,reference):
        if self.blocked:raise RuntimeError('Key provider called after preparation')
        if self.database.engine.pool.checkedout()!=0:raise RuntimeError('Key resolution inside checked-out DB transaction')
        if reference!='fixture/delivery-key':raise KeyError
        self.calls+=1
        return self.key


def invitation(owner,org):
    member,identifier=uuid4(),uuid4()
    email='recipient-'+uuid4().hex+'@example.invalid'
    token='synthetic-token-'+uuid4().hex+'-'+uuid4().hex
    owner.execute("INSERT INTO wpl.organization_memberships(id,org_id,invitation_id,status) VALUES (%s,%s,%s,'invite_pending')",(member,org,identifier))
    owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'student')",(org,member))
    owner.execute("""INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,token_hash,expires_at)
        VALUES (%s,%s,%s,%s,ARRAY['student'],%s,now()+interval '1 day')""",
        (identifier,org,member,email,hashlib.sha256(token.encode()).digest()))
    return {'invitation_id':str(identifier),'email':email,'activation_token':token}


class EnqueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture queue target.')
        cls.settings=FoundationSettings(enabled=True,application_database_url=url,pool_size=2)
        cls.database=FoundationDatabase(cls.settings)

    @classmethod
    def tearDownClass(cls):cls.database.close()

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.student,self.student_member=add_member(owner,self.a['org'],('student',))
            self.admin,self.admin_member=add_member(owner,self.a['org'],('admin',))
            self.payload=invitation(owner,self.a['org'])
            self.b_payload=invitation(owner,self.b['org'])
            for fixture in (self.a,self.b):owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            self.version=owner.execute('SELECT version FROM wpl.organization_memberships WHERE id=%s',(self.student_member,)).fetchone()[0]
        self.context=RequestContext(VerifiedIdentity(self.a['user']),RequestScope.TENANT,self.a['org'])
        self.delivery_id=uuid4()
        self.keys=SyntheticKeys(self.database)
        self.cipher=PayloadCipher(self.keys)

    def prepare(self,payload=None,context=None,identifier=None):
        return prepare_invitation(context or self.context,identifier or self.delivery_id,self.cipher,payload or self.payload)

    def enqueue(self,prepared,context=None,database=None):
        context=context or self.context
        with (database or self.database).request_transaction(context) as session:
            return enqueue_invitation(session,context,prepared)

    def counts(self):
        with connect() as owner:
            values=[owner.execute(f'SELECT count(*) FROM wpl.{table} WHERE org_id=%s',(self.a['org'],)).fetchone()[0]
                    for table in ('secret_payloads','jobs','audit_events','idempotency_records')]
            outbox=owner.execute("SELECT count(*) FROM wpl.outbox WHERE scope_kind='tenant' AND scope_id=%s",(self.a['org'],)).fetchone()[0]
            status=owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.student_member,)).fetchone()[0]
        return (*values,outbox,status)

    def business_callback(self,prepared):
        def callback(session):
            result=set_member_status(session,self.context.identity,self.a['org'],self.student_member,'suspended',self.version,'Synthetic atomic queue mutation')
            enqueue_invitation(session,self.context,prepared)
            return MutationResult(200,{'membership_id':str(result['id']),'status':result['status'],'version':result['version']})
        return callback

    def business_request(self,session,prepared):
        return execute_idempotent(session,self.context,TenantOperation.MEMBER_STATUS,'queue-business-request',
            {'membership_id':str(self.student_member),'version':self.version},self.business_callback(prepared))

    def test_enqueue_persists_ciphertext_job_outbox_and_redacted_audit_not_delivery(self):
        prepared=self.prepare()
        receipt=self.enqueue(prepared)
        self.assertEqual(receipt.public(),{'job_id':str(self.delivery_id),'state':'queued','delivery_status':'pending_integration'})
        self.assertEqual(self.counts(),(1,1,1,0,1,'active'))
        self.assertNotIn(self.payload['activation_token'],repr(prepared))
        self.assertNotIn(self.payload['email'],repr(prepared))
        self.assertNotIn(self.payload['activation_token'],json.dumps(receipt.public()))
        with connect() as owner:
            row=owner.execute('SELECT key_reference,ciphertext FROM wpl.secret_payloads WHERE id=%s',(prepared.binding.payload_id,)).fetchone()
            envelope=EncryptedPayload(row[0],bytes(row[1]))
            job=owner.execute('SELECT actor_id,state,attempts,lease_generation FROM wpl.jobs WHERE id=%s',(self.delivery_id,)).fetchone()
            self.assertEqual(job,(self.context.identity.subject,'queued',0,0))
            self.assertEqual(owner.execute('SELECT state,dispatched_at FROM wpl.outbox WHERE job_id=%s',(self.delivery_id,)).fetchone(),('pending',None))
            audit=owner.execute('SELECT actor_id,changes FROM wpl.audit_events WHERE target_id=%s',(self.delivery_id,)).fetchone()
            self.assertEqual(audit[0],self.context.identity.subject)
            self.assertNotIn(self.payload['activation_token'],json.dumps(audit[1]))
            self.assertNotIn(self.payload['email'],json.dumps(audit[1]))
        self.assertNotIn(self.payload['activation_token'].encode(),envelope.ciphertext)
        self.assertEqual(self.cipher.decrypt(envelope,prepared.binding),self.payload)
        print('Actual wpl_app enqueue: encrypted payload, queued job, pending outbox, redacted audit; no provider contacted.',flush=True)

    def test_same_operation_concurrency_deduplicates_without_orphan_ciphertexts(self):
        first,second=self.prepare(),self.prepare()
        self.assertNotEqual(first.binding.payload_id,second.binding.payload_id)
        barrier=threading.Barrier(2)
        def run(prepared):
            barrier.wait(timeout=5)
            return self.enqueue(prepared)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,prepared) for prepared in (first,second)]
            receipts=[future.result(timeout=15) for future in futures]
        self.assertEqual(receipts[0],receipts[1])
        self.assertEqual(self.counts(),(1,1,1,0,1,'active'))

    def test_reused_delivery_id_with_different_valid_intent_conflicts(self):
        self.enqueue(self.prepare())
        with connect() as owner:other=invitation(owner,self.a['org'])
        changed=self.prepare(other)
        with self.assertRaises(TenantConflict) as result:self.enqueue(changed)
        self.assertEqual(result.exception.code,'job_conflict')
        self.assertEqual(self.counts(),(1,1,1,0,1,'active'))

    def test_outer_rollback_and_committed_retry_include_business_audit_outbox_and_receipt(self):
        prepared=self.prepare()
        with self.assertRaisesRegex(RuntimeError,'synthetic outer rollback'):
            with self.database.request_transaction(self.context) as session:
                self.business_request(session,prepared)
                raise RuntimeError('synthetic outer rollback')
        self.assertEqual(self.counts(),(0,0,0,0,0,'active'))
        with self.database.request_transaction(self.context) as session:
            result=self.business_request(session,prepared)
            self.assertFalse(result.replayed)
        self.assertEqual(self.counts(),(1,1,2,1,1,'suspended'))
        other=FoundationDatabase(self.settings);self.addCleanup(other.close)
        self.assertEqual(self.enqueue(prepared,database=other).job_id,self.delivery_id)
        self.assertEqual(self.counts(),(1,1,2,1,1,'suspended'))

    def test_real_outbox_constraint_failure_rolls_back_business_and_new_queue_rows(self):
        prepared=self.prepare()
        with connect() as owner:
            old=uuid4()
            owner.execute("""INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key)
                VALUES (%s,'tenant',%s,%s,%s,'fixture_only',%s)""",(old,self.a['org'],self.a['org'],self.a['user'],str(old)))
            owner.execute("""INSERT INTO wpl.outbox(id,scope_kind,scope_id,job_id,event_kind,dedup_key)
                VALUES (%s,'tenant',%s,%s,'delivery_requested',%s)""",(uuid4(),self.a['org'],old,'delivery:'+str(self.delivery_id)))
        before=self.counts()
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(self.context) as session:self.business_request(session,prepared)
        self.assertEqual(result.exception.orig.sqlstate,'23505')
        self.assertEqual(self.counts(),before)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.jobs WHERE id=%s',(self.delivery_id,)).fetchone()[0],0)

    def test_key_resolution_is_before_uow_and_key_failure_creates_no_queue_state(self):
        prepared=self.prepare()
        calls=self.keys.calls
        self.keys.blocked=True
        self.enqueue(prepared)
        self.assertEqual(self.keys.calls,calls)
        self.assertEqual(self.counts(),(1,1,1,0,1,'active'))
        with self.assertRaises(PayloadKeyUnavailable):self.prepare(identifier=uuid4())
        self.assertEqual(self.database.engine.pool.checkedout(),0)
        self.assertEqual(self.counts(),(1,1,1,0,1,'active'))

    def test_bad_target_recipient_token_scope_expiry_or_revocation_creates_no_job(self):
        payloads=[{**self.payload,'email':'other@example.invalid'},
                  {**self.payload,'activation_token':'synthetic-invalid-token-'+'x'*40},self.b_payload]
        for state in ('expired','revoked'):
            with connect() as owner:
                payload=invitation(owner,self.a['org'])
                if state=='expired':
                    owner.execute("UPDATE wpl.invitations SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=%s",(payload['invitation_id'],))
                else:owner.execute("UPDATE wpl.invitations SET status='revoked' WHERE id=%s",(payload['invitation_id'],))
            payloads.append(payload)
        for payload in payloads:
            with self.subTest(case=payload['invitation_id']),self.assertRaises(TenantConflict) as result:
                self.enqueue(self.prepare(payload))
            self.assertEqual(result.exception.code,'delivery_target_unavailable')
        self.assertEqual(self.counts(),(0,0,0,0,0,'active'))

    def test_nonadmin_and_context_substitution_are_denied(self):
        student=RequestContext(VerifiedIdentity(self.student),RequestScope.TENANT,self.a['org'])
        prepared=self.prepare(context=student)
        with self.assertRaises(AuthorizationDenied):self.enqueue(prepared,student)
        original=self.prepare()
        other=RequestContext(VerifiedIdentity(self.admin),RequestScope.TENANT,self.a['org'])
        with self.assertRaises(AuthorizationDenied):
            with self.database.request_transaction(other) as session:enqueue_invitation(session,self.context,original)
        with self.assertRaises(AuthorizationDenied):self.enqueue(original,other)
        self.assertEqual(self.counts(),(0,0,0,0,0,'active'))

    def test_job_reads_are_scoped_and_application_cannot_complete_or_read_secrets(self):
        prepared=self.prepare();self.enqueue(prepared)
        for context,expected in ((self.context,1),
                (RequestContext(VerifiedIdentity(self.admin),RequestScope.TENANT,self.a['org']),1),
                (RequestContext(VerifiedIdentity(self.student),RequestScope.TENANT,self.a['org']),0),
                (RequestContext(VerifiedIdentity(self.b['user']),RequestScope.TENANT,self.b['org']),0)):
            with self.database.request_transaction(context) as session:
                self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.jobs WHERE id=:id'),{'id':self.delivery_id}).scalar_one(),expected)
        for statement in ("UPDATE wpl.jobs SET state='succeeded'",'DELETE FROM wpl.jobs',
                          "UPDATE wpl.outbox SET state='dispatched',dispatched_at=now()",'SELECT ciphertext FROM wpl.secret_payloads'):
            with self.subTest(operation=statement.split()[0]),self.assertRaises(DBAPIError) as result:
                with self.database.request_transaction(self.context) as session:session.execute(text(statement))
            self.assertEqual(result.exception.orig.sqlstate,'42501')
        with connect('WORKER') as worker:
            import psycopg
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):worker.execute('SELECT * FROM wpl.jobs')

    def test_legacy_unverified_job_id_collision_is_not_adopted_and_has_no_orphan_payload(self):
        prepared=self.prepare()
        with connect() as owner:
            owner.execute("""INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key)
                VALUES (%s,'tenant',%s,%s,%s,'deliver_invitation','legacy-fixture')""",
                (self.delivery_id,self.a['org'],self.a['org'],self.a['user']))
        with self.assertRaises(TenantConflict) as result:self.enqueue(prepared)
        self.assertEqual(result.exception.code,'job_conflict')
        self.assertEqual(self.counts(),(0,1,0,0,0,'active'))
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT intent_hash,private_payload_id FROM wpl.jobs WHERE id=%s',(self.delivery_id,)).fetchone(),(None,None))
