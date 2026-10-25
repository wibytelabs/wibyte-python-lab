"""Minimal tenant-admin member/role/instructor writes, with bounded audit intent.

No executive, designation, identity-binding or queue authority is granted here.
"""
from alembic import op
revision='p0206_tenant_mutations'
down_revision='p0205_identity_mirror'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""CREATE FUNCTION wpl.write_tenant(org uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        SELECT wpl.tenant_admin(org)
        $$""")
    op.execute("""CREATE FUNCTION wpl.write_tenant_audit(org uuid,actor uuid,action_name varchar,
        kind varchar,target uuid,reason_text varchar) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        SELECT actor=wpl.ctx_uuid('wpl.actor_id') AND wpl.tenant_admin(org)
          AND length(trim(reason_text)) BETWEEN 5 AND 1000
          AND ((kind='membership' AND action_name IN ('membership_status_changed','membership_roles_changed')
              AND EXISTS(SELECT 1 FROM wpl.organization_memberships m WHERE m.org_id=org AND m.id=target))
            OR (kind='cohort' AND action_name='cohort_instructors_changed'
              AND EXISTS(SELECT 1 FROM wpl.cohorts c WHERE c.org_id=org AND c.id=target)))
        $$""")
    for function in ('write_tenant(uuid)',
                     'write_tenant_audit(uuid,uuid,character varying,character varying,uuid,character varying)'):
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_app')
    for table in ('organizations','organization_memberships','cohorts','cohort_memberships'):
        op.execute(f'CREATE POLICY tenant_update ON wpl.{table} FOR UPDATE TO wpl_app '
                   'USING (wpl.write_tenant('+('id' if table=='organizations' else 'org_id')+')) '
                   'WITH CHECK (wpl.write_tenant('+('id' if table=='organizations' else 'org_id')+'))')
    op.execute('GRANT UPDATE (name,contact_email,home_region) ON wpl.organizations TO wpl_app')
    op.execute('GRANT UPDATE (status,version) ON wpl.organization_memberships TO wpl_app')
    op.execute('GRANT UPDATE (name) ON wpl.cohorts TO wpl_app')
    op.execute('GRANT UPDATE (status) ON wpl.cohort_memberships TO wpl_app')
    op.execute('CREATE POLICY tenant_roles_insert ON wpl.organization_roles FOR INSERT TO wpl_app WITH CHECK (wpl.write_tenant(org_id))')
    op.execute('CREATE POLICY tenant_roles_delete ON wpl.organization_roles FOR DELETE TO wpl_app USING (wpl.write_tenant(org_id))')
    op.execute('GRANT INSERT,DELETE ON wpl.organization_roles TO wpl_app')
    op.execute('CREATE POLICY tenant_assignment_insert ON wpl.cohort_memberships FOR INSERT TO wpl_app WITH CHECK (wpl.write_tenant(org_id))')
    op.execute('GRANT INSERT ON wpl.cohort_memberships TO wpl_app')
    op.execute('CREATE POLICY tenant_audit_read ON wpl.audit_events FOR SELECT TO wpl_app USING (wpl.write_tenant(org_id))')
    op.execute('CREATE POLICY tenant_audit_insert ON wpl.audit_events FOR INSERT TO wpl_app '
               'WITH CHECK (wpl.write_tenant_audit(org_id,actor_id,action,target_type,target_id,reason))')
    op.execute('GRANT SELECT ON wpl.audit_events TO wpl_app')
    op.execute('GRANT INSERT (id,actor_id,org_id,action,reason,target_type,target_id,changes) ON wpl.audit_events TO wpl_app')


def downgrade():
    op.execute('REVOKE INSERT (id,actor_id,org_id,action,reason,target_type,target_id,changes) ON wpl.audit_events FROM wpl_app')
    op.execute('REVOKE SELECT ON wpl.audit_events FROM wpl_app')
    op.execute('DROP POLICY tenant_audit_insert ON wpl.audit_events')
    op.execute('DROP POLICY tenant_audit_read ON wpl.audit_events')
    op.execute('REVOKE INSERT ON wpl.cohort_memberships FROM wpl_app')
    op.execute('DROP POLICY tenant_assignment_insert ON wpl.cohort_memberships')
    op.execute('REVOKE INSERT,DELETE ON wpl.organization_roles FROM wpl_app')
    op.execute('DROP POLICY tenant_roles_delete ON wpl.organization_roles')
    op.execute('DROP POLICY tenant_roles_insert ON wpl.organization_roles')
    for table,columns in (('organizations','name,contact_email,home_region'),
                          ('organization_memberships','status,version'),('cohorts','name'),
                          ('cohort_memberships','status')):
        op.execute(f'REVOKE UPDATE ({columns}) ON wpl.{table} FROM wpl_app')
        op.execute(f'DROP POLICY tenant_update ON wpl.{table}')
    op.execute('DROP FUNCTION wpl.write_tenant_audit(uuid,uuid,character varying,character varying,uuid,character varying)')
    op.execute('DROP FUNCTION wpl.write_tenant(uuid)')
