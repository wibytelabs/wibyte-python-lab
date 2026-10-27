"""Private, version-bound primary/recovery preview; no designation writes."""
from pathlib import Path
from alembic import op
revision='p0216_transfer_preview'
down_revision='p0215_primary_worker'
branch_labels=None
depends_on=None
ENTRY='preview_primary_transfer(uuid,uuid,integer,character varying,uuid,bytea)'


def upgrade():
    op.execute("ALTER TABLE wpl.primary_admin_transfers ADD COLUMN authorization_scope varchar(16) NOT NULL DEFAULT 'tenant' CHECK(authorization_scope IN ('tenant','platform'))")
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        if statement.strip():op.execute(statement.strip())
    op.execute('REVOKE ALL ON FUNCTION wpl.primary_transfer_allowed(uuid) FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{ENTRY} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{ENTRY} TO wpl_app')


def downgrade():
    op.execute(f'DROP FUNCTION wpl.{ENTRY}')
    op.execute('DROP FUNCTION wpl.primary_transfer_allowed(uuid)')
    op.execute('ALTER TABLE wpl.primary_admin_transfers DROP COLUMN authorization_scope')
