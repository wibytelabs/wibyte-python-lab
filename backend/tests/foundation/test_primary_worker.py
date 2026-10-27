"""Signed create -> restricted worker -> durable fake effect -> redacted status."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.jobs.enqueue import prepare_invitation,enqueue_invitation
from backend.app.domains.jobs.execution import process_delivery
from backend.app.domains.jobs.leases import claim_deliveries
from backend.app.domains.jobs.transitions import load_delivery
from backend.app.domains.jobs.payloads import encode_object
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings,postgres_url
from test_schema import connect
from test_enqueue import invitation
import test_http_provisioning as http_fixture
import test_worker_execution as fake_fixture


class PrimaryWorkerTests(unittest.TestCase):
    setUpClass=classmethod(http_fixture.HTTPProvisioningTests.setUpClass.__func__)
    token=http_fixture.HTTPProvisioningTests.token
    get=http_fixture.HTTPProvisioningTests.get
    assert_error=http_fixture.HTTPProvisioningTests.assert_error
    make_app=http_fixture.HTTPProvisioningTests.make_app
    post=http_fixture.HTTPProvisioningTests.post

    def setUp(self):
        http_fixture.HTTPProvisioningTests.setUp(self)
        url=postgres_url(os.environ['WPL_WORKER_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture primary worker target.')
        self.worker_settings=FoundationSettings(enabled=True,application_database_url=url,pool_size=2)
        self.worker=FoundationDatabase(self.worker_settings);self.addCleanup(self.worker.close)
        self.worker.verify_runtime_role();self.worker_id=uuid4();self.ids=[]
        self.keys.before_resolve=lambda:self.assertEqual(self.worker.engine.pool.checkedout(),0)
        directory=tempfile.TemporaryDirectory(prefix='wpl-primary-fake-');self.addCleanup(directory.cleanup)
        self.store=Path(directory.name)/'provider.sqlite'
        self.addCleanup(self.clear_jobs)

    def clear_jobs(self):
        with connect() as owner:
            for identifier in self.ids:owner.execute("UPDATE wpl.jobs SET state='cancelled',lease_owner=NULL,lease_until=NULL WHERE id=%s AND state IN ('queued','running')",(identifier,))

    def new_job(self):
        response=self.post(key='primary-worker-'+uuid4().hex)
        self.assertEqual(response.status_code,201,response.text)
        receipt=response.json();self.ids.append(receipt['job_id'])
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET available_at='1980-01-01' WHERE id=%s",(receipt['job_id'],))
        return receipt

    def claim(self,worker_id=None,database=None):return claim_deliveries(database or self.worker,worker_id or self.worker_id,batch_size=1)
    def adapter(self,worker=None,**options):return fake_fixture.DurableFakeAdapter(self.store,self.database,worker or self.worker,**options)
    def process(self,lease,adapter=None,worker=None,worker_id=None):
        return process_delivery(worker or self.worker,worker_id or self.worker_id,lease,
            self.app.state.foundation_payload_cipher,adapter or self.adapter(worker))

    def test_signed_create_worker_fake_ack_keeps_primary_and_organization_pending(self):
        receipt=self.new_job();lease=self.claim()[0]
        self.assertEqual(str(lease.job_id),receipt['job_id'])
        result=self.process(lease)
        self.assertEqual((result.state,result.delivery_status),('succeeded','simulated'))
        path='/v1/platform/organizations/'+receipt['org_id']+'/jobs/'+receipt['job_id']
        response=self.get(path,self.executive)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['delivery_status'],'simulated')
        self.assertNotIn('primary@example.invalid',response.text)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.organizations WHERE id=%s',(receipt['org_id'],)).fetchone()[0],'pending')
            self.assertEqual(owner.execute('SELECT status,user_id FROM wpl.organization_memberships WHERE id=%s',(receipt['primary_admin_membership_id'],)).fetchone(),('invite_pending',None))
            self.assertEqual(owner.execute('SELECT status FROM wpl.invitations WHERE org_id=%s',(receipt['org_id'],)).fetchone()[0],'pending')
            self.assertEqual(owner.execute("SELECT actor_id FROM wpl.audit_events WHERE target_id=%s AND action='job_acknowledged'",(receipt['job_id'],)).fetchone()[0],self.executive)
        self.assertEqual(self.adapter().count(),1)
        print('Signed HTTP create -> actual wpl_worker -> one simulated initial-primary effect; org/designation/invitation remain pending, no activation or mail provider.',flush=True)

    def test_stored_executive_capability_expiry_global_state_and_pending_scope_are_rechecked(self):
        for kind in ('capability','expiry','global','organization'):
            with self.subTest(kind=kind):
                with connect() as owner:
                    owner.execute("UPDATE wpl.users SET global_state='active' WHERE id=%s",(self.executive,))
                    owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Explicit synthetic restore') ON CONFLICT(user_id,capability) DO UPDATE SET expires_at=NULL",(self.executive,))
                receipt=self.new_job()
                with connect() as owner:
                    if kind=='capability':owner.execute('DELETE FROM wpl.platform_roles WHERE user_id=%s',(self.executive,))
                    elif kind=='expiry':owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s",(self.executive,))
                    elif kind=='global':owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.executive,))
                    else:
                        # Explicit owner-only acceptance fixture; this does not implement invitation redemption.
                        accepted=uuid4();owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(accepted,))
                        owner.execute("UPDATE wpl.invitations SET status='accepted',accepted_user_id=%s,accepted_at=now() WHERE org_id=%s",(accepted,receipt['org_id']))
                        owner.execute("UPDATE wpl.organization_memberships SET user_id=%s,status='active' WHERE id=%s",(accepted,receipt['primary_admin_membership_id']))
                        owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(receipt['org_id'],))
                self.assertEqual(self.claim(),[])
                with connect() as owner:
                    self.assertEqual(owner.execute('SELECT state,last_error_code FROM wpl.jobs WHERE id=%s',(receipt['job_id'],)).fetchone(),('cancelled','actor_not_authorized'))
        self.assertEqual(self.adapter().count(),0)

    def test_revocation_after_claim_cancels_before_payload_or_effect(self):
        receipt=self.new_job();lease=self.claim()[0]
        with connect() as owner:owner.execute('DELETE FROM wpl.platform_roles WHERE user_id=%s',(self.executive,))
        self.assertIsNone(load_delivery(self.worker,self.worker_id,lease))
        self.assertEqual(self.process(lease).state,'cancelled')
        self.assertEqual(self.adapter().count(),0)
        with connect() as owner:self.assertEqual(owner.execute('SELECT last_error_code FROM wpl.jobs WHERE id=%s',(receipt['job_id'],)).fetchone()[0],'actor_not_authorized')

    def test_revoked_or_expired_pending_invitation_cannot_create_fake_effect(self):
        for kind in ('revoked','expired'):
            with self.subTest(kind=kind):
                receipt=self.new_job();lease=self.claim()[0]
                with connect() as owner:
                    if kind=='revoked':owner.execute("UPDATE wpl.invitations SET status='revoked' WHERE org_id=%s",(receipt['org_id'],))
                    else:owner.execute("UPDATE wpl.invitations SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE org_id=%s",(receipt['org_id'],))
                self.assertEqual(self.process(lease).state,'cancelled')
                with connect() as owner:self.assertEqual(owner.execute('SELECT last_error_code FROM wpl.jobs WHERE id=%s',(receipt['job_id'],)).fetchone()[0],'target_unavailable')
        self.assertEqual(self.adapter().count(),0)

    def test_nondesignated_invitation_is_denied_even_with_authenticated_matching_intent_fixture(self):
        receipt=self.new_job();lease=self.claim()[0]
        material=load_delivery(self.worker,self.worker_id,lease)
        with connect() as owner:other=invitation(owner,lease.org_id)
        envelope=self.app.state.foundation_payload_cipher.encrypt(other,material.binding)
        digest=hashlib.sha256(encode_object({'actor_id':str(lease.actor_id),'org_id':str(lease.org_id),
            'kind':'deliver_primary_invitation','payload':other})).hexdigest()
        with connect() as owner:
            owner.execute('UPDATE wpl.secret_payloads SET ciphertext=%s,key_reference=%s WHERE id=%s',(envelope.ciphertext,envelope.key_reference,material.binding.payload_id))
            owner.execute('UPDATE wpl.jobs SET intent_hash=%s WHERE id=%s',(digest,lease.job_id))
        self.assertEqual(self.process(lease).state,'cancelled')
        self.assertEqual(self.adapter().count(),0)

    def test_competing_mixed_kind_claims_keep_tenant_and_primary_purposes_separate(self):
        primary=self.new_job()
        with connect() as owner:payload=invitation(owner,self.a['org'])
        context=RequestContext(VerifiedIdentity(self.a['user']),RequestScope.TENANT,self.a['org'])
        identifier=uuid4();self.ids.append(identifier)
        prepared=prepare_invitation(context,identifier,self.app.state.foundation_payload_cipher,payload)
        with self.database.request_transaction(context) as session:enqueue_invitation(session,context,prepared)
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET available_at='1980-01-01' WHERE id=%s",(identifier,))
        barrier=threading.Barrier(2)
        def run():
            worker_id=uuid4();barrier.wait(timeout=5)
            return worker_id,self.claim(worker_id)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run) for _ in range(2)]
            claims=[future.result(timeout=15) for future in futures]
        self.assertEqual({str(lease.job_id) for _,lease in claims},{primary['job_id'],str(identifier)})
        purposes=set()
        for worker_id,lease in claims:
            material=load_delivery(self.worker,worker_id,lease);purposes.add(material.binding.purpose)
            self.assertEqual(self.process(lease,worker_id=worker_id).delivery_status,'simulated')
        self.assertEqual(purposes,{'deliver_invitation','deliver_primary_invitation'})
        self.assertEqual(self.adapter().count(),2)

    def test_primary_crash_after_fake_acceptance_reclaims_and_reconciles_one_effect(self):
        receipt=self.new_job();old=self.claim()[0]
        with self.assertRaises(fake_fixture.SimulatedProcessCrash):self.process(old,self.adapter(crash=True))
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(old.job_id,))
        restarted=FoundationDatabase(self.worker_settings);self.addCleanup(restarted.close)
        worker_id=uuid4();new=self.claim(worker_id,restarted)[0]
        self.assertGreater(new.lease_generation,old.lease_generation)
        self.assertEqual(self.process(new,self.adapter(restarted),restarted,worker_id).delivery_status,'simulated')
        self.assertEqual(self.process(old).state,'lease_lost')
        self.assertEqual(self.adapter().count(),1)
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_succeeded'",(receipt['job_id'],)).fetchone()[0],1)

    def test_worker_context_cannot_relabel_tenant_admin_as_executive_or_execute_private_helper(self):
        receipt=self.new_job()
        with connect() as owner:owner.execute('UPDATE wpl.jobs SET actor_id=%s WHERE id=%s',(self.a['user'],receipt['job_id']))
        with self.worker.request_transaction(RequestContext(VerifiedIdentity(self.executive),RequestScope.PLATFORM)) as session:
            rows=session.execute(text('SELECT * FROM wpl.claim_deliveries(:worker,1,60)'),{'worker':self.worker_id}).all()
            self.assertEqual(rows,[])
        self.assertEqual(self.adapter().count(),0)
        for database in (self.database,self.worker):
            with self.assertRaises(DBAPIError) as error:
                with database.transaction() as session:
                    session.execute(text("SELECT wpl.job_delivery_actor_allowed(:actor,:org,'deliver_primary_invitation')"),{'actor':self.executive,'org':receipt['org_id']})
            self.assertEqual(error.exception.orig.sqlstate,'42501')
