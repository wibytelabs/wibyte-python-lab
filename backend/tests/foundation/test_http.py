"""HTTP -> actual signature verification -> typed context -> real-runtime RLS."""
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from uuid import UUID,uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import httpx
import jwt
from jwt.algorithms import ECAlgorithm
from sqlalchemy.exc import OperationalError

from backend.app.domains.identity.settings import IdentitySettings
from backend.app.foundation.app import create_app
from backend.app.foundation.settings import FoundationSettings,FoundationConfigurationError,postgres_url
from backend.app.foundation.migrate import migrate
from test_schema import connect,seed_org
from test_guards import add_member

ISSUER='https://issuer.example.invalid/auth/v1'
JWKS=ISSUER+'/.well-known/jwks.json'


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        cls.key=ec.generate_private_key(ec.SECP256R1())
        cls.jwk=json.loads(ECAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update({'kid':'synthetic-key','alg':'ES256','use':'sig'})

    def setUp(self):
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':
            raise RuntimeError('Refusing non-fixture HTTP target.')
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.teacher,self.teacher_member=add_member(owner,self.a['org'],('instructor',))
            self.student,self.student_member=add_member(owner,self.a['org'],('student',))
            self.extra=uuid4()
            owner.execute("INSERT INTO wpl.cohorts(id,org_id,name,slug) VALUES (%s,%s,'Pending class',%s)",
                          (self.extra,self.a['org'],'fixture-'+uuid4().hex))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(self.a['org'],self.a['cohort'],self.teacher_member))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'student','active')",(self.a['org'],self.a['cohort'],self.student_member))
            # Keep another eligible instructor while testing teacher suspension.
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'instructor')",(self.a['org'],self.a['member']))
            owner.execute("INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status) VALUES (%s,%s,%s,'instructor','active')",(self.a['org'],self.a['cohort'],self.a['member']))
            for fixture in (self.a,self.b):
                owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            owner.execute("UPDATE wpl.cohorts SET status='active' WHERE id=%s",(self.a['cohort'],))
        self.provider_calls=[]
        def handler(request):
            self.provider_calls.append(request)
            self.assertEqual(str(request.url),JWKS)
            return httpx.Response(200,json={'keys':[self.jwk]})
        settings=FoundationSettings(enabled=True,application_database_url=url,pool_size=1)
        self.app=create_app(settings,identity_settings=IdentitySettings(mode='jwt',issuer=ISSUER,
            audience='authenticated',jwks_url=JWKS,algorithms=('ES256',)),identity_transport=httpx.MockTransport(handler))
        self.client=self.enterContext(TestClient(self.app,raise_server_exceptions=False))

    def token(self,subject,**extra):
        now=int(time.time())
        claims={'sub':str(subject),'session_id':str(uuid4()),'iss':ISSUER,'aud':'authenticated','iat':now,'exp':now+300}
        claims.update(extra)
        return jwt.encode(claims,self.key,algorithm='ES256',headers={'kid':'synthetic-key'})

    def get(self,path,subject=None,**kwargs):
        headers=kwargs.pop('headers',{})
        if subject is not None: headers['Authorization']='Bearer '+self.token(subject)
        return self.client.get(path,headers=headers,**kwargs)

    def assert_error(self,response,status,code):
        self.assertEqual(response.status_code,status,response.text)
        body=response.json()
        self.assertEqual(body['code'],code)
        self.assertEqual(response.headers['X-Request-ID'],body['request_id'])
        self.assertEqual(len(body['request_id']),32)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertNotIn('input',body)
        return body

    def test_pending_new_identity_gets_persisted_own_me_without_approval_or_email_mapping(self):
        subject=uuid4()
        token=self.token(subject,email='synthetic@example.invalid',email_verified=True,
                         role='executive',user_metadata={'capabilities':['orgs'],'approved':True})
        headers={'Authorization':'Bearer '+token}
        first=self.client.get('/v1/me',headers=headers)
        self.assertEqual(first.status_code,200,first.text)
        second=self.client.get('/v1/me',headers=headers)
        self.assertEqual(second.json(),first.json())
        body=first.json()
        self.assertEqual(body['user']['id'],str(subject))
        self.assertEqual(body['user']['global_state'],'pending')
        self.assertEqual(body['capabilities'],[])
        self.assertEqual(body['memberships'],{'items':[],'next_cursor':None})
        self.assertNotIn('session_id',body)
        self.assertNotIn('synthetic@example.invalid',first.text)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT global_state,verified_email FROM wpl.users WHERE id=%s',(subject,)).fetchone(),('pending',None))
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.platform_roles WHERE user_id=%s',(subject,)).fetchone()[0],0)
        self.assertEqual(len(self.provider_calls),1)
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}",subject),404,'not_found')

    def test_missing_malformed_invalid_and_expired_identity_rejected_without_mirror(self):
        for headers in ({},{'X-Actor-ID':str(self.a['user'])}, {'Authorization':'Basic synthetic'},
                        {'Authorization':'Bearer bad token'}, {'Authorization':'Bearer invalid'}):
            self.assert_error(self.client.get('/v1/me',headers=headers),401,'invalid_identity')
        subject=uuid4()
        expired=self.token(subject,exp=int(time.time())-120)
        self.assert_error(self.client.get('/v1/me',headers={'Authorization':'Bearer '+expired}),401,'invalid_identity')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.users WHERE id=%s',(subject,)).fetchone()[0],0)

    def test_provider_outage_is_sanitized_503_without_database_identity_creation(self):
        subject=uuid4()
        def unavailable(request):
            raise httpx.ReadTimeout('synthetic-secret-provider-detail',request=request)
        app=create_app(FoundationSettings(enabled=True,application_database_url=self.app.state.foundation_database.engine.url),
            identity_settings=IdentitySettings(mode='jwt',issuer=ISSUER,audience='authenticated',jwks_url=JWKS,algorithms=('ES256',)),
            identity_transport=httpx.MockTransport(unavailable))
        with TestClient(app,raise_server_exceptions=False) as client:
            response=client.get('/v1/me',headers={'Authorization':'Bearer '+self.token(subject)})
        self.assert_error(response,503,'identity_unavailable')
        self.assertNotIn('synthetic-secret',response.text)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.users WHERE id=%s',(subject,)).fetchone()[0],0)

    def test_org_authority_masks_private_fields_and_ignores_spoofed_actor_headers(self):
        admin=self.get(f"/v1/orgs/{self.a['org']}",self.a['user'])
        self.assertEqual(admin.status_code,200,admin.text)
        self.assertIn('contact_email',admin.json())
        student=self.get(f"/v1/orgs/{self.a['org']}",self.student,
                         headers={'X-Actor-ID':str(self.a['user']),'X-Role':'admin','X-Org-ID':str(self.b['org'])})
        self.assertEqual(student.status_code,200,student.text)
        self.assertNotIn('contact_email',student.json())
        self.assertNotIn('primary_admin_membership_id',student.json())
        self.assert_error(self.get(f"/v1/orgs/{self.b['org']}",self.a['user']),404,'not_found')
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}/members",self.student,
                                  headers={'X-Actor-ID':str(self.a['user'])}),403,'forbidden')

    def test_cohort_http_matrix_matches_production_rls(self):
        for subject,expected in ((self.a['user'],{self.a['cohort'],self.extra}),
                                 (self.teacher,{self.a['cohort']}),(self.student,{self.a['cohort']})):
            response=self.get(f"/v1/orgs/{self.a['org']}/cohorts",subject)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual({UUID(item['id']) for item in response.json()['items']},expected)
        self.assert_error(self.get(f"/v1/orgs/{self.b['org']}/cohorts",self.teacher),404,'not_found')

    def test_members_pagination_is_bounded_stable_and_org_scoped(self):
        path=f"/v1/orgs/{self.a['org']}/members"
        seen=[];cursor=None
        for _ in range(5):
            response=self.get(path,self.a['user'],params={'limit':1,**({'cursor':cursor} if cursor else {})})
            self.assertEqual(response.status_code,200,response.text)
            body=response.json()
            seen.extend(item['id'] for item in body['items'])
            self.assertTrue(all('verified_email' not in item for item in body['items']))
            cursor=body['next_cursor']
            if cursor is None: break
        self.assertIsNone(cursor)
        self.assertEqual(set(seen),{str(self.a['member']),str(self.teacher_member),str(self.student_member)})
        self.assertEqual(len(seen),len(set(seen)))
        for params,status,code in (({'limit':101},422,'validation_error'),({'cursor':'not-a-cursor'},400,'invalid_cursor'),
                                   ({'cursor':'x'*513},422,'validation_error')):
            self.assert_error(self.get(path,self.a['user'],params=params),status,code)
        self.assert_error(self.get('/v1/orgs/not-a-uuid/members',self.a['user']),422,'validation_error')

    def test_current_member_and_global_suspension_block_cached_token_requests(self):
        path=f"/v1/orgs/{self.a['org']}/cohorts"
        headers={'Authorization':'Bearer '+self.token(self.teacher)}
        self.assertEqual(self.client.get(path,headers=headers).status_code,200)
        with connect() as owner:
            owner.execute("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(self.teacher_member,))
        self.assert_error(self.client.get(path,headers=headers),404,'not_found')
        with connect() as owner:
            owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.teacher_member,))
            owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.teacher,))
        self.assert_error(self.client.get(path,headers=headers),404,'not_found')
        own=self.client.get('/v1/me',headers=headers)
        self.assertEqual(own.status_code,200,own.text)
        self.assertEqual(own.json()['user']['global_state'],'suspended')
        self.assertEqual(own.json()['capabilities'],[])
        self.assertTrue(all(not item['can_enter'] for item in own.json()['memberships']['items']))

    def test_request_errors_release_pool_and_never_return_database_details(self):
        database=self.app.state.foundation_database
        with patch.object(database,'request_transaction',side_effect=OperationalError('SELECT synthetic-secret',{},RuntimeError('private-dsn-marker'))):
            response=self.get('/v1/me',self.a['user'])
        self.assert_error(response,503,'data_unavailable')
        self.assertNotIn('synthetic-secret',response.text)
        self.assertNotIn('private-dsn-marker',response.text)
        for _ in range(2):
            self.assert_error(self.get(f"/v1/orgs/{self.b['org']}",self.a['user']),404,'not_found')
            self.assertEqual(self.get(f"/v1/orgs/{self.a['org']}",self.a['user']).status_code,200)
        self.assertEqual(database.engine.pool.checkedout(),0)
        with database.transaction() as session:
            from sqlalchemy import text
            row=session.execute(text("SELECT current_setting('wpl.actor_id',true),current_setting('wpl.org_id',true)")).one()
            self.assertTrue(all(value in (None,'') for value in row))

    def test_feature_off_has_no_identity_requirement_or_versioned_routes(self):
        app=create_app(FoundationSettings())
        with TestClient(app,raise_server_exceptions=False) as client:
            self.assert_error(client.get('/v1/me'),404,'not_found')
        self.assertIsNone(app.state.foundation_database)
        self.assertIsNone(app.state.foundation_verifier)
        with self.assertRaises(FoundationConfigurationError):
            create_app(FoundationSettings(enabled=True,application_database_url=self.app.state.foundation_database.engine.url))

    def test_internal_prefix_and_separate_public_proxy_contract(self):
        self.assertEqual(self.get('/v1/me',self.a['user']).status_code,200)
        self.assert_error(self.get('/api/v1/me',self.a['user']),404,'not_found')
        source=Path('/app/deploy/nginx.conf.template').read_text()
        self.assertIn('location /api/',source)
        self.assertIn('proxy_pass http://127.0.0.1:8000/;',source)
        # Source mapping only: no real reverse proxy/browser smoke is claimed.
        self.assertEqual('/api/v1/me'.removeprefix('/api'),'/v1/me')
