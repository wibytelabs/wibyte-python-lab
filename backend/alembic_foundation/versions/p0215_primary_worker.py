"""Explicit stored executive authority for pending designated-primary delivery."""
from pathlib import Path
from alembic import op
revision='p0215_primary_worker'
down_revision='p0214_provisioning_reads'
branch_labels=None
depends_on=None
PAYLOAD='delivery_payload(uuid,uuid,bigint)'
NAMES={'claim_deliveries','renew_delivery','delivery_payload','authorize_delivery_target','finish_delivery'}


def _grant_payload():
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{PAYLOAD} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{PAYLOAD} TO wpl_worker')


def upgrade():
    op.execute(f'DROP FUNCTION wpl.{PAYLOAD}')
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    op.execute('REVOKE ALL ON FUNCTION wpl.job_delivery_actor_allowed(uuid,uuid,character varying) FROM PUBLIC,wpl_app,wpl_worker')
    _grant_payload()


def downgrade():
    op.execute(f'DROP FUNCTION wpl.{PAYLOAD}')
    for source in ('p0209_worker_leases.sql','p0210_worker_transitions.sql'):
        for statement in Path(__file__).with_name(source).read_text().split('-- statement --'):
            statement=statement.strip()
            if any(statement.startswith('CREATE FUNCTION wpl.'+name+'(') for name in NAMES):
                if not statement.startswith('CREATE FUNCTION wpl.delivery_payload('):
                    statement=statement.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
                op.execute(statement)
    _grant_payload()
    op.execute('DROP FUNCTION wpl.job_delivery_actor_allowed(uuid,uuid,character varying)')
