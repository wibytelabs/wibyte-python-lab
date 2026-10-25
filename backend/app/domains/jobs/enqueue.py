"""Prepare encrypted delivery outside DB transactions; persist intent atomically.

No delivery adapter/provider call occurs here. All accepted receipts mean durable
queue intent, never mail delivery or account activation. Only the tenant invitation
operation is wired initially; platform provisioning requires its own P02.5 scope.
"""
from dataclasses import dataclass,field
import hashlib
import hmac
import re
from uuid import UUID,uuid4

from sqlalchemy import text

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.authorization.policy import require_tenant_admin
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadBinding,PayloadScope,EncryptedPayload,encode_object

KIND='deliver_invitation'
TOKEN=re.compile(r'[A-Za-z0-9_-]{32,512}')
HASH=re.compile(r'[0-9a-f]{64}')


class InvalidDelivery(ValueError):
    code='invalid_delivery'
    status_code=422
    def __init__(self):super().__init__('Invitation delivery input is invalid.')


@dataclass(frozen=True)
class PreparedInvitation:
    binding: PayloadBinding
    envelope: EncryptedPayload=field(repr=False)
    invitation_id: UUID
    recipient: str=field(repr=False)
    token_digest: bytes=field(repr=False)
    intent_hash: str=field(repr=False)


@dataclass(frozen=True)
class QueuedDelivery:
    job_id: UUID
    state: str
    delivery_status: str='pending_integration'

    def public(self):
        return {'job_id':str(self.job_id),'state':self.state,'delivery_status':self.delivery_status}


def prepare_invitation(context: RequestContext,delivery_id: UUID,cipher: PayloadCipher,payload: dict):
    """Call before opening the mutation UOW, including any key-provider resolution.

    A future remote KMS provider must prefetch/resolve outside the DB transaction.
    No key lookup, network call or encryption is performed by enqueue_invitation.
    """
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.TENANT
            or not isinstance(delivery_id,UUID) or delivery_id.int==0 or not isinstance(cipher,PayloadCipher)
            or not isinstance(payload,dict) or set(payload)!={'invitation_id','email','activation_token'}):
        raise InvalidDelivery()
    email=payload['email'];token=payload['activation_token'];invitation=payload['invitation_id']
    if (not isinstance(email,str) or not 3<=len(email)<=254 or email!=email.strip().lower()
            or email.count('@')!=1 or '.' not in email.split('@')[1]
            or any(char.isspace() or ord(char)<33 or ord(char)>126 for char in email)
            or not isinstance(token,str) or TOKEN.fullmatch(token) is None
            or not isinstance(invitation,str) or len(invitation)!=36):
        raise InvalidDelivery()
    try:
        invitation_id=UUID(invitation)
        if invitation_id.int==0:raise ValueError
    except ValueError:raise InvalidDelivery() from None
    value={'invitation_id':str(invitation_id),'email':email,'activation_token':token}
    bound=PayloadBinding(PayloadScope.TENANT,context.org_id,context.identity.subject,delivery_id,uuid4(),KIND)
    intent_hash=hashlib.sha256(encode_object({'actor_id':str(context.identity.subject),
        'org_id':str(context.org_id),'kind':KIND,'payload':value})).hexdigest()
    return PreparedInvitation(bound,cipher.encrypt(value,bound),invitation_id,email,
                              hashlib.sha256(token.encode('ascii')).digest(),intent_hash)


def enqueue_invitation(session,context: RequestContext,prepared: PreparedInvitation):
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.TENANT
            or not isinstance(prepared,PreparedInvitation) or not isinstance(prepared.binding,PayloadBinding)
            or not isinstance(prepared.envelope,EncryptedPayload) or not isinstance(prepared.invitation_id,UUID)
            or not isinstance(prepared.token_digest,bytes) or len(prepared.token_digest)!=32
            or not isinstance(prepared.intent_hash,str) or HASH.fullmatch(prepared.intent_hash) is None
            or not session.in_transaction()):
        raise InvalidDelivery()
    bound=prepared.binding
    if (bound.scope is not PayloadScope.TENANT or bound.scope_id!=context.org_id
            or bound.actor_id!=context.identity.subject or bound.purpose!=KIND):
        raise AuthorizationDenied()
    require_tenant_admin(session,context.identity,context.org_id)
    lock_key=int.from_bytes(hashlib.blake2b(('wpl.delivery.v1:'+str(bound.operation_id)).encode(),digest_size=8).digest(),signed=True)
    parameters={'id':bound.operation_id,'org':context.org_id,'actor':context.identity.subject,
                'kind':KIND,'payload_id':bound.payload_id,'intent':prepared.intent_hash,
                'dedup':'invitation:'+str(context.identity.subject)+':'+str(bound.operation_id)}
    with session.begin_nested():
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':lock_key})
        require_tenant_admin(session,context.identity,context.org_id)
        eligible=session.execute(text('SELECT wpl.delivery_target_allowed(:org,:invitation,:email,:digest)'),
            {'org':context.org_id,'invitation':prepared.invitation_id,'email':prepared.recipient,'digest':prepared.token_digest}).scalar_one()
        if not eligible:
            raise TenantConflict('delivery_target_unavailable','This invitation cannot be queued for delivery.')
        row=session.execute(text('SELECT id,actor_id,org_id,kind,state,intent_hash,delivery_status FROM wpl.jobs WHERE id=:id'),parameters).mappings().one_or_none()
        if row is not None:
            if (row['actor_id']!=context.identity.subject or row['org_id']!=context.org_id or row['kind']!=KIND
                    or not hmac.compare_digest(row['intent_hash'],prepared.intent_hash)):
                raise TenantConflict('job_conflict','The delivery operation already has different input.')
            return QueuedDelivery(row['id'],row['state'],row['delivery_status'])
        session.execute(text('''INSERT INTO wpl.secret_payloads(id,scope_kind,scope_id,org_id,key_reference,ciphertext)
            VALUES (:id,'tenant',:org,:org,:reference,:ciphertext)'''),
            {'id':bound.payload_id,'org':context.org_id,'reference':prepared.envelope.key_reference,
             'ciphertext':prepared.envelope.ciphertext})
        inserted=session.execute(text('''INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key,private_payload_id,intent_hash)
            VALUES (:id,'tenant',:org,:org,:actor,:kind,:dedup,:payload_id,:intent)
            ON CONFLICT (id) DO NOTHING RETURNING id'''),parameters).scalar_one_or_none()
        if inserted is None:
            raise TenantConflict('job_conflict','The delivery operation already has different input.')
        session.execute(text('''INSERT INTO wpl.outbox(id,scope_kind,scope_id,job_id,event_kind,dedup_key)
            VALUES (:id,'tenant',:org,:job,'delivery_requested',:dedup)'''),
            {'id':uuid4(),'org':context.org_id,'job':bound.operation_id,'dedup':'delivery:'+str(bound.operation_id)})
        session.execute(text('''INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
            VALUES (:id,:actor,:org,'job_enqueued','Invitation delivery queued','job',:job,
              jsonb_build_object('job_kind','deliver_invitation','delivery_status','pending_integration'))'''),
            {'id':uuid4(),'actor':context.identity.subject,'org':context.org_id,'job':bound.operation_id})
        return QueuedDelivery(bound.operation_id,'queued')
