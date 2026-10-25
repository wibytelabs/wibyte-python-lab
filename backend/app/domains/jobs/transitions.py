"""Explicit worker operations, each owning a short database transaction.

Decrypt, resolve keys and call delivery adapters only after these functions return.
A final target/actor check reduces revocation exposure but cannot make an external
provider transaction atomic with PostgreSQL. Adapters need stable operation dedup.
"""
from dataclasses import dataclass,field
import hashlib
from uuid import UUID
from sqlalchemy import text
from backend.app.domains.jobs.enqueue import KIND,TOKEN
from backend.app.domains.jobs.leases import DeliveryLease
from backend.app.domains.jobs.payloads import PayloadBinding,PayloadScope,EncryptedPayload,encode_object


@dataclass(frozen=True)
class DeliveryMaterial:
    binding: PayloadBinding
    envelope: EncryptedPayload=field(repr=False)


def _validate(worker,lease):
    if (not isinstance(worker,UUID) or worker.int==0 or not isinstance(lease,DeliveryLease)
            or not isinstance(lease.job_id,UUID) or lease.job_id.int==0
            or type(lease.lease_generation) is not int or lease.lease_generation<1):
        raise ValueError('Invalid delivery lease.')
    return {'job':lease.job_id,'worker':worker,'generation':lease.lease_generation}


def load_delivery(database,worker,lease):
    values=_validate(worker,lease)
    with database.transaction() as session:
        row=session.execute(text('SELECT * FROM wpl.delivery_payload(:job,:worker,:generation)'),values).mappings().one_or_none()
        material=None if row is None else DeliveryMaterial(
            PayloadBinding(PayloadScope.TENANT,row['org_id'],row['actor_id'],lease.job_id,row['payload_id'],KIND),
            EncryptedPayload(row['key_reference'],bytes(row['ciphertext'])))
    return material


def authorize_delivery(database,worker,lease,payload):
    values=_validate(worker,lease)
    # Only the fixed decrypted invitation shape crosses this boundary. Never echo it.
    if not isinstance(payload,dict) or set(payload)!={'invitation_id','email','activation_token'}:
        raise ValueError('Invalid invitation delivery payload.')
    invitation=payload['invitation_id'];email=payload['email'];token=payload['activation_token']
    if (not isinstance(invitation,str) or len(invitation)!=36 or not isinstance(email,str)
            or not 3<=len(email)<=254 or email!=email.strip().lower() or email.count('@')!=1
            or '.' not in email.split('@')[1] or any(char.isspace() or ord(char)<33 or ord(char)>126 for char in email)
            or not isinstance(token,str) or TOKEN.fullmatch(token) is None):
        raise ValueError('Invalid invitation delivery payload.')
    try:
        identifier=UUID(invitation)
        if identifier.int==0:raise ValueError
    except ValueError:raise ValueError('Invalid invitation delivery payload.') from None
    intent=hashlib.sha256(encode_object({'actor_id':str(lease.actor_id),'org_id':str(lease.org_id),
        'kind':KIND,'payload':{'invitation_id':str(identifier),'email':email,'activation_token':token}})).hexdigest()
    values.update(invitation=identifier,email=email,digest=hashlib.sha256(token.encode('ascii')).digest(),intent=intent)
    with database.transaction() as session:
        allowed=session.execute(text('SELECT wpl.authorize_delivery_target(:job,:worker,:generation,:invitation,:email,:digest,:intent)'),values).scalar_one()
    return allowed


def finish_delivery(database,worker,lease,*,outcome,error_code=None):
    values=_validate(worker,lease)
    allowed={'success':{None},'retry':{'transport_unavailable','key_unavailable'},
             'cancel':{'payload_invalid','target_unavailable'}}
    if not isinstance(outcome,str) or outcome not in allowed or not isinstance(error_code,(str,type(None))) or error_code not in allowed[outcome]:
        raise ValueError('Invalid delivery transition.')
    values.update(outcome=outcome,error=error_code)
    with database.transaction() as session:
        state=session.execute(text('SELECT wpl.finish_delivery(:job,:worker,:generation,:outcome,:error)'),values).scalar_one()
    return state
