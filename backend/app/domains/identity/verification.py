"""Bounded provider identity and asymmetric JWT verification; no tenant grants."""
from datetime import datetime, timezone
import json
import re
import threading
import time
from uuid import UUID
import httpx
import jwt
from jwt.exceptions import PyJWTError
from backend.app.domains.identity.settings import IdentitySettings
from backend.app.domains.identity.types import VerifiedIdentity

TOKEN=re.compile(r'[A-Za-z0-9._~+/=-]{1,16384}')
KID=re.compile(r'[A-Za-z0-9_-]{1,128}')

class InvalidIdentity(ValueError):
    code='invalid_identity'
    status_code=401
    def __init__(self):
        super().__init__('Invalid or expired authentication token.')

class IdentityUnavailable(RuntimeError):
    code='identity_unavailable'
    status_code=503
    def __init__(self):
        super().__init__('Identity verification is temporarily unavailable.')


def token_value(token):
    if not isinstance(token,str) or TOKEN.fullmatch(token) is None:
        raise InvalidIdentity()
    return token


def subject_uuid(value):
    if not isinstance(value,str) or len(value)!=36:
        raise ValueError('Invalid subject shape')
    return UUID(value)


def email_value(value):
    if not isinstance(value,str) or not 3 < len(value) <= 254 or value.strip()!=value or '@' not in value or any(c.isspace() or ord(c)<32 for c in value):
        return None
    return value


class BoundedJSONClient:
    """No proxy env/redirects; bounded phases, response bytes and read-loop budget.

    HTTP phase timeouts plus a read-loop deadline bound slow responses. This is
    not an OS-level guarantee against a blocked system resolver. Fixture failures
    use injected transports; no real provider is required by mandatory tests.
    """
    def __init__(self, settings: IdentitySettings, *, transport=None, monotonic=time.monotonic):
        self.settings=settings
        self.clock=monotonic
        self.client=httpx.Client(trust_env=False,follow_redirects=False,transport=transport,
            timeout=httpx.Timeout(settings.request_timeout_seconds,connect=min(1,settings.request_timeout_seconds)),
            limits=httpx.Limits(max_connections=2,max_keepalive_connections=2))

    def get(self,url,*,headers=None,max_bytes=131072):
        deadline=self.clock()+self.settings.deadline_seconds
        try:
            request_headers={'Accept-Encoding':'identity',**(headers or {})}
            with self.client.stream('GET',url,headers=request_headers) as response:
                if self.clock()>deadline:
                    raise IdentityUnavailable()
                if response.status_code!=200:
                    return response.status_code,None
                if response.headers.get('content-encoding','identity').lower()!='identity':
                    raise IdentityUnavailable()
                content_type=response.headers.get('content-type','').split(';',1)[0].strip().lower()
                if content_type not in {'application/json','application/jwk-set+json'}:
                    raise IdentityUnavailable()
                parts=[]
                size=0
                for part in response.iter_bytes():
                    size+=len(part)
                    if size>max_bytes or self.clock()>deadline:
                        raise IdentityUnavailable()
                    parts.append(part)
                return 200,json.loads(b''.join(parts))
        except IdentityUnavailable:
            raise
        except (httpx.HTTPError,ValueError,RecursionError):
            raise IdentityUnavailable() from None

    def close(self):
        self.client.close()


class JWKSCache:
    def __init__(self,settings,http,*,monotonic=time.monotonic):
        self.settings=settings
        self.http=http
        self.clock=monotonic
        self.lock=threading.Lock()
        self.keys={}
        self.expires=0.0
        self.last_attempt=float('-inf')
        self.last_failed=False

    def parsed_keys(self,payload):
        if not isinstance(payload,dict) or not isinstance(payload.get('keys'),list) or not 1 <= len(payload['keys']) <= 32:
            raise IdentityUnavailable()
        keys={}
        seen=set()
        try:
            for data in payload['keys']:
                if not isinstance(data,dict):
                    raise ValueError
                kid=data.get('kid')
                if not isinstance(kid,str) or KID.fullmatch(kid) is None or kid in seen:
                    raise ValueError
                seen.add(kid)
                if any(name in data for name in ('d','p','q','dp','dq','qi','oth','k')):
                    raise ValueError
                algorithm=data.get('alg')
                if algorithm not in self.settings.algorithms:
                    continue
                if data.get('use','sig')!='sig' or data.get('key_ops',['verify'])!=['verify']:
                    continue
                if algorithm=='ES256' and (data.get('kty')!='EC' or data.get('crv')!='P-256'):
                    raise ValueError
                if algorithm=='RS256' and (data.get('kty')!='RSA' or not isinstance(data.get('n'),str) or len(data['n'])>2048):
                    raise ValueError
                key=jwt.PyJWK.from_dict(data,algorithm=algorithm).key
                if algorithm=='RS256' and not 2048 <= key.key_size <= 8192:
                    raise ValueError
                keys[kid]=(algorithm,key)
        except (PyJWTError,ValueError,TypeError,OverflowError):
            raise IdentityUnavailable() from None
        if not keys:
            raise IdentityUnavailable()
        return keys

    def get(self,kid,algorithm):
        if not self.lock.acquire(timeout=self.settings.deadline_seconds):
            raise IdentityUnavailable()
        try:
            now=self.clock()
            if now<self.expires and kid in self.keys:
                stored,key=self.keys[kid]
                if stored!=algorithm:
                    raise InvalidIdentity()
                return key
            if now-self.last_attempt<self.settings.refresh_seconds:
                if self.last_failed or now>=self.expires:
                    raise IdentityUnavailable()
                raise InvalidIdentity()
            self.last_attempt=now
            try:
                status,payload=self.http.get(self.settings.jwks_url)
                if status!=200:
                    raise IdentityUnavailable()
                parsed=self.parsed_keys(payload)
            except IdentityUnavailable:
                self.last_failed=True
                raise
            self.keys=parsed
            self.expires=self.clock()+self.settings.cache_seconds
            self.last_failed=False
            if kid not in self.keys or self.keys[kid][0]!=algorithm:
                raise InvalidIdentity()
            return self.keys[kid][1]
        finally:
            self.lock.release()


class JWTVerifier:
    def __init__(self,settings,http,*,monotonic=time.monotonic):
        self.settings=settings
        self.http=http
        self.cache=JWKSCache(settings,http,monotonic=monotonic)

    def verify(self,token):
        token=token_value(token)
        try:
            header=jwt.get_unverified_header(token)
            algorithm=header.get('alg')
            kid=header.get('kid')
            if (algorithm not in self.settings.algorithms or not isinstance(kid,str) or KID.fullmatch(kid) is None
                    or any(name in header for name in ('jku','x5u','jwk','crit','b64'))
                    or header.get('typ','JWT')!='JWT'):
                raise InvalidIdentity()
            key=self.cache.get(kid,algorithm)
            # Allowed algorithms are configuration-owned, never derived from the token.
            claims=jwt.decode(token,key,algorithms=list(self.settings.algorithms),
                issuer=self.settings.issuer,audience=self.settings.audience,leeway=self.settings.leeway_seconds,
                options={'require':['exp','iat','iss','aud','sub','session_id'],
                         'verify_signature':True,'verify_exp':True,'verify_iat':True,'verify_nbf':True,
                         'verify_aud':True,'verify_iss':True,'verify_sub':True})
            for name in ('iat','exp'):
                if type(claims[name]) is not int or claims[name]<0:
                    raise InvalidIdentity()
            if claims['exp']<=claims['iat'] or ('nbf' in claims and type(claims['nbf']) is not int):
                raise InvalidIdentity()
            subject=subject_uuid(claims['sub'])
            session=subject_uuid(claims['session_id'])
            authenticated=None
            if 'auth_time' in claims:
                value=claims['auth_time']
                if type(value) is not int or value<0 or value>claims['iat']+self.settings.leeway_seconds:
                    raise InvalidIdentity()
                authenticated=datetime.fromtimestamp(value,timezone.utc)
            email=email_value(claims.get('email')) if claims.get('email_verified') is True else None
            return VerifiedIdentity(subject,authenticated,email,str(session))
        except (InvalidIdentity,IdentityUnavailable):
            raise
        except (PyJWTError,ValueError,TypeError,RecursionError,OverflowError,KeyError):
            raise InvalidIdentity() from None

    def close(self):
        self.http.close()


class ProviderUserVerifier:
    def __init__(self,settings,http):
        self.settings=settings
        self.http=http
        self.url=settings.provider_url.rstrip('/')+'/auth/v1/user'

    def verify(self,token):
        token=token_value(token)
        status,user=self.http.get(self.url,headers={
            'apikey':self.settings.publishable_key,'Authorization':'Bearer '+token},max_bytes=65536)
        if status in (401,403):
            raise InvalidIdentity()
        if status!=200 or not isinstance(user,dict):
            raise IdentityUnavailable()
        try:
            subject=subject_uuid(user.get('id'))
            confirmed=user.get('email_confirmed_at')
            email=None
            if confirmed:
                when=datetime.fromisoformat(confirmed.replace('Z','+00:00'))
                if when.tzinfo is None:
                    raise ValueError
                email=email_value(user.get('email'))
            # Account-wide last_sign_in_at is not proof of this token's recent auth.
            # Provider mode does not pretend to know session/auth time from an opaque token.
            return VerifiedIdentity(subject,verified_email=email)
        except (ValueError,TypeError,AttributeError):
            raise IdentityUnavailable() from None

    def close(self):
        self.http.close()


def build_verifier(settings: IdentitySettings,*,transport=None,monotonic=time.monotonic):
    http=BoundedJSONClient(settings,transport=transport)
    if settings.mode=='provider_user':
        return ProviderUserVerifier(settings,http)
    return JWTVerifier(settings,http,monotonic=monotonic)
