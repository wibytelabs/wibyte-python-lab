"""Real asymmetric signatures with synthetic JWKS/provider transports, no providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import json
import time
import unittest
from uuid import uuid4
import httpx
import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from backend.app.foundation.settings import FoundationConfigurationError
from backend.app.domains.identity.settings import IdentitySettings
from backend.app.domains.identity.verification import build_verifier, InvalidIdentity, IdentityUnavailable

ISSUER='https://issuer.example.invalid/auth/v1'
JWKS='https://issuer.example.invalid/auth/v1/.well-known/jwks.json'


class FakeClock:
    def __init__(self): self.value=1000.0
    def __call__(self): return self.value
    def advance(self,value): self.value+=value


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ec1=ec.generate_private_key(ec.SECP256R1())
        cls.ec2=ec.generate_private_key(ec.SECP256R1())
        cls.rsa1=rsa.generate_private_key(public_exponent=65537,key_size=2048)

    def setUp(self):
        self.subject=uuid4()
        self.clock=FakeClock()

    def claims(self):
        now=int(time.time())
        return {'sub':str(self.subject),'session_id':str(uuid4()),'iss':ISSUER,'aud':'authenticated',
                'iat':now,'exp':now+600,'auth_time':now,'email':'fixture@example.invalid','email_verified':True}

    def token(self,claims=None,*,key=None,kid='key-1',algorithm='ES256',headers=None):
        key=self.ec1 if key is None else key
        return jwt.encode(self.claims() if claims is None else claims,key,algorithm=algorithm,
                          headers={'kid':kid,**(headers or {})})

    def jwk(self,key=None,kid='key-1',algorithm='ES256'):
        key=self.ec1 if key is None else key
        public=key.public_key()
        data=json.loads((ECAlgorithm if algorithm=='ES256' else RSAAlgorithm).to_jwk(public))
        return {**data,'kid':kid,'alg':algorithm,'use':'sig','key_ops':['verify']}

    def setup_verifier(self,*,mode='jwt',payload=None,algorithms=('ES256',)):
        settings=IdentitySettings(mode='jwt',issuer=ISSUER,audience='authenticated',jwks_url=JWKS,
            algorithms=algorithms,cache_seconds=30,refresh_seconds=2,leeway_seconds=5) if mode=='jwt' else IdentitySettings(
                provider_url='https://provider.example.invalid',publishable_key='synthetic-public')
        state={'status':200,'payload':({'keys':[self.jwk()]} if payload is None else payload)}
        calls=[]
        def handler(request):
            calls.append(request)
            if 'error' in state: raise state['error']
            if 'response' in state: return state['response']
            return httpx.Response(state['status'],json=state['payload'])
        verifier=build_verifier(settings,transport=httpx.MockTransport(handler),monotonic=self.clock)
        self.addCleanup(verifier.close)
        return verifier,state,calls

    def test_explicit_configuration_has_no_hs_fallback_or_environment_defaults(self):
        with self.assertRaises(FoundationConfigurationError): IdentitySettings.from_mapping({})
        for mode in ('none','debug','hs256'):
            with self.subTest(mode=mode),self.assertRaises(FoundationConfigurationError): IdentitySettings(mode=mode)
        for algorithms in ((),('HS256',),('none',),('ES256','ES256')):
            with self.subTest(algorithms=algorithms),self.assertRaises(FoundationConfigurationError):
                IdentitySettings(mode='jwt',issuer=ISSUER,audience='authenticated',jwks_url=JWKS,algorithms=algorithms)
        configured=IdentitySettings.from_mapping({'WPL_AUTH_PROVIDER_URL':'https://provider.example.invalid','WPL_AUTH_PUBLISHABLE_KEY':'synthetic-secret-marker'})
        self.assertEqual(configured.mode,'provider_user')
        self.assertNotIn('synthetic-secret-marker',repr(configured))

    def test_configuration_rejects_untrusted_urls_and_invalid_bounds(self):
        for url in ('http://remote.example.invalid','//other.invalid','https://user:secret@example.invalid',
                    'https://example.invalid#fragment','https://example.invalid?token=secret','https://example.invalid:0'):
            with self.subTest(url=url),self.assertRaises(FoundationConfigurationError) as caught:
                IdentitySettings(provider_url=url,publishable_key='synthetic-public')
            self.assertNotIn('secret',str(caught.exception))
        with self.assertRaises(FoundationConfigurationError):
            IdentitySettings(provider_url='https://provider.example.invalid',publishable_key='synthetic',cache_seconds=10000)

    def test_real_es256_and_rs256_round_trips_return_identity_only(self):
        for algorithm,key in (('ES256',self.ec1),('RS256',self.rsa1)):
            with self.subTest(algorithm=algorithm):
                verifier,_,calls=self.setup_verifier(payload={'keys':[self.jwk(key,algorithm=algorithm)]},algorithms=(algorithm,))
                identity=verifier.verify(self.token(key=key,algorithm=algorithm))
                self.assertEqual(identity.subject,self.subject)
                self.assertIsNotNone(identity.authenticated_at)
                self.assertEqual(identity.verified_email,'fixture@example.invalid')
                self.assertEqual(len(calls),1)
                self.assertEqual(str(calls[0].url),JWKS)

    def test_user_metadata_and_jwt_role_never_grant_capabilities(self):
        verifier,_,_=self.setup_verifier()
        claims=self.claims()
        claims.update({'role':'executive','user_metadata':{'admin':True,'capabilities':['orgs']},'email_verified':'true'})
        claims.pop('auth_time')
        identity=verifier.verify(self.token(claims))
        self.assertEqual(identity.subject,self.subject)
        self.assertIsNone(identity.verified_email)
        self.assertIsNone(identity.authenticated_at)
        self.assertFalse(hasattr(identity,'roles'))
        self.assertFalse(hasattr(identity,'capabilities'))

    def test_signature_and_standard_claim_failures_are_rejected(self):
        verifier,_,_=self.setup_verifier()
        self.assertEqual(verifier.verify(self.token()).subject,self.subject)
        with self.assertRaises(InvalidIdentity): verifier.verify(self.token(key=self.ec2))
        for field,value in (('iss','https://evil.example.invalid'),('aud','other-audience'),('exp',int(time.time())-60),
            ('iat',int(time.time())+120),('nbf',int(time.time())+120),('sub','not-a-uuid'),('session_id','not-a-uuid')):
            with self.subTest(field=field),self.assertRaises(InvalidIdentity):
                claims=self.claims();claims[field]=value
                verifier.verify(self.token(claims))

    def test_missing_required_claims_are_rejected(self):
        verifier,_,_=self.setup_verifier()
        for field in ('sub','iss','aud','exp','iat','session_id'):
            with self.subTest(field=field),self.assertRaises(InvalidIdentity):
                claims=self.claims();claims.pop(field)
                verifier.verify(self.token(claims))

    def test_numeric_types_and_recent_auth_claim_cannot_be_coerced(self):
        verifier,_,_=self.setup_verifier()
        for field,value in (('iat',True),('iat',str(int(time.time()))),('exp',str(int(time.time())+600)),
            ('nbf',str(int(time.time()))),('auth_time',True),('auth_time',-1),('auth_time',int(time.time())+120)):
            with self.subTest(field=field,value=value),self.assertRaises(InvalidIdentity):
                claims=self.claims();claims[field]=value
                verifier.verify(self.token(claims))

    def test_embedded_key_urls_and_critical_extensions_never_fetch(self):
        verifier,_,calls=self.setup_verifier()
        for header in ({'jku':'https://evil.invalid/keys'},{'x5u':'https://evil.invalid/cert'},
                       {'jwk':self.jwk()},{'crit':['unknown']},{'b64':False},{'typ':'unsupported'}):
            with self.subTest(header=list(header)),self.assertRaises(InvalidIdentity):
                verifier.verify(self.token(headers=header))
        self.assertEqual(calls,[])

    def test_unsupported_algorithms_and_missing_kid_never_fetch(self):
        verifier,_,calls=self.setup_verifier()
        bad_tokens=[self.token(key=self.rsa1,algorithm='RS256'),
                    jwt.encode(self.claims(),'synthetic-hmac-key-'*4,algorithm='HS256',headers={'kid':'key-1'}),
                    jwt.encode(self.claims(),key=None,algorithm='none',headers={'kid':'key-1'}),
                    jwt.encode(self.claims(),self.ec1,algorithm='ES256')]
        for token in bad_tokens:
            with self.assertRaises(InvalidIdentity): verifier.verify(token)
        self.assertEqual(calls,[])

    def test_unknown_kid_refreshes_are_rate_bounded(self):
        verifier,_,calls=self.setup_verifier()
        for index in range(10):
            with self.assertRaises(InvalidIdentity): verifier.verify(self.token(kid='unknown-'+str(index)))
        self.assertEqual(len(calls),1)
        self.clock.advance(2.1)
        with self.assertRaises(InvalidIdentity): verifier.verify(self.token(kid='still-unknown'))
        self.assertEqual(len(calls),2)

    def test_synthetic_rotation_refreshes_once_after_cooldown(self):
        verifier,state,calls=self.setup_verifier()
        verifier.verify(self.token())
        state['payload']={'keys':[self.jwk(),self.jwk(self.ec2,'key-2')]}
        with self.assertRaises(InvalidIdentity): verifier.verify(self.token(key=self.ec2,kid='key-2'))
        self.clock.advance(2.1)
        self.assertEqual(verifier.verify(self.token(key=self.ec2,kid='key-2')).subject,self.subject)
        verifier.verify(self.token())
        self.assertEqual(len(calls),2)

    def test_concurrent_cold_cache_fetch_is_shared(self):
        verifier,_,calls=self.setup_verifier()
        token=self.token()
        with ThreadPoolExecutor(max_workers=6) as pool:
            identities=list(pool.map(verifier.verify,[token]*6))
        self.assertTrue(all(identity.subject==self.subject for identity in identities))
        self.assertEqual(len(calls),1)

    def test_outage_uses_only_fresh_cache_and_stale_cache_fails_closed(self):
        verifier,state,calls=self.setup_verifier()
        token=self.token()
        verifier.verify(token)
        state['status']=503
        self.assertEqual(verifier.verify(token).subject,self.subject)
        self.assertEqual(len(calls),1)
        self.clock.advance(31)
        for _ in range(5):
            with self.assertRaises(IdentityUnavailable): verifier.verify(token)
        self.assertEqual(len(calls),2)

    def test_timeout_error_does_not_echo_token_or_provider_details(self):
        verifier,state,_=self.setup_verifier()
        state['error']=httpx.ReadTimeout('synthetic-secret-provider-error')
        with self.assertRaises(IdentityUnavailable) as caught: verifier.verify(self.token())
        self.assertNotIn('synthetic-secret',str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_malformed_duplicate_private_or_wrong_family_jwks_fail_closed(self):
        valid=self.jwk()
        for payload in ({'keys':[]},{'keys':'invalid'},{'keys':[valid,valid]},
            {'keys':[{**valid,'d':'private'}]},{'keys':[{**valid,'kty':'RSA'}]},
            {'keys':[{**valid,'use':'enc'}]},{'keys':[{**valid,'key_ops':['sign','verify']}]},
            {'keys':[valid]*33}):
            with self.subTest(shape=str(list(payload))),self.assertRaises(IdentityUnavailable):
                verifier,_,_=self.setup_verifier(payload=payload)
                verifier.verify(self.token())

    def test_oversized_compressed_and_redirect_responses_are_rejected(self):
        for response in (httpx.Response(200,content=b' '*131073,headers={'Content-Type':'application/json'}),
            httpx.Response(200,content=gzip.compress(b'{}'),headers={'Content-Type':'application/json','Content-Encoding':'gzip'}),
            httpx.Response(302,headers={'Location':'https://evil.example.invalid/keys'})):
            with self.subTest(status=response.status_code),self.assertRaises(IdentityUnavailable):
                verifier,state,calls=self.setup_verifier()
                state['response']=response
                verifier.verify(self.token())
            self.assertEqual(len(calls),1)
            self.assertEqual(str(calls[0].url),JWKS)

    def test_provider_user_mode_returns_identity_without_profile_approval_call(self):
        payload={'id':str(self.subject),'email':'fixture@example.invalid','email_confirmed_at':'2026-01-01T00:00:00Z',
                 'last_sign_in_at':'2030-01-01T00:00:00Z','approval_status':'pending','user_metadata':{'role':'executive'}}
        verifier,_,calls=self.setup_verifier(mode='provider_user',payload=payload)
        identity=verifier.verify('synthetic-opaque-token')
        self.assertEqual(identity.subject,self.subject)
        self.assertEqual(identity.verified_email,'fixture@example.invalid')
        self.assertIsNone(identity.authenticated_at)
        self.assertIsNone(identity.session_id)
        self.assertFalse(hasattr(identity,'approval_status'))
        self.assertEqual(len(calls),1)
        self.assertEqual(str(calls[0].url),'https://provider.example.invalid/auth/v1/user')
        self.assertEqual(calls[0].headers['Authorization'],'Bearer synthetic-opaque-token')
        self.assertEqual(calls[0].headers['apikey'],'synthetic-public')

    def test_provider_does_not_trust_unconfirmed_email_or_account_login_time(self):
        verifier,_,_=self.setup_verifier(mode='provider_user',payload={'id':str(self.subject),
            'email':'unconfirmed@example.invalid','last_sign_in_at':datetime.now(timezone.utc).isoformat()})
        identity=verifier.verify('synthetic-opaque-token')
        self.assertIsNone(identity.verified_email)
        self.assertIsNone(identity.authenticated_at)

    def test_provider_invalid_token_and_service_failures_remain_distinct(self):
        for status,error in ((401,InvalidIdentity),(403,InvalidIdentity),(429,IdentityUnavailable),
                             (500,IdentityUnavailable),(302,IdentityUnavailable)):
            with self.subTest(status=status),self.assertRaises(error):
                verifier,state,_=self.setup_verifier(mode='provider_user')
                state['status']=status
                verifier.verify('synthetic-opaque-token')
        verifier,_,_=self.setup_verifier(mode='provider_user',payload={'id':'invalid-subject'})
        with self.assertRaises(IdentityUnavailable): verifier.verify('synthetic-opaque-token')

    def test_malformed_bearers_are_rejected_before_any_provider_or_jwks_fetch(self):
        for mode in ('jwt','provider_user'):
            verifier,_,calls=self.setup_verifier(mode=mode)
            for token in (None,False,'','Bearer token','bad\ntoken','ü-token','a'*16385):
                with self.subTest(mode=mode,kind=type(token).__name__),self.assertRaises(InvalidIdentity): verifier.verify(token)
            self.assertEqual(calls,[])
