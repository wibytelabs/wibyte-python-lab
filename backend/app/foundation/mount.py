"""Explicit legacy composition without loading legacy config or environment here."""
from contextlib import asynccontextmanager
from typing import Mapping
from backend.app.domains.identity.settings import IdentitySettings
from backend.app.foundation.app import create_app
from backend.app.foundation.settings import FoundationSettings,FoundationConfigurationError


def mount_foundation(parent,values: Mapping[str,str],*,identity_transport=None,payload_cipher=None):
    settings=FoundationSettings.from_mapping(values)
    if not settings.enabled:return None
    if any(getattr(route,'path','')=='/v1' or getattr(route,'path','').startswith('/v1/') for route in parent.routes):
        raise FoundationConfigurationError('Foundation /v1 routes are already configured.')
    identity=IdentitySettings.from_mapping(values)
    child=create_app(settings,identity_settings=identity,identity_transport=identity_transport,
        payload_cipher=payload_cipher,route_prefix='')
    previous=parent.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        # ASGI mounts do not run child lifespans automatically. Enter foundation
        # first so a failed role check cannot start legacy background services.
        async with child.router.lifespan_context(child):
            async with previous(app) as state:
                yield state

    try:
        parent.mount('/v1',child,name='foundation-v1')
        parent.router.lifespan_context=lifespan
        parent.state.foundation_app=child
    except BaseException:
        try:child.state.foundation_database.close()
        finally:child.state.foundation_verifier.close()
        raise
    return child
