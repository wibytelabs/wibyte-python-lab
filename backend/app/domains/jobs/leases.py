"""Short committed worker transactions; callers perform no I/O inside them.

Worker database configuration is explicitly supplied by the server. No runtime
role switch, actor header, environment lookup or migration capability is used.
These leases expose metadata only, not a delivery executor or success result.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from sqlalchemy import text


@dataclass(frozen=True)
class DeliveryLease:
    job_id: UUID
    actor_id: UUID
    org_id: UUID
    lease_generation: int
    lease_until: datetime
    attempts: int


def _uuid(value):return isinstance(value,UUID) and value.int!=0


def claim_deliveries(database,worker_id: UUID,*,batch_size=10,lease_seconds=60):
    if (not _uuid(worker_id) or type(batch_size) is not int or not 1<=batch_size<=20
            or type(lease_seconds) is not int or not 5<=lease_seconds<=300):
        raise ValueError('Invalid worker claim bounds.')
    with database.transaction() as session:
        rows=session.execute(text('SELECT * FROM wpl.claim_deliveries(:worker,:batch,:seconds)'),
            {'worker':worker_id,'batch':batch_size,'seconds':lease_seconds}).mappings().all()
        leases=[DeliveryLease(**row) for row in rows]
    return leases


def renew_delivery(database,worker_id: UUID,lease: DeliveryLease,*,lease_seconds=60):
    if (not _uuid(worker_id) or not isinstance(lease,DeliveryLease) or not _uuid(lease.job_id)
            or type(lease.lease_generation) is not int or lease.lease_generation<1
            or type(lease_seconds) is not int or not 5<=lease_seconds<=300):
        raise ValueError('Invalid worker lease bounds.')
    with database.transaction() as session:
        renewed=session.execute(text('SELECT wpl.renew_delivery(:job,:worker,:generation,:seconds)'),
            {'job':lease.job_id,'worker':worker_id,'generation':lease.lease_generation,'seconds':lease_seconds}).scalar_one()
    return renewed
