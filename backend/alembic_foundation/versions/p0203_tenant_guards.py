"""Serialize tenant transitions and enforce deferred final-state invariants."""
from pathlib import Path
from alembic import op
revision = 'p0203_tenant_guards'
down_revision = 'p0202_tenant_schema'
branch_labels = None
depends_on = None
FUNCTIONS = ('version_entity','version_scoped_entity','lock_membership_parents',
             'lock_cohort_parent','check_primary','check_cohort_instructor',
             'check_invitation_binding','global_security_recovery','advance_role_epoch')
TRIGGERS = (
    ('users','a_users_version','BEFORE UPDATE','version_entity'),
    ('users','b_users_recovery','BEFORE UPDATE','global_security_recovery'),
    ('organizations','organization_version','BEFORE UPDATE','version_scoped_entity'),
    ('organization_memberships','member_version','BEFORE UPDATE','version_scoped_entity'),
    ('cohorts','cohort_version','BEFORE UPDATE','version_scoped_entity'),
    ('organization_memberships','member_parent','BEFORE INSERT OR UPDATE OR DELETE','lock_membership_parents'),
    ('organization_roles','role_parent','BEFORE INSERT OR UPDATE OR DELETE','lock_membership_parents'),
    ('organization_roles','role_member_epoch','AFTER INSERT OR UPDATE OR DELETE','advance_role_epoch'),
    ('cohort_memberships','cohort_member_parent','BEFORE INSERT OR UPDATE OR DELETE','lock_cohort_parent'),
)
DEFERRED = (
    ('organizations','primary_final_state','INSERT OR UPDATE','check_primary'),
    ('cohorts','cohort_final_instructor','INSERT OR UPDATE','check_cohort_instructor'),
    ('organization_memberships','member_primary_final','INSERT OR UPDATE OR DELETE','check_primary'),
    ('organization_roles','role_primary_final','INSERT OR UPDATE OR DELETE','check_primary'),
    ('organization_memberships','member_cohort_final','INSERT OR UPDATE OR DELETE','check_cohort_instructor'),
    ('organization_roles','role_cohort_final','INSERT OR UPDATE OR DELETE','check_cohort_instructor'),
    ('cohort_memberships','assignment_cohort_final','INSERT OR UPDATE OR DELETE','check_cohort_instructor'),
    ('organization_memberships','member_invitation_binding','INSERT OR UPDATE OR DELETE','check_invitation_binding'),
    ('invitations','invitation_member_binding','INSERT OR UPDATE OR DELETE','check_invitation_binding'),
)

def upgrade():
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for name in FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{name}() FROM PUBLIC,wpl_app,wpl_worker')
    for table, name, events, function in TRIGGERS:
        op.execute(f'CREATE TRIGGER {name} {events} ON wpl.{table} FOR EACH ROW EXECUTE FUNCTION wpl.{function}()')
    for table, name, events, function in DEFERRED:
        op.execute(f'CREATE CONSTRAINT TRIGGER {name} AFTER {events} ON wpl.{table} '
                   f'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION wpl.{function}()')


def downgrade():
    for table, name, _, _ in (*DEFERRED,*TRIGGERS):
        op.execute(f'DROP TRIGGER {name} ON wpl.{table}')
    for name in reversed(FUNCTIONS):
        op.execute(f'DROP FUNCTION wpl.{name}()')
