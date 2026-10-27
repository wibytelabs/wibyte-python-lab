"""Atomic confirmed primary change/recovery and pending notification intent."""
from pathlib import Path
from alembic import op
revision='p0217_transfer_completion'
down_revision='p0216_transfer_preview'
branch_labels=None
depends_on=None
ENTRY='confirm_primary_transfer(uuid,uuid,integer,bytea,uuid)'


def upgrade():
    op.execute("ALTER TABLE wpl.primary_admin_transfers ADD COLUMN result jsonb CHECK(result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=16384))")
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        if statement.strip():op.execute(statement.strip())
    op.execute('REVOKE ALL ON FUNCTION wpl.primary_transfer_receipt_allowed(uuid) FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{ENTRY} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{ENTRY} TO wpl_app')


def downgrade():
    op.execute(f'DROP FUNCTION wpl.{ENTRY}')
    op.execute('DROP FUNCTION wpl.primary_transfer_receipt_allowed(uuid)')
    op.execute('ALTER TABLE wpl.primary_admin_transfers DROP COLUMN result')
