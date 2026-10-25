"""Shared internal /v1 read router; public proxy adds the /api prefix."""
import base64
import binascii
from datetime import datetime, timezone
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.domains.authorization.context import RequestContext, RequestScope
from backend.app.domains.authorization.policy import require_tenant_admin
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
