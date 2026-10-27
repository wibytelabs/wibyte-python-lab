"""Atomic pending organization creation; no direct table/bootstrap grants."""
from pathlib import Path
from alembic import op
revision='p0213_provisioning'
down_revision='p0212_executive_metadata'
branch_labels=None
depends_on=None
FUNCTION='provision_organization(jsonb,character varying,uuid,uuid,uuid,uuid,uuid,bytea,character varying,bytea,character varying)'


def upgrade():
    op.execute(Path(__file__).with_suffix('.sql').read_text())
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{FUNCTION} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{FUNCTION} TO wpl_app')


def downgrade():op.execute(f'DROP FUNCTION wpl.{FUNCTION}')
