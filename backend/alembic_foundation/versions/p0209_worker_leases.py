"""Bounded metadata-only worker leases; no payload or effect privileges."""
from pathlib import Path
from alembic import op
revision='p0209_worker_leases'
down_revision='p0208_enqueue'
branch_labels=None
depends_on=None
FUNCTIONS=('delivery_actor_allowed(uuid,uuid)','claim_deliveries(uuid,integer,integer)',
           'renew_delivery(uuid,uuid,bigint,integer)')


def upgrade():
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for function in FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
    for function in FUNCTIONS[1:]:op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_worker')


def downgrade():
    for function in reversed(FUNCTIONS[1:]):op.execute(f'DROP FUNCTION wpl.{function}')
    op.execute('''CREATE OR REPLACE FUNCTION wpl.tenant_admin(org uuid) RETURNS boolean LANGUAGE sql STABLE
        SET search_path=pg_catalog,wpl AS $$
        SELECT wpl.tenant_member(org) AND EXISTS(SELECT 1 FROM wpl.organization_memberships m
          JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id
          WHERE m.org_id=org AND m.user_id=wpl.ctx_uuid('wpl.actor_id') AND m.status='active' AND r.role='admin')
        $$''')
    op.execute('DROP FUNCTION wpl.delivery_actor_allowed(uuid,uuid)')
