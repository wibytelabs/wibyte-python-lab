"""Explicit identity configuration; no environment/dotenv or legacy fallback."""
from dataclasses import dataclass, field
import math
from typing import Mapping
from urllib.parse import urlsplit
from backend.app.foundation.settings import FoundationConfigurationError


def identity_url(value, name):
    try:
        if not isinstance(value,str) or not value or '\\' in value or any(c.isspace() or ord(c)<32 for c in value):
            raise ValueError
        url=urlsplit(value)
        if (not url.hostname or url.username is not None or url.password is not None
                or url.query or url.fragment or (url.port is not None and not 1 <= url.port <= 65535)):
            raise ValueError
        if url.scheme!='https' and not (url.scheme=='http' and url.hostname in {'localhost','127.0.0.1','::1'}):
            raise ValueError
        return value.rstrip('/')
    except (ValueError,TypeError):
        raise FoundationConfigurationError(f'{name} requires an explicit HTTPS URL (or loopback HTTP).') from None


@dataclass(frozen=True)
class IdentitySettings:
    mode: str = 'provider_user'
    provider_url: str | None = None
    publishable_key: str | None = field(default=None,repr=False)
    issuer: str | None = None
    audience: str | None = None
    jwks_url: str | None = None
    algorithms: tuple[str,...] = ()
    cache_seconds: int = 300
    refresh_seconds: int = 10
    leeway_seconds: int = 30
    request_timeout_seconds: float = 2.0
    deadline_seconds: float = 3.0

    def __post_init__(self):
        if self.mode not in {'provider_user','jwt'}:
            raise FoundationConfigurationError('WPL_AUTH_MODE must be provider_user or jwt.')
        for name,low,high in (('cache_seconds',30,600),('refresh_seconds',2,60),('leeway_seconds',0,60)):
            value=getattr(self,name)
            if type(value) is not int or not low <= value <= high:
                raise FoundationConfigurationError(f'{name} is outside its bounded range.')
        for name,low,high in (('request_timeout_seconds',0.1,5),('deadline_seconds',1,10)):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
                raise FoundationConfigurationError(f'{name} is outside its bounded range.')
        if self.mode=='provider_user':
            identity_url(self.provider_url,'WPL_AUTH_PROVIDER_URL')
            key=self.publishable_key
            if not isinstance(key,str) or not 1 <= len(key) <= 4096 or any(c.isspace() or ord(c)<32 or ord(c)>126 for c in key):
                raise FoundationConfigurationError('WPL_AUTH_PUBLISHABLE_KEY is required and must be a valid header value.')
        else:
            identity_url(self.issuer,'WPL_AUTH_ISSUER')
            identity_url(self.jwks_url,'WPL_AUTH_JWKS_URL')
            if not isinstance(self.audience,str) or not 1 <= len(self.audience) <= 128 or self.audience.strip()!=self.audience:
                raise FoundationConfigurationError('WPL_AUTH_AUDIENCE is required.')
            if (not isinstance(self.algorithms,tuple) or not self.algorithms or len(self.algorithms)>2
                    or not all(isinstance(value,str) for value in self.algorithms)
                    or len(set(self.algorithms))!=len(self.algorithms)
                    or not set(self.algorithms)<={'ES256','RS256'}):
                raise FoundationConfigurationError('WPL_AUTH_ALGORITHMS must explicitly select ES256 and/or RS256.')

    @classmethod
    def from_mapping(cls, values: Mapping[str,str]):
        mode=values.get('WPL_AUTH_MODE','provider_user')
        if mode=='provider_user':
            return cls(mode=mode,provider_url=values.get('WPL_AUTH_PROVIDER_URL'),
                       publishable_key=values.get('WPL_AUTH_PUBLISHABLE_KEY'))
        return cls(mode=mode,issuer=values.get('WPL_AUTH_ISSUER'),audience=values.get('WPL_AUTH_AUDIENCE'),
                   jwks_url=values.get('WPL_AUTH_JWKS_URL'),
                   algorithms=tuple(values.get('WPL_AUTH_ALGORITHMS','').split(',')))
