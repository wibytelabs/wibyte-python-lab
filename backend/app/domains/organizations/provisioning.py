"""Prepare sensitive intent outside the UOW; create pending records atomically."""
from dataclasses import dataclass,field
import hashlib
import json
import re
import secrets
from uuid import UUID,uuid4
from sqlalchemy import text
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.organizations.directory import require_organization_directory
from backend.app.domains.organizations.requests import OrganizationCreate
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadBinding,PayloadScope,EncryptedPayload,encode_object

KIND='deliver_primary_invitation'
KEY=re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
PUBLIC={'org_id','status','primary_admin_membership_id','invitation_status','job_id','delivery_status','version'}


@dataclass(frozen=True)
class PreparedOrganization:
    actor_id: UUID
    org_id: UUID
    member_id: UUID
    invitation_id: UUID
    binding: PayloadBinding
    request: OrganizationCreate=field(repr=False)
    envelope: EncryptedPayload=field(repr=False)
    token_digest: bytes=field(repr=False)
    intent_hash: str=field(repr=False)


@dataclass(frozen=True)
class OrganizationCreation:
    receipt: dict=field(repr=False)
    replayed: bool

    def public(self):return dict(self.receipt)


def prepare_organization(context: RequestContext,request: OrganizationCreate,cipher: PayloadCipher):
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.PLATFORM or context.org_id is not None
            or not isinstance(request,OrganizationCreate) or not isinstance(cipher,PayloadCipher)):
        raise AuthorizationDenied()
    org,member,invitation,job,payload=(uuid4() for _ in range(5))
    token=secrets.token_urlsafe(32)
    value={'invitation_id':str(invitation),'email':request.primary_admin_email,'activation_token':token}
    binding=PayloadBinding(PayloadScope.TENANT,org,context.identity.subject,job,payload,KIND)
    intent=hashlib.sha256(encode_object({'actor_id':str(context.identity.subject),'org_id':str(org),'kind':KIND,'payload':value})).hexdigest()
    return PreparedOrganization(context.identity.subject,org,member,invitation,binding,request.model_copy(deep=True),
        cipher.encrypt(value,binding),hashlib.sha256(token.encode('ascii')).digest(),intent)


def create_organization(session,context: RequestContext,request_key: str,prepared: PreparedOrganization):
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.PLATFORM or context.org_id is not None
            or not isinstance(prepared,PreparedOrganization) or prepared.actor_id!=context.identity.subject
            or prepared.binding.actor_id!=context.identity.subject or prepared.binding.scope is not PayloadScope.TENANT
            or prepared.binding.scope_id!=prepared.org_id or prepared.binding.purpose!=KIND):
        raise AuthorizationDenied()
    if not isinstance(request_key,str) or KEY.fullmatch(request_key) is None:
        raise TenantConflict('invalid_idempotency_key','A bounded idempotency key is required.')
    require_organization_directory(session,context.identity)
    with session.begin_nested():
        result=session.execute(text('''SELECT wpl.provision_organization(CAST(:body AS jsonb),:key,:org,:member,:invitation,
            :job,:payload,:digest,:reference,:encrypted,:intent)'''),
            {'body':json.dumps(prepared.request.model_dump()),'key':request_key,'org':prepared.org_id,'member':prepared.member_id,
             'invitation':prepared.invitation_id,'job':prepared.binding.operation_id,'payload':prepared.binding.payload_id,
             'digest':prepared.token_digest,'reference':prepared.envelope.key_reference,
             'encrypted':prepared.envelope.ciphertext,'intent':prepared.intent_hash}).scalar_one()
        return _creation_result(result)


def _creation_result(result):
    if result.get('error')=='forbidden':raise AuthorizationDenied()
    if 'error' in result:
        code='idempotency_conflict' if result['error']=='idempotency_conflict' else 'invalid_provisioning'
        message='The idempotency key already has different input.' if code=='idempotency_conflict' else 'Organization provisioning input is invalid.'
        raise TenantConflict(code,message)
    receipt=result.get('receipt')
    if (not isinstance(receipt,dict) or set(receipt)!=PUBLIC or receipt['status']!='pending'
            or receipt['invitation_status']!='pending' or receipt['delivery_status']!='pending_integration'
            or type(receipt['version']) is not int or receipt['version']<1 or type(result.get('replayed')) is not bool):
        raise RuntimeError('Organization receipt is invalid.')
    for name in ('org_id','primary_admin_membership_id','job_id'):
        try:
            if not isinstance(receipt[name],str) or UUID(receipt[name]).int==0:raise ValueError
        except (ValueError,TypeError):raise RuntimeError('Organization receipt is invalid.') from None
    return OrganizationCreation(receipt,result['replayed'])


def find_organization_creation(session,context: RequestContext,request_key: str,request: OrganizationCreate):
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.PLATFORM or context.org_id is not None
            or not isinstance(request,OrganizationCreate)):
        raise AuthorizationDenied()
    if not isinstance(request_key,str) or KEY.fullmatch(request_key) is None:
        raise TenantConflict('invalid_idempotency_key','A bounded idempotency key is required.')
    require_organization_directory(session,context.identity)
    result=session.execute(text('SELECT wpl.organization_creation_receipt(CAST(:body AS jsonb),:key)'),
        {'body':json.dumps(request.model_dump()),'key':request_key}).scalar_one()
    return None if result is None else _creation_result(result)
