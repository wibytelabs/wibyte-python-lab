"""Fenced payload access and terminal/retry decisions; no external provider."""
from pathlib import Path
from alembic import op
revision='p0210_worker_transitions'
down_revision='p0209_worker_leases'
branch_labels=None
depends_on=None
FUNCTIONS=('delivery_payload(uuid,uuid,bigint)',
    'authorize_delivery_target(uuid,uuid,bigint,uuid,character varying,bytea,character varying)',
    'finish_delivery(uuid,uuid,bigint,character varying,character varying)')


def upgrade():
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for function in FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_worker')


def downgrade():
    for function in reversed(FUNCTIONS):op.execute(f'DROP FUNCTION wpl.{function}')
