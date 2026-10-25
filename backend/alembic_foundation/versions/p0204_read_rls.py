"""Scoped read policies; mutation and queue policies follow separately."""
from pathlib import Path
from alembic import op

revision = 'p0204_read_rls'
down_revision = 'p0203_tenant_guards'
branch_labels = None
depends_on = None

INTERNAL = ('ctx_uuid(text)', 'ctx_scope()', 'actor_active()', 'platform_capability(text)',
            'tenant_member(uuid)', 'tenant_admin(uuid)', 'assigned_cohort(uuid,uuid,text)',
            'recovery_target(uuid)')
ENTRY_POINTS = ('read_org(uuid)', 'read_member(uuid,uuid)', 'read_user(uuid)',
                'read_cohort(uuid,uuid)', 'read_assignment(uuid,uuid,uuid)', 'read_platform_role(uuid)')
POLICIES = {
    'users': 'wpl.read_user(id)',
    'platform_roles': "wpl.read_platform_role(user_id) AND (expires_at IS NULL OR expires_at>statement_timestamp())",
    'organizations': 'wpl.read_org(id)',
    'organization_memberships': 'wpl.read_member(org_id,id)',
    'organization_roles': 'wpl.read_member(org_id,membership_id)',
    'cohorts': 'wpl.read_cohort(org_id,id)',
    'cohort_memberships': 'wpl.read_assignment(org_id,cohort_id,membership_id)',
}
USER_COLUMNS = 'id,full_name,global_state,access_epoch,version,created_at,updated_at'
ROLE_COLUMNS = 'user_id,capability,expires_at'


def upgrade():
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for function in (*INTERNAL, *ENTRY_POINTS):
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
    for function in ENTRY_POINTS:
        op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_app')
    for table, expression in POLICIES.items():
        op.execute(f'CREATE POLICY foundation_read ON wpl.{table} FOR SELECT TO wpl_app USING ({expression})')
        if table not in ('users', 'platform_roles'):
            op.execute(f'GRANT SELECT ON wpl.{table} TO wpl_app')
    op.execute(f'GRANT SELECT ({USER_COLUMNS}) ON wpl.users TO wpl_app')
    op.execute(f'GRANT SELECT ({ROLE_COLUMNS}) ON wpl.platform_roles TO wpl_app')


def downgrade():
    for table in POLICIES:
        op.execute(f'DROP POLICY foundation_read ON wpl.{table}')
        op.execute(f'REVOKE SELECT ON wpl.{table} FROM wpl_app')
    op.execute(f'REVOKE SELECT ({USER_COLUMNS}) ON wpl.users FROM wpl_app')
    op.execute(f'REVOKE SELECT ({ROLE_COLUMNS}) ON wpl.platform_roles FROM wpl_app')
    for function in reversed((*INTERNAL, *ENTRY_POINTS)):
        op.execute(f'DROP FUNCTION wpl.{function}')
