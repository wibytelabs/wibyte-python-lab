"""One explicitly injected delivery attempt; no daemon, provider or key defaults.

Adapters must honor the supplied timeout, deduplicate/reconcile by the stable job
UUID across lease generations and distinguish simulation from provider acceptance.
A database lease cannot guarantee universal exactly-once external effects.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID
from sqlalchemy import text
from backend.app.domains.jobs.leases import DeliveryLease,renew_delivery
from backend.app.domains.jobs.transitions import load_delivery,authorize_delivery,finish_delivery
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadKeyUnavailable,InvalidPayload


class DeliveryAcknowledgement(Enum):
    SIMULATED='simulated'
    PROVIDER_ACCEPTED='provider_accepted'


class InvitationDeliveryAdapter(Protocol):
    def deliver(self,operation_id: UUID,payload: dict,*,timeout_seconds: int) -> DeliveryAcknowledgement: ...


@dataclass(frozen=True)
class DeliveryExecution:
    job_id: UUID
    state: str
    delivery_status: str='pending_integration'

    def public(self):
        return {'job_id':str(self.job_id),'state':self.state,'delivery_status':self.delivery_status}


def process_delivery(database,worker_id: UUID,lease: DeliveryLease,cipher: PayloadCipher,adapter: InvitationDeliveryAdapter):
    """Use only with a committed claim. All key/provider I/O is outside DB UOWs.

    A process-level BaseException intentionally escapes without recording success;
    expiry/reclaim retries the same provider operation ID. Database errors after
    adapter acceptance also escape, leaving the claim recoverable. Caller logs
    must not include raw exceptions or local payload values.
    """
    if (not isinstance(worker_id,UUID) or worker_id.int==0 or not isinstance(lease,DeliveryLease)
            or not isinstance(cipher,PayloadCipher) or not callable(getattr(adapter,'deliver',None))):
        raise ValueError('Explicit worker lease, cipher and delivery adapter are required.')

    def finish(outcome,error):
        state=finish_delivery(database,worker_id,lease,outcome=outcome,error_code=error)
        return DeliveryExecution(lease.job_id,state or 'lease_lost')

    failure=None
    try:
        material=load_delivery(database,worker_id,lease)
        if material is None:return finish('cancel','target_unavailable')
        payload=cipher.decrypt(material.envelope,material.binding)
    except PayloadKeyUnavailable:
        failure=('retry','key_unavailable')
    except InvalidPayload:
        failure=('cancel','payload_invalid')
    if failure is not None:return finish(*failure)
    if not renew_delivery(database,worker_id,lease,lease_seconds=60):
        return finish('cancel','target_unavailable')
    try:
        allowed=authorize_delivery(database,worker_id,lease,payload)
    except ValueError:
        allowed=None
    if allowed is None:return finish('cancel','payload_invalid')
    if not allowed:return finish('cancel','target_unavailable')
    try:
        acknowledgement=adapter.deliver(lease.job_id,payload,timeout_seconds=10)
    except Exception:
        # Leave the handler before DB work: a DB error must not chain raw provider diagnostics.
        acknowledgement=None
    if not isinstance(acknowledgement,DeliveryAcknowledgement):
        return finish('retry','transport_unavailable')
    with database.transaction() as session:
        state=session.execute(text('SELECT wpl.acknowledge_delivery(:job,:worker,:generation,:ack)'),
            {'job':lease.job_id,'worker':worker_id,'generation':lease.lease_generation,'ack':acknowledgement.value}).scalar_one()
    return DeliveryExecution(lease.job_id,state or 'lease_lost',
        acknowledgement.value if state=='succeeded' else 'pending_integration')
