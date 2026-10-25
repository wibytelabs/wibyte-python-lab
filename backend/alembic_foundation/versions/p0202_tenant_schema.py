"""Add the bounded P02 tenant/job schema, private by default.

Database transition guards follow in the next P02.2 revision. No application table
is granted to the runtime roles until actual scoped policy is installed.
"""
from pathlib import Path
from alembic import op
revision = 'p0202_tenant_schema'
down_revision = 'p0201_private_schema'
branch_labels = None
depends_on = None
TABLES = (
    'users', 'platform_roles', 'organizations', 'organization_memberships',
    'organization_roles', 'invitations', 'primary_admin_transfers', 'cohorts',
    'cohort_memberships', 'secret_payloads', 'jobs', 'outbox', 'idempotency_records',
    'audit_events', 'migration_mappings',
)

def upgrade():
    # Each explicitly delimited block is one statement, including function bodies.
    source = Path(__file__).with_suffix('.sql').read_text()
    for statement in source.split('-- statement --'):
        op.execute(statement.strip())
    for name in TABLES:
        op.execute(f'ALTER TABLE wpl.{name} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE wpl.{name} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute("""CREATE FUNCTION wpl.reject_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, wpl AS $$
        BEGIN RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='audit_events are append-only'; END;
        $$""")
    op.execute('REVOKE ALL ON FUNCTION wpl.reject_audit_mutation() FROM PUBLIC,wpl_app,wpl_worker')
    op.execute('CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON wpl.audit_events '
               'FOR EACH ROW EXECUTE FUNCTION wpl.reject_audit_mutation()')


def downgrade():
    # Only called explicitly by the migration owner; disposable rehearsal only in P02.
    op.execute('ALTER TABLE wpl.organizations DROP CONSTRAINT organizations_primary_same_org')
    op.execute('ALTER TABLE wpl.organization_memberships DROP CONSTRAINT memberships_invitation_same_org')
    for name in reversed(TABLES):
        op.execute(f'DROP TABLE wpl.{name} CASCADE')
    op.execute('DROP FUNCTION wpl.reject_audit_mutation()')
