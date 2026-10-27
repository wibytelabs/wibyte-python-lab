"""HTTP create -> real synthetic JWT -> runtime transaction, no identity bypass."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import event
from backend.app.domains.identity.settings import IdentitySettings
from backend.app.domains.jobs.payloads import PayloadCipher
from backend.app.foundation.app import create_app
from backend.app.foundation.settings import FoundationSettings,FoundationConfigurationError
from test_schema import connect
import test_http as http_fixtures
import test_http_platform as platform_fixtures


class HTTPKeys:
    def __init__(self):
        self.key=AESGCM.generate_key(bit_length=256);self.calls=0
        self.local=threading.local();self.lock=threading.Lock();self.fail=False;self.before_resolve=None
    def current_reference(self):return 'fixture/http-provisioning-key'
    def resolve(self,reference):
        if getattr(self.local,'checkouts',0)!=0:raise RuntimeError('Key resolution inside request DB checkout')
        with self.lock:self.calls+=1
        if self.before_resolve:self.before_resolve()
        if self.fail:raise RuntimeError('Synthetic private provider detail must never escape')
        if reference!=self.current_reference():raise KeyError
        return self.key


class HTTPProvisioningTests(unittest.TestCase):
    setUpClass=classmethod(platform_fixtures.PlatformHTTPTests.setUpClass.__func__)
    token=platform_fixtures.PlatformHTTPTests.token
    get=platform_fixtures.PlatformHTTPTests.get
    assert_error=platform_fixtures.PlatformHTTPTests.assert_error

    def setUp(self):
        platform_fixtures.PlatformHTTPTests.setUp(self)
        self.url=self.database.engine.url
        self.keys=HTTPKeys()
        self.app=self.make_app(PayloadCipher(self.keys))
        self.database=self.app.state.foundation_database
        def checkout(connection,record,proxy):self.keys.local.checkouts=getattr(self.keys.local,'checkouts',0)+1
        def checkin(connection,record):self.keys.local.checkouts=getattr(self.keys.local,'checkouts',0)-1
        event.listen(self.database.engine,'checkout',checkout);event.listen(self.database.engine,'checkin',checkin)
        self.client=self.enterContext(TestClient(self.app,raise_server_exceptions=False))
        self.body={'name':'Create-'+uuid4().hex,'organization_type':'school','contact_email':'contact@example.invalid',
            'primary_admin_email':'primary@example.invalid','home_region':'fixture','reason':'Explicit synthetic HTTP provisioning'}
        self.request_key='http-create-'+uuid4().hex

    def make_app(self,cipher):
        def handler(request):
            self.assertEqual(str(request.url),http_fixtures.JWKS)
            return httpx.Response(200,json={'keys':[self.jwk]})
        return create_app(FoundationSettings(enabled=True,application_database_url=self.url,pool_size=2),
            identity_settings=IdentitySettings(mode='jwt',issuer=http_fixtures.ISSUER,audience='authenticated',
                jwks_url=http_fixtures.JWKS,algorithms=('ES256',)),identity_transport=httpx.MockTransport(handler),payload_cipher=cipher)

    def post(self,body=None,*,key=None,subject=None,client=None):
        return (client or self.client).post('/v1/platform/organizations',json=self.body if body is None else body,
            headers={'Authorization':'Bearer '+self.token(subject or self.executive),'Idempotency-Key':key or self.request_key})

    def count(self):
        with connect() as owner:return owner.execute('SELECT count(*) FROM wpl.organizations WHERE name=%s',(self.body['name'],)).fetchone()[0]

    def test_create_returns_committed_pending_receipt_detail_and_redacted_platform_job(self):
        response=self.post();self.assertEqual(response.status_code,201,response.text)
        receipt=response.json();self.assertEqual(response.headers['Idempotency-Replayed'],'false')
        self.assertEqual(set(receipt),{'org_id','status','primary_admin_membership_id','invitation_status','job_id','delivery_status','version'})
        self.assertEqual((receipt['status'],receipt['invitation_status'],receipt['delivery_status']),('pending','pending','pending_integration'))
        self.assertEqual(self.count(),1)
        detail=self.get('/v1/platform/organizations/'+receipt['org_id'],self.executive)
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['primary_admin_membership_id'],receipt['primary_admin_membership_id'])
        job=self.get('/v1/platform/organizations/'+receipt['org_id']+'/jobs/'+receipt['job_id'],self.executive)
        self.assertEqual(job.status_code,200,job.text)
        self.assertEqual((job.json()['kind'],job.json()['state'],job.json()['delivery_status']),('deliver_primary_invitation','queued','pending_integration'))
        for marker in ('activation_token','token_digest','ciphertext','private_payload','key_reference','intent_hash','lease_owner','primary@example.invalid'):
            self.assertNotIn(marker,response.text+job.text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.database.engine.pool.checkedout(),0)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT user_id,status FROM wpl.organization_memberships WHERE id=%s',(receipt['primary_admin_membership_id'],)).fetchone(),(None,'invite_pending'))
        print('HTTP 201 actual-runtime create committed pending designation and queued encrypted intent; no activation or delivery claimed.',flush=True)

    def test_saved_receipt_replays_without_keys_and_changed_body_conflicts_before_key_io(self):
        first=self.post();self.assertEqual(first.status_code,201,first.text);calls=self.keys.calls
        self.keys.fail=True
        replay=self.post();self.assertEqual(replay.status_code,201,replay.text)
        self.assertEqual(replay.json(),first.json());self.assertEqual(replay.headers['Idempotency-Replayed'],'true')
        self.assertEqual(self.keys.calls,calls)
        self.assert_error(self.post({**self.body,'name':'Changed request body'}),409,'idempotency_conflict')
        self.assertEqual(self.keys.calls,calls)
        with TestClient(self.make_app(None),raise_server_exceptions=False) as restarted:
            replay=self.post(client=restarted)
            self.assertEqual(replay.status_code,201,replay.text);self.assertEqual(replay.json(),first.json())
            self.assert_error(self.post(key='new-operation',client=restarted),503,'delivery_unavailable')
        self.assertEqual(self.count(),1)

    def test_concurrent_signed_http_requests_return_one_org_and_same_public_receipt(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.post) for _ in range(2)]
            responses=[future.result(timeout=20) for future in futures]
        self.assertTrue(all(response.status_code==201 for response in responses),[response.text for response in responses])
        self.assertEqual(responses[0].json(),responses[1].json())
        self.assertCountEqual([response.headers['Idempotency-Replayed'] for response in responses],['false','true'])
        self.assertEqual(self.count(),1)
        receipt=responses[0].json()
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.invitations WHERE org_id=%s',(receipt['org_id'],)).fetchone()[0],1)
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.jobs WHERE org_id=%s',(receipt['org_id'],)).fetchone()[0],1)
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.outbox WHERE job_id=%s',(receipt['job_id'],)).fetchone()[0],1)

    def test_missing_invalid_key_body_or_current_capability_creates_nothing(self):
        path='/v1/platform/organizations'
        self.assert_error(self.client.post(path,json=self.body,headers={'Idempotency-Key':self.request_key}),401,'invalid_identity')
        for subject in (self.student,self.a['user'],self.observer,self.pending):self.assert_error(self.post(subject=subject),403,'forbidden')
        headers={'Authorization':'Bearer '+self.token(self.executive)}
        self.assert_error(self.client.post(path,json=self.body,headers=headers),422,'validation_error')
        for key in ('bad key','x'*129):
            self.assert_error(self.client.post(path,json=self.body,headers={**headers,'Idempotency-Key':key}),422,'validation_error')
        self.assert_error(self.post({**self.body,'actor_id':str(self.executive)}),422,'validation_error')
        self.assert_error(self.post({**self.body,'primary_admin_email':'invalid'}),422,'validation_error')
        self.assertEqual(self.keys.calls,0);self.assertEqual(self.count(),0)

    def test_key_outage_is_sanitized_and_new_create_without_configuration_is_not_success(self):
        self.keys.fail=True
        response=self.post();self.assert_error(response,503,'delivery_unavailable')
        self.assertNotIn('Synthetic private',response.text)
        self.assertNotIn(self.body['primary_admin_email'],response.text)
        self.assertEqual(self.count(),0)
        with TestClient(self.make_app(None),raise_server_exceptions=False) as client:
            self.assert_error(self.post(client=client),503,'delivery_unavailable')
        self.assertEqual(self.count(),0)

    def test_capability_revoked_during_key_io_and_before_replay_cannot_create_or_replay(self):
        def revoke():
            with connect() as owner:owner.execute('DELETE FROM wpl.platform_roles WHERE user_id=%s',(self.executive,))
        self.keys.before_resolve=revoke
        self.assert_error(self.post(),403,'forbidden');self.assertEqual(self.count(),0)
        self.keys.before_resolve=None
        with connect() as owner:owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Explicit synthetic restore')",(self.executive,))
        self.assertEqual(self.post().status_code,201)
        calls=self.keys.calls;revoke()
        self.assert_error(self.post(),403,'forbidden')
        self.assertEqual(self.keys.calls,calls);self.assertEqual(self.count(),1)

    def test_initial_job_requires_explicit_platform_target_and_does_not_grant_tenant_access(self):
        response=self.post();self.assertEqual(response.status_code,201,response.text)
        receipt=response.json();path='/v1/platform/organizations/'+receipt['org_id']+'/jobs/'+receipt['job_id']
        for subject in (self.student,self.a['user'],self.observer,self.pending):
            self.assert_error(self.get(path,subject,headers={'X-Actor-ID':str(self.executive)}),403,'forbidden')
        self.assert_error(self.get('/v1/platform/organizations/'+str(self.a['org'])+'/jobs/'+receipt['job_id'],self.executive),404,'not_found')
        self.assert_error(self.get('/v1/platform/organizations/'+receipt['org_id']+'/jobs/'+str(uuid4()),self.executive),404,'not_found')
        self.assert_error(self.get('/v1/orgs/'+receipt['org_id']+'/members',self.executive),404,'not_found')
        self.assert_error(self.get('/v1/orgs/'+receipt['org_id']+'/jobs/'+receipt['job_id'],self.executive),404,'not_found')

    def test_disabled_factory_mounts_no_create_route_and_rejects_invalid_cipher_resource(self):
        with TestClient(create_app(FoundationSettings()),raise_server_exceptions=False) as client:
            self.assert_error(client.post('/v1/platform/organizations',json=self.body),404,'not_found')
        with self.assertRaises(FoundationConfigurationError):
            create_app(FoundationSettings(),payload_cipher=object())
        self.assertEqual(self.count(),0)
