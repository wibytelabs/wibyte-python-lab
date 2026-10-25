"""Synthetic provider store plus actual PostgreSQL worker/crash reconciliation.

This adapter is test-only. SQLite records an operation/digest, never sends mail or
stores raw recipients/tokens. Its durable unique key models a deduplicating provider,
not a claim that every external integration supplies exactly-once effects.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.jobs.enqueue import prepare_invitation,enqueue_invitation
from backend.app.domains.jobs.execution import process_delivery,DeliveryAcknowledgement
from backend.app.domains.jobs.payloads import PayloadCipher,encode_object
from backend.app.foundation.db import FoundationDatabase
from test_schema import connect
from test_enqueue import invitation,SyntheticKeys
import test_worker_leases as lease_fixtures


class SimulatedProcessCrash(BaseException):pass


class DurableFakeAdapter:
    def __init__(self,path,app,worker,*,crash=False,fail=False,accepted=None,release=None):
        self.path=path;self.app=app;self.worker=worker
        self.crash=crash;self.fail=fail;self.accepted=accepted;self.release=release
        with sqlite3.connect(self.path,timeout=5) as store:
            store.execute('CREATE TABLE IF NOT EXISTS effects(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL)')

    def deliver(self,operation_id,payload,*,timeout_seconds):
        if self.app.engine.pool.checkedout()!=0 or self.worker.engine.pool.checkedout()!=0:
            raise AssertionError('External effect attempted during database checkout')
        if timeout_seconds!=10:raise AssertionError('Missing bounded adapter timeout')
        if self.fail:raise RuntimeError('Synthetic provider detail '+payload['activation_token'])
        digest=hashlib.sha256(encode_object(payload)).hexdigest()
        with sqlite3.connect(self.path,timeout=5) as store:
            store.execute('INSERT INTO effects(operation_id,request_hash) VALUES (?,?) ON CONFLICT(operation_id) DO NOTHING',(str(operation_id),digest))
            if store.execute('SELECT request_hash FROM effects WHERE operation_id=?',(str(operation_id),)).fetchone()[0]!=digest:
                raise ValueError('Synthetic provider operation conflict')
        if self.accepted is not None:self.accepted.set()
        if self.release is not None and not self.release.wait(timeout=10):raise RuntimeError('Synthetic adapter barrier timed out')
        if self.crash:raise SimulatedProcessCrash('Synthetic process crash after durable fake acceptance')
        return DeliveryAcknowledgement.SIMULATED

    def count(self):
        with sqlite3.connect(self.path,timeout=5) as store:return store.execute('SELECT count(*) FROM effects').fetchone()[0]


class WorkerExecutionTests(unittest.TestCase):
    setUpClass=classmethod(lease_fixtures.WorkerLeaseTests.setUpClass.__func__)
    tearDownClass=classmethod(lease_fixtures.WorkerLeaseTests.tearDownClass.__func__)
    clear_jobs=lease_fixtures.WorkerLeaseTests.clear_jobs
    enqueue=lease_fixtures.WorkerLeaseTests.enqueue
    claim=lease_fixtures.WorkerLeaseTests.claim
    expire=lease_fixtures.WorkerLeaseTests.expire

    def setUp(self):
        lease_fixtures.WorkerLeaseTests.setUp(self)
        self.keys=SyntheticKeys(self.app);self.cipher=PayloadCipher(self.keys)
        directory=tempfile.TemporaryDirectory(prefix='wpl-fake-provider-');self.addCleanup(directory.cleanup)
        self.store=Path(directory.name)/'provider.sqlite'

    def adapter(self,worker=None,**options):return DurableFakeAdapter(self.store,self.app,worker or self.worker,**options)

    def process(self,lease,adapter,worker=None,worker_id=None,cipher=None):
        return process_delivery(worker or self.worker,worker_id or self.worker_id,lease,cipher or self.cipher,adapter)

    def state(self,identifier):
        with connect() as owner:
            return owner.execute('SELECT state,delivery_status,last_error_code FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone()

    def test_fake_acceptance_persists_simulated_status_and_public_replay_never_claims_mail(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        adapter=self.adapter();result=self.process(lease,adapter)
        self.assertEqual(result.public(),{'job_id':str(identifier),'state':'succeeded','delivery_status':'simulated'})
        self.assertEqual(self.state(identifier),('succeeded','simulated',None))
        self.assertEqual(adapter.count(),1)
        # Reconstruct the same pending invitation input for the original stable operation.
        with connect() as owner:
            payload_row=owner.execute('SELECT p.id,p.key_reference,p.ciphertext FROM wpl.jobs j JOIN wpl.secret_payloads p ON p.id=j.private_payload_id WHERE j.id=%s',(identifier,)).fetchone()
        from backend.app.domains.jobs.payloads import PayloadBinding,PayloadScope,EncryptedPayload
        binding=PayloadBinding(PayloadScope.TENANT,lease.org_id,lease.actor_id,identifier,payload_row[0],'deliver_invitation')
        payload=self.cipher.decrypt(EncryptedPayload(payload_row[1],bytes(payload_row[2])),binding)
        context=RequestContext(VerifiedIdentity(lease.actor_id),RequestScope.TENANT,lease.org_id)
        prepared=prepare_invitation(context,identifier,self.cipher,payload)
        with self.app.request_transaction(context) as session:replayed=enqueue_invitation(session,context,prepared)
        self.assertEqual(replayed.delivery_status,'simulated')
        with connect() as owner:
            events=owner.execute('SELECT changes FROM wpl.audit_events WHERE target_id=%s',(identifier,)).fetchall()
            self.assertNotIn(payload['activation_token'],repr(events))
            self.assertNotIn(payload['email'],repr(events))
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_acknowledged'",(identifier,)).fetchone()[0],1)
        self.assertEqual(self.worker.engine.pool.checkedout(),0)
        print('Synthetic adapter accepted one durable operation; persisted status is simulated. No mail provider contacted.',flush=True)

    def test_crash_after_fake_acceptance_reconciles_same_operation_after_new_pool_and_adapter(self):
        identifier=self.enqueue();old=self.claim(batch_size=1)[0]
        crashed=self.adapter(crash=True)
        with self.assertRaises(SimulatedProcessCrash):self.process(old,crashed)
        self.assertEqual(crashed.count(),1)
        self.assertEqual(self.state(identifier),('running','pending_integration',None))
        self.expire(identifier)
        restarted=FoundationDatabase(self._worker_settings())
        self.addCleanup(restarted.close)
        from backend.app.domains.jobs.leases import claim_deliveries
        worker_id=uuid4();new=claim_deliveries(restarted,worker_id,batch_size=1)[0]
        adapter=self.adapter(worker=restarted)
        restarted_keys=SyntheticKeys(self.app);restarted_keys.key=self.keys.key
        result=self.process(new,adapter,worker=restarted,worker_id=worker_id,cipher=PayloadCipher(restarted_keys))
        self.assertEqual((result.state,result.delivery_status),('succeeded','simulated'))
        self.assertEqual(adapter.count(),1)
        self.assertGreater(new.lease_generation,old.lease_generation)
        print('Crash after durable fake acceptance: new worker pool/adapter reclaimed and reconciled one stable operation, one simulated effect.',flush=True)

    def _worker_settings(self):
        from backend.app.foundation.settings import FoundationSettings
        return FoundationSettings(enabled=True,application_database_url=self.worker.engine.url,pool_size=2)

    def test_overlap_after_expiry_reclaim_fences_old_ack_and_provider_deduplicates(self):
        identifier=self.enqueue();old=self.claim(batch_size=1)[0]
        accepted=threading.Event();release=threading.Event()
        old_adapter=self.adapter(accepted=accepted,release=release)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.process,old,old_adapter)
            try:
                self.assertTrue(accepted.wait(timeout=10))
                self.expire(identifier)
                new_owner=uuid4();new=self.claim(new_owner,batch_size=1)[0]
                result=self.process(new,self.adapter(),worker_id=new_owner)
                self.assertEqual(result.delivery_status,'simulated')
            finally:release.set()
            late=future.result(timeout=15)
        self.assertEqual(late.state,'lease_lost')
        self.assertEqual(old_adapter.count(),1)
        self.assertEqual(self.state(identifier),('succeeded','simulated',None))
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_succeeded'",(identifier,)).fetchone()[0],1)

    def test_transport_failure_has_fixed_error_then_retry_uses_same_provider_operation(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        adapter=self.adapter(fail=True)
        result=self.process(lease,adapter)
        self.assertEqual((result.state,result.delivery_status),('queued','pending_integration'))
        self.assertEqual(self.state(identifier),('queued','pending_integration','transport_unavailable'))
        self.assertEqual(adapter.count(),0)
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET available_at='1990-01-01' WHERE id=%s",(identifier,))
        new=self.claim(batch_size=1)[0]
        adapter=self.adapter()
        self.assertEqual(self.process(new,adapter).delivery_status,'simulated')
        self.assertEqual(adapter.count(),1)

    def test_key_failure_and_tampered_ciphertext_never_invoke_adapter(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        adapter=self.adapter();self.keys.blocked=True
        result=self.process(lease,adapter)
        self.assertEqual(result.state,'queued')
        self.assertEqual(self.state(identifier)[2],'key_unavailable')
        self.assertEqual(adapter.count(),0)
        self.keys.blocked=False
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        with connect() as owner:
            owner.execute("UPDATE wpl.secret_payloads SET ciphertext=%s WHERE id=(SELECT private_payload_id FROM wpl.jobs WHERE id=%s)",(b'WPL1'+b'x'*64,identifier))
        self.assertEqual(self.process(lease,adapter).state,'cancelled')
        self.assertEqual(self.state(identifier)[2],'payload_invalid')
        self.assertEqual(adapter.count(),0)

    def test_role_revoked_during_key_resolution_and_revoked_invitation_block_effects(self):
        identifier=self.enqueue(actor=self.admin);lease=self.claim(batch_size=1)[0]
        ordinary=self.keys
        class RevokingKeys:
            def current_reference(self):return ordinary.current_reference()
            def resolve(provider,reference):
                key=ordinary.resolve(reference)
                with connect() as owner:owner.execute("DELETE FROM wpl.organization_roles WHERE membership_id=%s AND role='admin'",(self.member,))
                return key
        adapter=self.adapter()
        result=self.process(lease,adapter,cipher=PayloadCipher(RevokingKeys()))
        self.assertEqual(result.state,'cancelled')
        self.assertEqual(self.state(identifier)[2],'actor_not_authorized')
        self.assertEqual(adapter.count(),0)
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        with connect() as owner:owner.execute("UPDATE wpl.invitations SET status='revoked' WHERE org_id=%s AND status='pending'",(self.a['org'],))
        self.assertEqual(self.process(lease,adapter).state,'cancelled')
        self.assertEqual(self.state(identifier)[2],'target_unavailable')
        self.assertEqual(adapter.count(),0)

    def test_real_ack_constraint_failure_rolls_back_completion_then_reconciles_fake_effect(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        adapter=self.adapter()
        with connect() as owner:owner.execute("ALTER TABLE wpl.jobs ADD CONSTRAINT fixture_reject_simulated CHECK(delivery_status<>'simulated') NOT VALID")
        try:
            with self.assertRaises(DBAPIError) as result:self.process(lease,adapter)
            self.assertEqual(result.exception.orig.sqlstate,'23514')
        finally:
            with connect() as owner:owner.execute('ALTER TABLE wpl.jobs DROP CONSTRAINT fixture_reject_simulated')
        self.assertEqual(adapter.count(),1)
        self.assertEqual(self.state(identifier),('running','pending_integration',None))
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action IN ('job_succeeded','job_acknowledged')",(identifier,)).fetchone()[0],0)
        self.expire(identifier)
        new=self.claim(batch_size=1)[0]
        self.assertEqual(self.process(new,self.adapter()).delivery_status,'simulated')
        self.assertEqual(adapter.count(),1)

    def test_adapter_is_explicit_and_unrecognized_acknowledgement_does_not_claim_delivery(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        with self.assertRaises(ValueError):self.process(lease,None)
        class UnrecognizedAdapter:
            def deliver(adapter,operation_id,payload,*,timeout_seconds):return 'Delivered'
        result=self.process(lease,UnrecognizedAdapter())
        self.assertEqual((result.state,result.delivery_status),('queued','pending_integration'))
        self.assertEqual(self.state(identifier)[2],'transport_unavailable')
        with self.assertRaises(DBAPIError):
            with self.app.transaction() as session:
                session.execute(text("SELECT wpl.acknowledge_delivery(:job,:worker,1,'simulated')"),{'job':identifier,'worker':self.worker_id})
