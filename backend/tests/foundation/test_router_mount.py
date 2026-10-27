"""Actual shared-router mount, lifecycle and isolated legacy composition proof."""
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import httpx
from backend.app.foundation.app import create_app
from backend.app.foundation.mount import mount_foundation
from backend.app.foundation.settings import FoundationSettings,FoundationConfigurationError
from test_schema import connect
import test_http as http_fixtures


class RouterMountTests(unittest.TestCase):
    setUpClass=classmethod(http_fixtures.HTTPTests.setUpClass.__func__)
    token=http_fixtures.HTTPTests.token

    def setUp(self):
        self.subject=uuid4();self.events=[];self.calls=[]
        self.values={'WPL_FOUNDATION_ENABLED':'true','WPL_APPLICATION_DATABASE_URL':os.environ['WPL_APPLICATION_DATABASE_URL'],
            'WPL_AUTH_MODE':'jwt','WPL_AUTH_ISSUER':http_fixtures.ISSUER,'WPL_AUTH_AUDIENCE':'authenticated',
            'WPL_AUTH_JWKS_URL':http_fixtures.JWKS,'WPL_AUTH_ALGORITHMS':'ES256'}
        def provider(request):
            self.calls.append(request)
            self.assertEqual(str(request.url),http_fixtures.JWKS)
            return httpx.Response(200,json={'keys':[self.jwk]})
        self.transport=httpx.MockTransport(provider)

    def parent(self,*,fail_start=False,fail_stop=False):
        @asynccontextmanager
        async def lifespan(app):
            self.events.append('legacy_start')
            if fail_start:raise RuntimeError('Synthetic legacy startup failure')
            try:yield {'legacy_marker':'retained'}
            finally:
                self.events.append('legacy_stop')
                if fail_stop:raise RuntimeError('Synthetic legacy shutdown failure')
        app=FastAPI(lifespan=lifespan)
        @app.get('/health')
        def health():return {'status':'legacy-ok'}
        @app.post('/labs')
        def protected():raise HTTPException(401,'Legacy authentication required')
        return app

    def mount(self,app):
        child=mount_foundation(app,self.values,identity_transport=self.transport)
        # Cleanup remains safe even when a test intentionally never starts ASGI.
        self.addCleanup(child.state.foundation_verifier.close)
        self.addCleanup(child.state.foundation_database.close)
        return child

    def test_disabled_mount_ignores_new_configuration_and_changes_no_legacy_routes_or_state(self):
        app=self.parent();routes=list(app.routes);lifespan=app.router.lifespan_context
        with patch('backend.app.foundation.mount.create_app',side_effect=AssertionError('Disabled composition must not construct resources')):
            result=mount_foundation(app,{'WPL_FOUNDATION_ENABLED':'false','WPL_APPLICATION_DATABASE_URL':'not-a-dsn','WPL_AUTH_MODE':'invalid'})
            self.assertIsNone(result)
        self.assertEqual(app.routes,routes);self.assertIs(app.router.lifespan_context,lifespan)
        self.assertFalse(hasattr(app.state,'foundation_app'))
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json(),{'status':'legacy-ok'})
            self.assertEqual(client.get('/v1/me').status_code,404)
            denied=client.post('/labs');self.assertEqual(denied.status_code,401)
            self.assertEqual(denied.json(),{'detail':'Legacy authentication required'})
        self.assertEqual(self.calls,[])

    def test_enabled_mount_uses_same_signed_identity_pending_me_and_single_version_prefix(self):
        app=self.parent();child=self.mount(app)
        self.assertIs(app.state.foundation_app,child)
        self.assertFalse(hasattr(app.state,'foundation_database'))
        with TestClient(app) as client:
            response=client.get('/v1/me',headers={'Authorization':'Bearer '+self.token(self.subject,
                role='executive',user_metadata={'approved':True,'capabilities':['orgs']})})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['user']['global_state'],'pending')
            self.assertEqual(response.json()['capabilities'],[])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(client.get('/v1/me').json()['code'],'invalid_identity')
            for path in ('/v1/v1/me','/api/v1/me','/me'):
                self.assertEqual(client.get(path).status_code,404,path)
            self.assertEqual(client.get('/health').json(),{'status':'legacy-ok'})
        with connect() as owner:self.assertEqual(owner.execute('SELECT global_state FROM wpl.users WHERE id=%s',(self.subject,)).fetchone()[0],'pending')
        self.assertEqual(len(self.calls),1)

    def test_lifespans_verify_role_before_legacy_start_and_close_resources_after_legacy_stop(self):
        app=self.parent();child=self.mount(app);database=child.state.foundation_database;verifier=child.state.foundation_verifier
        verify=database.verify_runtime_role;db_close=database.close;http_close=verifier.close
        def checked():verify();self.events.append('foundation_verified')
        def closed_db():self.events.append('foundation_db_closed');db_close()
        def closed_http():self.events.append('foundation_http_closed');http_close()
        with patch.object(database,'verify_runtime_role',side_effect=checked),patch.object(database,'close',side_effect=closed_db),patch.object(verifier,'close',side_effect=closed_http):
            with TestClient(app) as client:
                self.assertEqual(client.app_state['legacy_marker'],'retained')
                self.assertEqual(client.get('/health').status_code,200)
        self.assertEqual(self.events,['foundation_verified','legacy_start','legacy_stop','foundation_db_closed','foundation_http_closed'])

    def test_role_check_failure_prevents_legacy_start_and_closes_both_foundation_resources(self):
        app=self.parent();child=self.mount(app);db=child.state.foundation_database;verifier=child.state.foundation_verifier
        with patch.object(db,'verify_runtime_role',side_effect=FoundationConfigurationError('Synthetic role failure')),patch.object(db,'close',wraps=db.close) as closed_db,patch.object(verifier,'close',wraps=verifier.close) as closed_http:
            with self.assertRaisesRegex(FoundationConfigurationError,'Synthetic role failure'):
                with TestClient(app):pass
            closed_db.assert_called_once();closed_http.assert_called_once()
        self.assertEqual(self.events,[])

    def test_legacy_start_failure_unwinds_verified_foundation_lifespan(self):
        app=self.parent(fail_start=True);child=self.mount(app);db=child.state.foundation_database;verifier=child.state.foundation_verifier
        with patch.object(db,'close',wraps=db.close) as closed_db,patch.object(verifier,'close',wraps=verifier.close) as closed_http:
            with self.assertRaisesRegex(RuntimeError,'Synthetic legacy startup failure'):
                with TestClient(app):pass
            closed_db.assert_called_once();closed_http.assert_called_once()
        self.assertEqual(self.events,['legacy_start'])

    def test_invalid_settings_prefix_and_duplicate_routes_fail_without_extra_resources(self):
        for values in ({'WPL_FOUNDATION_ENABLED':'maybe'}, {'WPL_FOUNDATION_ENABLED':'true'},
            {'WPL_FOUNDATION_ENABLED':'true','WPL_APPLICATION_DATABASE_URL':self.values['WPL_APPLICATION_DATABASE_URL']}):
            app=self.parent();before=list(app.routes)
            with self.assertRaises(FoundationConfigurationError) as error:mount_foundation(app,values)
            self.assertNotIn(self.values['WPL_APPLICATION_DATABASE_URL'],str(error.exception))
            self.assertEqual(app.routes,before)
        app=self.parent();self.mount(app)
        with patch('backend.app.foundation.mount.create_app',side_effect=AssertionError('Do not build twice')):
            with self.assertRaises(FoundationConfigurationError):mount_foundation(app,self.values)
        with patch('backend.app.foundation.app.build_verifier',side_effect=AssertionError('Reject prefix before resources')):
            with self.assertRaises(FoundationConfigurationError):create_app(FoundationSettings(),route_prefix='/api/v1')

    def test_parent_errors_cors_and_shutdown_failure_do_not_replace_or_leak_foundation(self):
        app=self.parent(fail_stop=True)
        app.add_middleware(CORSMiddleware,allow_origins=['https://page.example.invalid'],allow_methods=['*'],allow_headers=['*'])
        child=self.mount(app);db=child.state.foundation_database;verifier=child.state.foundation_verifier
        with patch.object(db,'close',wraps=db.close) as closed_db,patch.object(verifier,'close',wraps=verifier.close) as closed_http:
            with self.assertRaisesRegex(RuntimeError,'Synthetic legacy shutdown failure'):
                with TestClient(app) as client:
                    denied=client.post('/labs');self.assertEqual(denied.json(),{'detail':'Legacy authentication required'})
                    self.assertNotIn('X-Request-ID',denied.headers)
                    response=client.get('/v1/me',headers={'Origin':'https://page.example.invalid'})
                    self.assertEqual(response.status_code,401)
                    self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://page.example.invalid')
                    self.assertIn('X-Request-ID',response.headers)
                    self.assertEqual(client.get('/v1/me',headers={'Origin':'https://foreign.example.invalid'}).headers.get('Access-Control-Allow-Origin'),None)
            closed_db.assert_called_once();closed_http.assert_called_once()

    def test_actual_legacy_main_mounts_only_explicit_process_flag_and_keeps_legacy_contract(self):
        # Separate interpreters prevent legacy module globals/SQLite state from
        # entering the foundation suite. Docker, provider and dotenv access are
        # blocked/mocked; SQLite is a newly owned TemporaryDirectory fixture.
        code=r'''
import asyncio,json,os,tempfile,time
from contextlib import ExitStack
from unittest.mock import patch
from uuid import uuid4
import httpx,jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from fastapi.testclient import TestClient
from backend.app.foundation.app import create_app
import backend.app.foundation.mount as composition
scenario=os.environ['MOUNT_SCENARIO']
key=ec.generate_private_key(ec.SECP256R1());jwk=json.loads(ECAlgorithm.to_jwk(key.public_key()))
jwk.update(kid='synthetic-key',alg='ES256',use='sig')
calls=[]
def jwks(request):
    assert str(request.url)=='https://issuer.example.invalid/auth/v1/.well-known/jwks.json'
    calls.append(request)
    return httpx.Response(200,json={'keys':[jwk]})
def factory(settings,**kwargs):
    kwargs['identity_transport']=httpx.MockTransport(jwks)
    return create_app(settings,**kwargs)
def dotenv(*args,**kwargs):
    if scenario=='dotenv-only':os.environ['WPL_FOUNDATION_ENABLED']='true'
    return False
async def idle(self):await asyncio.Event().wait()
with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
    os.environ['WPL_PUBLIC_URL']='http://localhost:8080'
    os.environ['WPL_DATABASE_PATH']=directory+'/owned-legacy.db'
    os.environ['WPL_SECRET_KEY']='synthetic-signing-key-which-is-not-a-provider-secret'
    stack.enter_context(patch('dotenv.load_dotenv',side_effect=dotenv))
    stack.enter_context(patch('docker.from_env'))
    stack.enter_context(patch('requests.get',side_effect=AssertionError('No legacy provider request permitted')))
    stack.enter_context(patch.object(composition,'create_app',side_effect=factory))
    from backend.app.main import app
    stack.enter_context(patch('backend.app.services.inactivity_service.InactivityService.run_forever',idle))
    assert hasattr(app.state,'foundation_app')==(scenario=='enabled')
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.post('/labs').status_code==401
        assert client.get('/gui/proxy-auth').status_code==403
        cors=client.options('/labs',headers={'Origin':'http://localhost:8080','Access-Control-Request-Method':'POST'})
        assert cors.headers['access-control-allow-origin']=='http://localhost:8080'
        if scenario=='enabled':
            now=int(time.time());subject=str(uuid4())
            token=jwt.encode({'sub':subject,'session_id':str(uuid4()),'iss':'https://issuer.example.invalid/auth/v1',
                'aud':'authenticated','iat':now,'exp':now+300},key,algorithm='ES256',headers={'kid':'synthetic-key'})
            response=client.get('/v1/me',headers={'Authorization':'Bearer '+token})
            assert response.status_code==200,response.text
            assert response.json()['user']['global_state']=='pending'
            assert client.get('/v1/v1/me').status_code==404
        else:assert client.get('/v1/me').status_code==404
    from backend.app.db.database import engine
    assert engine.url.drivername=='sqlite'
    assert engine.url.database==directory+'/owned-legacy.db'
    engine.dispose()
assert len(calls)==int(scenario=='enabled')
print('Actual legacy composition passed: '+scenario+'; synthetic Docker/provider/SQLite boundary retained.')
'''
        root=Path(__file__).resolve().parents[3]
        for scenario in ('disabled','dotenv-only','enabled'):
            env=dict(os.environ);env.update(self.values);env.update(MOUNT_SCENARIO=scenario,PYTHONDONTWRITEBYTECODE='1')
            env.pop('WPL_API_BASE_URL',None);env.pop('WPL_GUI_BASE_URL',None)
            if scenario=='disabled':env.update(WPL_FOUNDATION_ENABLED='false',WPL_APPLICATION_DATABASE_URL='invalid-disabled-url',WPL_AUTH_MODE='invalid-disabled-mode')
            if scenario=='dotenv-only':env.pop('WPL_FOUNDATION_ENABLED')
            result=subprocess.run([sys.executable,'-c',code],env=env,cwd=root,capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Actual legacy composition passed: '+scenario,result.stdout)
        print('Actual legacy main: explicit enabled mount, default/explicit off and dotenv-only nonactivation; legacy health/auth/CORS/SQLite retained.',flush=True)
