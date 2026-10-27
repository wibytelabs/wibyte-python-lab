"""Primary transfer previews bound to trusted request context and current authority.

Callers own commit/rollback. Confirmation is returned once to the caller, stored
only as a digest, and excluded from repr. Completion rechecks current authority, recent authentication and the preview.
"""
from dataclasses import dataclass,field
from datetime import datetime
import hashlib
import secrets
from uuid import UUID,uuid4
from sqlalchemy import text
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.errors import AuthorizationDenied,TenantConflict

ERRORS={
    'invalid_preview':'The transfer preview input is invalid.',
    'version_conflict':'The organization changed; reload before retrying.',
    'target_ineligible':'Choose another active administrator in this organization.',
    'preview_in_progress':'Another authorized actor has a current transfer preview.',
    'invalid_confirmation':'The transfer confirmation is stale or unavailable.',
    'recent_auth_required':'Authenticate again before confirming a primary change.',
}


@dataclass(frozen=True)
class TransferPreview:
    transfer_id: UUID
    org_id: UUID
    from_membership_id: UUID
    to_membership_id: UUID
    expected_version: int
    expires_at: datetime
    authorization_scope: str
    confirmation: str=field(repr=False)


def preview_transfer(session,context: RequestContext,target: UUID,version: int,reason: str):
    if (not isinstance(context,RequestContext) or context.scope not in (RequestScope.TENANT,RequestScope.PLATFORM)
            or context.org_id is None):raise AuthorizationDenied()
    bound=session.execute(text("""SELECT current_user,current_setting('wpl.actor_id',true),
        current_setting('wpl.scope_kind',true),current_setting('wpl.org_id',true)""")).one()
    if tuple(bound)!=('wpl_app',str(context.identity.subject),context.scope.value,str(context.org_id)):
        raise AuthorizationDenied()
    if (not isinstance(target,UUID) or type(version) is not int or version<1 or not isinstance(reason,str)
            or not 5<=len(reason.strip())<=1000 or any(ord(char)<32 or ord(char)==127 for char in reason)):
        raise TenantConflict('invalid_preview',ERRORS['invalid_preview'])
    transfer=uuid4();confirmation=secrets.token_urlsafe(32)
    with session.begin_nested():
        result=session.execute(text('SELECT wpl.preview_primary_transfer(:org,:target,:version,:reason,:id,:digest)'),
            {'org':context.org_id,'target':target,'version':version,'reason':reason.strip(),'id':transfer,
             'digest':hashlib.sha256(confirmation.encode()).digest()}).scalar_one()
        if not isinstance(result,dict):raise RuntimeError('Invalid transfer preview result.')
        if 'error' in result:
            code=result['error']
            if code=='forbidden':raise AuthorizationDenied()
            code=code if code in ERRORS else 'invalid_preview'
            raise TenantConflict(code,ERRORS[code])
        expected={'transfer_id','org_id','from_membership_id','to_membership_id','expected_version','expires_at','authorization_scope'}
        if set(result)!=expected:raise RuntimeError('Invalid transfer preview result.')
        preview=TransferPreview(*(UUID(result[key]) for key in ('transfer_id','org_id','from_membership_id','to_membership_id')),
            result['expected_version'],datetime.fromisoformat(result['expires_at']),result['authorization_scope'],confirmation)
        if (preview.transfer_id!=transfer or preview.org_id!=context.org_id or preview.to_membership_id!=target
                or type(preview.expected_version) is not int or preview.expected_version!=version
                or preview.authorization_scope!=context.scope.value or preview.expires_at.tzinfo is None):
            raise RuntimeError('Invalid transfer preview result.')
        return preview


@dataclass(frozen=True)
class TransferCompletion:
    receipt: dict=field(repr=False)
    replayed: bool

    @property
    def public(self):return dict(self.receipt)


def confirm_transfer(session,context: RequestContext,transfer_id: UUID,version: int,confirmation: str):
    if (not isinstance(context,RequestContext) or context.scope not in (RequestScope.TENANT,RequestScope.PLATFORM)
            or context.org_id is None):raise AuthorizationDenied()
    bound=session.execute(text("""SELECT current_user,current_setting('wpl.actor_id',true),
        current_setting('wpl.scope_kind',true),current_setting('wpl.org_id',true),current_setting('wpl.auth_time',true)""")).one()
    authenticated=context.identity.authenticated_at
    auth_time=str(int(authenticated.timestamp())) if authenticated is not None else ''
    if tuple(bound)!=('wpl_app',str(context.identity.subject),context.scope.value,str(context.org_id),auth_time):
        raise AuthorizationDenied()
    if (not isinstance(transfer_id,UUID) or type(version) is not int or version<1 or not isinstance(confirmation,str)
            or not 1<=len(confirmation)<=256 or any(ord(char)<33 or ord(char)>126 for char in confirmation)):
        raise TenantConflict('invalid_confirmation',ERRORS['invalid_confirmation'])
    with session.begin_nested():
        result=session.execute(text('SELECT wpl.confirm_primary_transfer(:org,:transfer,:version,:digest,:job)'),
            {'org':context.org_id,'transfer':transfer_id,'version':version,
             'digest':hashlib.sha256(confirmation.encode()).digest(),'job':uuid4()}).scalar_one()
        if not isinstance(result,dict):raise RuntimeError('Invalid primary change result.')
        if 'error' in result:
            code=result['error']
            if code=='forbidden':raise AuthorizationDenied()
            code=code if code in ERRORS else 'invalid_confirmation'
            raise TenantConflict(code,ERRORS[code])
        fields={'transfer_id','org_id','primary_admin_membership_id','version','access_epoch','status','job_id','delivery_status'}
        receipt=result.get('receipt')
        if set(result)!={'receipt','replayed'} or type(result['replayed']) is not bool or not isinstance(receipt,dict) or set(receipt)!=fields:
            raise RuntimeError('Invalid primary change result.')
        try:
            identifiers={key:UUID(receipt[key]) for key in ('transfer_id','org_id','primary_admin_membership_id','job_id')}
        except (TypeError,ValueError,AttributeError):raise RuntimeError('Invalid primary change result.') from None
        if (identifiers['transfer_id']!=transfer_id or identifiers['org_id']!=context.org_id
                or any(item.int==0 for item in identifiers.values()) or type(receipt['version']) is not int
                or receipt['version']!=version+1 or type(receipt['access_epoch']) is not int or receipt['access_epoch']<1
                or receipt['status']!='active' or receipt['delivery_status']!='pending_integration'):
            raise RuntimeError('Invalid primary change result.')
        return TransferCompletion(dict(receipt),result['replayed'])
