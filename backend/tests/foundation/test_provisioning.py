"""Actual runtime-role pending provisioning, idempotency and rollback proof."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import threading
import unittest
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.organizations.requests import OrganizationCreate
from backend.app.domains.organizations.provisioning import prepare_organization,create_organization
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadKeyUnavailable,EncryptedPayload
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings,postgres_url
from backend.app.foundation.migrate import migrate
from test_schema import connect
from test_enqueue import SyntheticKeys


class ProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture provisioning target.')
        cls.settings=FoundationSettings(enabled=True,application_database_url=url,pool_size=2)
        cls.database=FoundationDatabase(cls.settings)

    @classmethod
    def tearDownClass(cls):cls.database.close()

    def setUp(self):
        self.actor,self.other,self.ordinary=(uuid4() for _ in range(3))
        with connect() as owner:
            for actor in (self.actor,self.other,self.ordinary):owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(actor,))
            for actor in (self.actor,self.other):owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Explicit synthetic provisioning executive')",(actor,))
        self.context=RequestContext(VerifiedIdentity(self.actor),RequestScope.PLATFORM)
        self.request=OrganizationCreate(name='Synthetic pending school',organization_type='school',
            contact_email='contact@example.invalid',home_region='fixture',primary_admin_email='primary@example.invalid',
            reason='Explicit synthetic initial provisioning')
        self.keys=SyntheticKeys(self.database);self.cipher=PayloadCipher(self.keys)

    def prepare(self,context=None,request=None):return prepare_organization(context or self.context,request or self.request,self.cipher)

    def create(self,prepared,key='synthetic-create',context=None,database=None):
        context=context or self.context
        with (database or self.database).request_transaction(context) as session:
            return create_organization(session,context,key,prepared)

    def counts(self,org):
        with connect() as owner:
            result=[owner.execute('SELECT count(*) FROM wpl.organizations WHERE id=%s',(org,)).fetchone()[0]]
            for table in ('organization_memberships','organization_roles','invitations','secret_payloads','jobs'):
                result.append(owner.execute(f'SELECT count(*) FROM wpl.{table} WHERE org_id=%s',(org,)).fetchone()[0])
            result.append(owner.execute('SELECT count(*) FROM wpl.outbox WHERE scope_id=%s',(org,)).fetchone()[0])
            result.append(owner.execute('SELECT count(*) FROM wpl.audit_events WHERE org_id=%s',(org,)).fetchone()[0])
            result.append(owner.execute("SELECT count(*) FROM wpl.idempotency_records WHERE response->>'org_id'=%s",(str(org),)).fetchone()[0])
        return tuple(result)

    def test_creation_persists_one_pending_primary_without_email_binding_or_delivery_claim(self):
        with connect() as owner:
            same_email=uuid4()
            owner.execute("INSERT INTO wpl.users(id,verified_email,global_state) VALUES (%s,'primary@example.invalid','active')",(same_email,))
        prepared=self.prepare();result=self.create(prepared)
        self.assertFalse(result.replayed)
        self.assertEqual(self.counts(prepared.org_id),(1,1,1,1,1,1,1,2,1))
        receipt=result.public()
        self.assertEqual((receipt['status'],receipt['invitation_status'],receipt['delivery_status']),('pending','pending','pending_integration'))
        with connect() as owner:
            member=owner.execute('SELECT user_id,status,invitation_id FROM wpl.organization_memberships WHERE id=%s',(prepared.member_id,)).fetchone()
            self.assertEqual(member,(None,'invite_pending',prepared.invitation_id))
            row=owner.execute('SELECT key_reference,ciphertext FROM wpl.secret_payloads WHERE id=%s',(prepared.binding.payload_id,)).fetchone()
            job=owner.execute('SELECT actor_id,kind,state FROM wpl.jobs WHERE id=%s',(prepared.binding.operation_id,)).fetchone()
            self.assertEqual(job,(self.actor,'deliver_primary_invitation','queued'))
            self.assertEqual(owner.execute('SELECT state FROM wpl.outbox WHERE job_id=%s',(prepared.binding.operation_id,)).fetchone()[0],'pending')
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.platform_roles WHERE user_id=%s',(same_email,)).fetchone()[0],0)
            audit=owner.execute('SELECT changes FROM wpl.audit_events WHERE org_id=%s',(prepared.org_id,)).fetchall()
        value=self.cipher.decrypt(EncryptedPayload(row[0],bytes(row[1])),prepared.binding)
        self.assertEqual(value['email'],'primary@example.invalid')
        self.assertNotIn(value['activation_token'],repr(prepared))
        self.assertNotIn(value['email'],repr(prepared))
        self.assertNotIn(value['activation_token'],repr(receipt)+repr(audit))
        self.assertNotIn(value['email'],repr(receipt)+repr(audit))
        print('Actual wpl_app provisioning: one pending org/designated invite membership, encrypted intent, outbox/audit/receipt; no user binding, activation or delivery.',flush=True)

    def test_concurrent_same_actor_key_body_creates_one_org_invitation_and_delivery_intent(self):
        prepared=[self.prepare(),self.prepare()];barrier=threading.Barrier(2)
        def run(candidate):
            with self.database.request_transaction(self.context) as session:
                barrier.wait(timeout=5)
                return create_organization(session,self.context,'concurrent-create',candidate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,candidate) for candidate in prepared]
            results=[future.result(timeout=15) for future in futures]
        self.assertEqual(results[0].public(),results[1].public())
        self.assertCountEqual([result.replayed for result in results],[False,True])
        winner=results[0].public()['org_id']
        for candidate in prepared:
            self.assertEqual(self.counts(candidate.org_id),(1,1,1,1,1,1,1,2,1) if str(candidate.org_id)==winner else (0,)*9)
        print('Actual concurrent wpl_app org create: one org/primary invitation/job/outbox, same public receipt; one replay.',flush=True)

    def test_replay_after_new_pool_and_changed_body_conflict_do_not_repeat_effect(self):
        first=self.prepare();receipt=self.create(first)
        restarted=FoundationDatabase(self.settings);self.addCleanup(restarted.close)
        second=self.prepare();replay=self.create(second,database=restarted)
        self.assertTrue(replay.replayed);self.assertEqual(replay.public(),receipt.public())
        self.assertEqual(self.counts(second.org_id),(0,)*9)
        changed=OrganizationCreate(**{**self.request.model_dump(),'name':'Different synthetic organization'})
        candidate=self.prepare(request=changed)
        with self.assertRaises(TenantConflict) as conflict:self.create(candidate)
        self.assertEqual(conflict.exception.code,'idempotency_conflict')
        self.assertEqual(self.counts(candidate.org_id),(0,)*9)
        self.assertEqual(self.counts(first.org_id),(1,1,1,1,1,1,1,2,1))

    def test_actor_key_namespace_and_current_capability_recheck_protect_cached_receipts(self):
        first=self.prepare();receipt=self.create(first)
        other=RequestContext(VerifiedIdentity(self.other),RequestScope.PLATFORM)
        second=self.prepare(context=other);other_result=self.create(second,context=other)
        self.assertNotEqual(receipt.public()['org_id'],other_result.public()['org_id'])
        with connect() as owner:owner.execute('DELETE FROM wpl.platform_roles WHERE user_id=%s',(self.actor,))
        with self.assertRaises(AuthorizationDenied):self.create(self.prepare())
        self.assertEqual(self.counts(first.org_id),(1,1,1,1,1,1,1,2,1))

    def test_outer_rollback_removes_entire_creation_and_same_preparation_can_retry(self):
        prepared=self.prepare()
        with self.assertRaisesRegex(RuntimeError,'synthetic outer rollback'):
            with self.database.request_transaction(self.context) as session:
                create_organization(session,self.context,'rolled-back-create',prepared)
                raise RuntimeError('synthetic outer rollback')
        self.assertEqual(self.counts(prepared.org_id),(0,)*9)
        self.assertFalse(self.create(prepared,key='rolled-back-create').replayed)
        self.assertEqual(self.counts(prepared.org_id),(1,1,1,1,1,1,1,2,1))

    def test_real_audit_failure_rolls_back_creation_even_if_outer_caller_catches(self):
        prepared=self.prepare()
        with connect() as owner:owner.execute("ALTER TABLE wpl.audit_events ADD CONSTRAINT fixture_reject_provisioning CHECK(action<>'organization_provisioned') NOT VALID")
        try:
            with self.database.request_transaction(self.context) as session:
                with self.assertRaises(DBAPIError) as error:create_organization(session,self.context,'failing-create',prepared)
                self.assertEqual(error.exception.orig.sqlstate,'23514')
                self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.organizations WHERE id=:org'),{'org':prepared.org_id}).scalar_one(),0)
        finally:
            with connect() as owner:owner.execute('ALTER TABLE wpl.audit_events DROP CONSTRAINT fixture_reject_provisioning')
        self.assertEqual(self.counts(prepared.org_id),(0,)*9)
        self.assertFalse(self.create(prepared,key='failing-create').replayed)

    def test_missing_capability_context_substitution_keys_and_direct_table_access_fail(self):
        prepared=self.prepare()
        ordinary=RequestContext(VerifiedIdentity(self.ordinary),RequestScope.PLATFORM)
        for context,candidate in ((ordinary,self.prepare(context=ordinary)),(ordinary,prepared)):
            with self.assertRaises(AuthorizationDenied):self.create(candidate,context=context)
        for key in ('','x'*129,'key with spaces'):
            with self.assertRaises(TenantConflict):self.create(prepared,key=key)
        with self.assertRaises(AuthorizationDenied):self.create(replace(prepared,actor_id=self.other))
        with self.assertRaises(DBAPIError):
            with self.database.request_transaction(self.context) as session:
                session.execute(text("INSERT INTO wpl.organizations(id,name,organization_type,contact_email,home_region,primary_admin_membership_id,provisioning_identity) VALUES (:org,'Denied','other','x@example.invalid','fixture',:member,'raw-bypass')"),{'org':prepared.org_id,'member':prepared.member_id})
        with self.database.request_transaction(self.context) as session:
            self.assertEqual(session.execute(text("SELECT count(*) FROM wpl.idempotency_records WHERE operation='create_organization'")).scalar_one(),0)
        self.assertEqual(self.counts(prepared.org_id),(0,)*9)

    def test_key_unavailability_and_invalid_request_shape_create_nothing(self):
        self.keys.blocked=True
        with self.assertRaises(PayloadKeyUnavailable):self.prepare()
        self.assertEqual(self.database.engine.pool.checkedout(),0)
        for change in ({'primary_admin_email':'invalid'},{'name':'   '},{'reason':'     '},{'actor_id':str(self.actor)}):
            with self.assertRaises(ValidationError):OrganizationCreate(**{**self.request.model_dump(),**change})
        self.keys.blocked=False
        with self.assertRaises(AuthorizationDenied):prepare_organization(RequestContext(VerifiedIdentity(self.actor),RequestScope.GLOBAL),self.request,self.cipher)
