"""Shared internal /v1 read router; public proxy adds the /api prefix."""
import base64
import binascii
from datetime import datetime, timezone
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import text

from backend.app.domains.authorization.context import RequestContext, RequestScope
from backend.app.domains.authorization.policy import require_tenant_admin
from backend.app.domains.organizations.directory import require_organization_directory
from backend.app.domains.organizations.metadata import change_organization
from backend.app.domains.organizations.requests import OrganizationPatch, OrganizationStatus, OrganizationCreate, PrimaryTransferPreview, PrimaryTransferConfirmation
from backend.app.domains.organizations.provisioning import prepare_organization, create_organization, find_organization_creation
from backend.app.domains.jobs.payloads import PayloadKeyUnavailable, InvalidPayload
from backend.app.domains.errors import AuthorizationDenied, TenantConflict
from backend.app.domains.organizations.transfers import preview_transfer, confirm_transfer
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.identity.verification import InvalidIdentity

router=APIRouter(prefix='/v1')


class APIError(Exception):
    def __init__(self,status,code,message):
        self.status_code=status
        self.code=code
        self.message=message


def identity(request: Request) -> VerifiedIdentity:
    header=request.headers.get('Authorization','')
    parts=header.split(' ')
    if len(parts)!=2 or parts[0].lower()!='bearer' or not parts[1]:
        raise InvalidIdentity()
    # No actor/role/capability header or cookie is an authentication source.
    return request.app.state.foundation_verifier.verify(parts[1])


Actor=Annotated[VerifiedIdentity,Depends(identity)]
Limit=Annotated[int,Query(ge=1,le=100)]
Cursor=Annotated[str | None,Query(max_length=512)]


def decode_cursor(cursor):
    if cursor is None:
        return None
    try:
        raw=base64.b64decode(cursor+'='*(-len(cursor)%4),altchars=b'-_',validate=True)
        if len(raw)>384: raise ValueError
        parts=json.loads(raw)
        if not isinstance(parts,list) or len(parts)!=2 or not all(isinstance(p,str) for p in parts):
            raise ValueError
        timestamp=datetime.fromisoformat(parts[0])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None: raise ValueError
        return timestamp.astimezone(timezone.utc),UUID(parts[1])
    except (ValueError,TypeError,binascii.Error,OverflowError,UnicodeError):
        raise APIError(400,'invalid_cursor','Invalid pagination cursor.') from None


def page_parameters(limit,cursor):
    position=decode_cursor(cursor)
    return {'take':limit+1,'cursor_time':position[0] if position else None,
            'cursor_id':position[1] if position else None}


def page(rows,limit):
    more=len(rows)>limit
    items=[dict(row) for row in rows[:limit]]
    next_cursor=None
    if more:
        last=items[-1]
        raw=json.dumps([last['created_at'].isoformat(),str(last['id'])],separators=(',',':')).encode()
        next_cursor=base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return {'items':items,'next_cursor':next_cursor}


# Identifiers remain fixed SQL; cursor values are parameters and never SQL text.
PAGE_FILTER='AND (CAST(:cursor_time AS timestamptz) IS NULL OR (m.created_at,m.id)>(CAST(:cursor_time AS timestamptz),CAST(:cursor_id AS uuid)))'


def tenant_record(session,actor,org):
    record=session.execute(text('''SELECT o.id,o.name,o.organization_type,o.home_region,o.status,o.version,
        o.access_epoch,o.contact_email,o.primary_admin_membership_id
        FROM wpl.organizations o JOIN wpl.organization_memberships m ON m.org_id=o.id
        JOIN wpl.users u ON u.id=m.user_id
        WHERE o.id=:org AND m.user_id=:actor AND m.status='active' AND o.status='active' AND u.global_state='active'
    '''),{'org':org,'actor':actor.subject}).mappings().one_or_none()
    if record is None:
        raise APIError(404,'not_found','Requested resource is unavailable.')
    roles=session.execute(text('''SELECT r.role FROM wpl.organization_roles r
        JOIN wpl.organization_memberships m ON m.id=r.membership_id AND m.org_id=r.org_id
        WHERE m.org_id=:org AND m.user_id=:actor AND m.status='active' ORDER BY r.role'''),
        {'org':org,'actor':actor.subject}).scalars().all()
    return dict(record),roles


@router.get('/me')
def me(request: Request,actor: Actor,limit: Limit=50,cursor: Cursor=None):
    parameters=page_parameters(limit,cursor)
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.GLOBAL)) as session:
        # Only id is writable, and DB policy requires own actor + pending defaults.
        session.execute(text('INSERT INTO wpl.users(id) VALUES (:actor) ON CONFLICT (id) DO NOTHING'),{'actor':actor.subject})
        user=dict(session.execute(text('''SELECT id,full_name,global_state,access_epoch,version
            FROM wpl.users WHERE id=:actor'''),{'actor':actor.subject}).mappings().one())
        parameters['actor']=actor.subject
        rows=session.execute(text('''SELECT m.id,m.org_id,m.status,m.version,m.created_at,
            o.name AS organization_name,o.status AS organization_status,
            ARRAY(SELECT r.role FROM wpl.organization_roles r WHERE r.org_id=m.org_id AND r.membership_id=m.id ORDER BY r.role) AS roles
            FROM wpl.organization_memberships m JOIN wpl.organizations o ON o.id=m.org_id
            WHERE m.user_id=:actor '''+PAGE_FILTER+' ORDER BY m.created_at,m.id LIMIT :take'),parameters).mappings().all()
        memberships=page(rows,limit)
        for member in memberships['items']:
            member['can_enter']=(user['global_state']=='active' and member['status']=='active' and member['organization_status']=='active')
        capabilities=session.execute(text('''SELECT capability FROM wpl.platform_roles
            WHERE user_id=:actor ORDER BY capability'''),{'actor':actor.subject}).scalars().all() if user['global_state']=='active' else []
        return {'user':user,'memberships':memberships,'capabilities':capabilities}


@router.get('/orgs/{org_id}')
def organization(org_id: UUID,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.TENANT,org_id)) as session:
        record,roles=tenant_record(session,actor,org_id)
        if 'admin' not in roles:
            record.pop('contact_email')
            record.pop('primary_admin_membership_id')
        return record


@router.get('/orgs/{org_id}/members')
def members(org_id: UUID,request: Request,actor: Actor,limit: Limit=50,cursor: Cursor=None):
    parameters=page_parameters(limit,cursor)
    parameters['org']=org_id
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.TENANT,org_id)) as session:
        tenant_record(session,actor,org_id)
        require_tenant_admin(session,actor,org_id)
        rows=session.execute(text('''SELECT m.id,m.user_id,m.status,m.version,m.created_at,u.full_name,
            ARRAY(SELECT r.role FROM wpl.organization_roles r WHERE r.org_id=m.org_id AND r.membership_id=m.id ORDER BY r.role) AS roles
            FROM wpl.organization_memberships m LEFT JOIN wpl.users u ON u.id=m.user_id
            WHERE m.org_id=:org '''+PAGE_FILTER+' ORDER BY m.created_at,m.id LIMIT :take'),parameters).mappings().all()
        return page(rows,limit)


@router.get('/orgs/{org_id}/cohorts')
def cohorts(org_id: UUID,request: Request,actor: Actor,limit: Limit=50,cursor: Cursor=None):
    parameters=page_parameters(limit,cursor)
    parameters['org']=org_id
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.TENANT,org_id)) as session:
        tenant_record(session,actor,org_id)
        rows=session.execute(text('''SELECT m.id,m.name,m.slug,m.status,m.version,m.created_at
            FROM wpl.cohorts m WHERE m.org_id=:org '''+PAGE_FILTER+
            ' ORDER BY m.created_at,m.id LIMIT :take'),parameters).mappings().all()
        return page(rows,limit)


@router.get('/platform/organizations')
def organization_directory(request: Request,actor: Actor,limit: Limit=50,cursor: Cursor=None,
        status: Literal['pending','active','suspended','recovery_required'] | None=None,
        organization_type: Literal['school','university','training','other'] | None=None,
        search: Annotated[str | None,Query(max_length=120)]=None):
    parameters=page_parameters(limit,cursor)
    parameters.update(status=status,organization_type=organization_type,search=search)
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM)) as session:
        require_organization_directory(session,actor)
        rows=session.execute(text("""SELECT m.id,m.name,m.organization_type,m.home_region,m.status,m.version,m.created_at
            FROM wpl.organizations m WHERE (CAST(:status AS text) IS NULL OR m.status=:status)
            AND (CAST(:organization_type AS text) IS NULL OR m.organization_type=:organization_type)
            AND (CAST(:search AS text) IS NULL OR strpos(lower(m.name),lower(:search))>0) """+
            PAGE_FILTER+' ORDER BY m.created_at,m.id LIMIT :take'),parameters).mappings().all()
        return page(rows,limit)


@router.get('/platform/organizations/{org_id}')
def executive_organization(org_id: UUID,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM,org_id)) as session:
        require_organization_directory(session,actor,org_id)
        row=session.execute(text("""SELECT id,name,organization_type,home_region,status,contact_email,
            primary_admin_membership_id,version,access_epoch,created_at,updated_at
            FROM wpl.organizations WHERE id=:org"""),{'org':org_id}).mappings().one_or_none()
        if row is None:raise APIError(404,'not_found','Requested resource is unavailable.')
        return dict(row)


@router.get('/orgs/{org_id}/jobs/{job_id}')
def tenant_job(org_id: UUID,job_id: UUID,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.TENANT,org_id)) as session:
        tenant_record(session,actor,org_id)
        row=session.execute(text("""SELECT id AS job_id,kind,state,delivery_status,attempts,max_attempts,
            last_error_code,created_at,updated_at FROM wpl.jobs WHERE org_id=:org AND id=:job"""),
            {'org':org_id,'job':job_id}).mappings().one_or_none()
        if row is None:
            result=session.execute(text('SELECT wpl.primary_transfer_job(:org,:job)'),{'org':org_id,'job':job_id}).scalar_one()
            if result is None:raise APIError(404,'not_found','Requested resource is unavailable.')
            return result
        return dict(row)


@router.patch('/platform/organizations/{org_id}')
def edit_organization(org_id: UUID,body: OrganizationPatch,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM,org_id)) as session:
        result=change_organization(session,actor,org_id,version=body.expected_version,reason=body.reason,
            operation='metadata',name=body.name,contact_email=body.contact_email,home_region=body.home_region)
        if result is None:raise APIError(404,'not_found','Requested resource is unavailable.')
        return result


@router.post('/platform/organizations/{org_id}/status')
def organization_status(org_id: UUID,body: OrganizationStatus,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM,org_id)) as session:
        result=change_organization(session,actor,org_id,version=body.expected_version,reason=body.reason,
            operation='status',status=body.status)
        if result is None:raise APIError(404,'not_found','Requested resource is unavailable.')
        return result


@router.post('/platform/organizations',status_code=201)
def provision_organization(request: Request,response: Response,actor: Actor,body: OrganizationCreate,
        idempotency_key: Annotated[str,Header(alias='Idempotency-Key',min_length=1,max_length=128,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')]):
    database=request.app.state.foundation_database
    context=RequestContext(actor,RequestScope.PLATFORM)
    # Authority and saved-result lookup precede key I/O; cache replay needs no key.
    with database.request_transaction(context) as session:
        outcome=find_organization_creation(session,context,idempotency_key,body)
    if outcome is None:
        cipher=request.app.state.foundation_payload_cipher
        if cipher is None:raise APIError(503,'delivery_unavailable','Invitation preparation is temporarily unavailable.')
        try:
            prepared=prepare_organization(context,body,cipher)
        except (PayloadKeyUnavailable,InvalidPayload):
            raise APIError(503,'delivery_unavailable','Invitation preparation is temporarily unavailable.') from None
        with database.request_transaction(context) as session:
            outcome=create_organization(session,context,idempotency_key,prepared)
    response.headers['Idempotency-Replayed']='true' if outcome.replayed else 'false'
    return outcome.public()


@router.get('/platform/organizations/{org_id}/jobs/{job_id}')
def initial_primary_job(org_id: UUID,job_id: UUID,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM,org_id)) as session:
        require_organization_directory(session,actor,org_id)
        result=session.execute(text('SELECT wpl.platform_primary_job(:org,:job)'),{'org':org_id,'job':job_id}).scalar_one()
        if result is None:raise APIError(404,'not_found','Requested resource is unavailable.')
        if result.get('error')=='forbidden':raise AuthorizationDenied()
        return result


IfMatch=Annotated[str | None,Header(alias='If-Match',max_length=32)]


def transfer_preconditions(actor,version,if_match):
    # Auth time comes only from production identity verification, never headers.
    authenticated=actor.authenticated_at
    if authenticated is None or not -30<=(datetime.now(timezone.utc)-authenticated).total_seconds()<=300:
        raise TenantConflict('recent_auth_required','Authenticate again before changing the primary designation.')
    if if_match is not None and if_match!='"'+str(version)+'"':
        raise TenantConflict('version_conflict','The organization changed; reload before retrying.')


def transfer_preview_response(org_id,body,request,actor,scope,if_match):
    transfer_preconditions(actor,body.expected_version,if_match)
    context=RequestContext(actor,scope,org_id)
    with request.app.state.foundation_database.request_transaction(context) as session:
        result=preview_transfer(session,context,body.target_membership_id,body.expected_version,body.reason)
    return {'transfer_id':str(result.transfer_id),'org_id':str(result.org_id),
        'from_membership_id':str(result.from_membership_id),'to_membership_id':str(result.to_membership_id),
        'expected_version':result.expected_version,'expires_at':result.expires_at.isoformat(),
        'confirmation':result.confirmation,'former_primary_retains_admin':True,
        'operation':'recovery' if scope is RequestScope.PLATFORM else 'transfer'}


def transfer_confirmation_response(org_id,body,request,response,actor,scope,if_match):
    transfer_preconditions(actor,body.expected_version,if_match)
    context=RequestContext(actor,scope,org_id)
    with request.app.state.foundation_database.request_transaction(context) as session:
        result=confirm_transfer(session,context,body.transfer_id,body.expected_version,body.confirmation)
    response.headers['Idempotency-Replayed']='true' if result.replayed else 'false'
    return result.public


@router.post('/orgs/{org_id}/primary-admin-transfers/preview')
def primary_transfer_preview(org_id: UUID,body: PrimaryTransferPreview,request: Request,actor: Actor,if_match: IfMatch=None):
    return transfer_preview_response(org_id,body,request,actor,RequestScope.TENANT,if_match)


@router.post('/orgs/{org_id}/primary-admin-transfers')
def primary_transfer_confirmation(org_id: UUID,body: PrimaryTransferConfirmation,request: Request,response: Response,actor: Actor,if_match: IfMatch=None):
    return transfer_confirmation_response(org_id,body,request,response,actor,RequestScope.TENANT,if_match)


@router.post('/platform/organizations/{org_id}/primary-admin-recovery/preview')
def primary_recovery_preview(org_id: UUID,body: PrimaryTransferPreview,request: Request,actor: Actor,if_match: IfMatch=None):
    return transfer_preview_response(org_id,body,request,actor,RequestScope.PLATFORM,if_match)


@router.post('/platform/organizations/{org_id}/primary-admin-recovery')
def primary_recovery_confirmation(org_id: UUID,body: PrimaryTransferConfirmation,request: Request,response: Response,actor: Actor,if_match: IfMatch=None):
    return transfer_confirmation_response(org_id,body,request,response,actor,RequestScope.PLATFORM,if_match)


@router.get('/platform/organizations/{org_id}/primary-admin-recovery/jobs/{job_id}')
def primary_recovery_job(org_id: UUID,job_id: UUID,request: Request,actor: Actor):
    with request.app.state.foundation_database.request_transaction(RequestContext(actor,RequestScope.PLATFORM,org_id)) as session:
        result=session.execute(text('SELECT wpl.primary_transfer_job(:org,:job)'),{'org':org_id,'job':job_id}).scalar_one()
        if result is None:raise APIError(404,'not_found','Requested resource is unavailable.')
        return result
