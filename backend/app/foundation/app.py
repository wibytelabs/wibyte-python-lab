"""Independent factory mounting the shared router, standalone at /v1 or mounted by trusted composition."""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.identity.settings import IdentitySettings
from backend.app.domains.identity.verification import build_verifier,InvalidIdentity,IdentityUnavailable
from backend.app.foundation.api import router,APIError
from backend.app.foundation.settings import FoundationSettings,FoundationConfigurationError
from backend.app.foundation.db import FoundationDatabase
from backend.app.domains.jobs.payloads import PayloadCipher


def create_app(settings: FoundationSettings,*,identity_settings: IdentitySettings | None=None,identity_transport=None,payload_cipher: PayloadCipher | None=None,route_prefix: str='/v1') -> FastAPI:
    """Explicit trusted settings/resources; no dotenv or runtime bypass flags.

    identity_transport is an injected HTTP transport for isolated fixtures. Tokens
    still pass through the production verifier; request data cannot select it.
    """
    if route_prefix not in ('','/v1'):
        raise FoundationConfigurationError('Foundation route prefix must be /v1 or an explicit mounted root.')
    if payload_cipher is not None and not isinstance(payload_cipher,PayloadCipher):
        raise FoundationConfigurationError('An explicit payload cipher is required.')
    if settings.enabled and not isinstance(identity_settings,IdentitySettings):
        raise FoundationConfigurationError('Explicit foundation identity settings are required.')
    verifier=build_verifier(identity_settings,transport=identity_transport) if settings.enabled else None
    try:
        database=FoundationDatabase(settings) if settings.enabled else None
    except BaseException:
        if verifier: verifier.close()
        raise

    @asynccontextmanager
    async def lifespan(app):
        try:
            if database: database.verify_runtime_role()
            yield
        finally:
            try:
                if database: database.close()
            finally:
                if verifier: verifier.close()

    app=FastAPI(title='WPL tenant foundation',lifespan=lifespan)
    app.state.foundation_database=database
    app.state.foundation_verifier=verifier
    app.state.foundation_payload_cipher=payload_cipher if settings.enabled else None
    if settings.enabled: app.include_router(router,prefix=route_prefix)

    def error(request,status,code,message,**extra):
        request_id=getattr(request.state,'request_id',uuid4().hex)
        headers={'X-Request-ID':request_id,'Cache-Control':'no-store'}
        if status==401: headers['WWW-Authenticate']='Bearer'
        return JSONResponse(status_code=status,content={
            'code':code,'message':message,'request_id':request_id,**extra},headers=headers)

    @app.middleware('http')
    async def request_envelope(request,call_next):
        request.state.request_id=uuid4().hex
        response=await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(APIError)
    async def api_error(request,exception):
        return error(request,exception.status_code,exception.code,exception.message)

    @app.exception_handler(InvalidIdentity)
    @app.exception_handler(IdentityUnavailable)
    async def identity_error(request,exception):
        return error(request,exception.status_code,exception.code,str(exception))

    @app.exception_handler(AuthorizationDenied)
    async def forbidden(request,exception):
        return error(request,403,exception.code,str(exception))

    @app.exception_handler(TenantConflict)
    async def conflict(request,exception):
        return error(request,409,exception.code,str(exception))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exception):
        fields={'.'.join(str(part) for part in item['loc']):'Invalid value.' for item in exception.errors()}
        return error(request,422,'validation_error','Request validation failed.',field_errors=fields)

    @app.exception_handler(HTTPException)
    async def http_error(request,exception):
        if exception.status_code==404:
            return error(request,404,'not_found','Requested resource is unavailable.')
        return error(request,exception.status_code,'http_error','Request could not be completed.')

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request,exception):
        return error(request,503,'data_unavailable','Application data is temporarily unavailable.')

    @app.exception_handler(Exception)
    async def internal_error(request,exception):
        return error(request,500,'internal_error','Request could not be completed.')

    return app
