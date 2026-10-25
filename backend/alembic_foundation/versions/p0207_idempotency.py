"""Own-actor idempotency receipts for current tenant mutation operations only."""
from alembic import op
revision='p0207_idempotency'
down_revision='p0206_tenant_mutations'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""CREATE FUNCTION wpl.idempotency_access(actor uuid,org uuid,scope varchar,scope_uuid uuid,operation_name varchar)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        SELECT actor=wpl.ctx_uuid('wpl.actor_id') AND scope='tenant' AND scope_uuid=org
            AND wpl.tenant_admin(org) AND operation_name IN ('set_member_status','replace_roles','set_instructors')
        $$""")
    op.execute('REVOKE ALL ON FUNCTION wpl.idempotency_access(uuid,uuid,character varying,uuid,character varying) FROM PUBLIC,wpl_app,wpl_worker')
    op.execute('GRANT EXECUTE ON FUNCTION wpl.idempotency_access(uuid,uuid,character varying,uuid,character varying) TO wpl_app')
    access='wpl.idempotency_access(actor_id,org_id,scope_kind,scope_id,operation)'
    op.execute('CREATE POLICY own_idempotency_read ON wpl.idempotency_records FOR SELECT TO wpl_app USING ('+access+')')
    # Receipts have a fixed small public shape; no raw capability/payload field fits.
    receipt="""response_status=200 AND jsonb_typeof(response->'version')='number'
        AND (response->>'version') ~ '^[1-9][0-9]{0,9}$' AND (
          (operation='set_member_status'
            AND response ?& ARRAY['membership_id','status','version']
            AND response-ARRAY['membership_id','status','version']='{}'::jsonb
            AND jsonb_typeof(response->'membership_id')='string'
            AND (response->>'membership_id') ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            AND response->>'status' IN ('active','suspended','removed'))
          OR (operation='replace_roles'
            AND response ?& ARRAY['membership_id','roles','version']
            AND response-ARRAY['membership_id','roles','version']='{}'::jsonb
            AND jsonb_typeof(response->'membership_id')='string'
            AND (response->>'membership_id') ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            AND jsonb_typeof(response->'roles')='array' AND response->'roles'<@'["admin","instructor","student"]'::jsonb
            AND CASE WHEN jsonb_typeof(response->'roles')='array' THEN jsonb_array_length(response->'roles') BETWEEN 1 AND 3 ELSE false END)
          OR (operation='set_instructors'
            AND response ?& ARRAY['cohort_id','version']
            AND response-ARRAY['cohort_id','version']='{}'::jsonb
            AND jsonb_typeof(response->'cohort_id')='string'
            AND (response->>'cohort_id') ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'))"""
    op.execute('CREATE POLICY own_idempotency_insert ON wpl.idempotency_records FOR INSERT TO wpl_app WITH CHECK ('+access+' AND ('+receipt+'))')
    op.execute('GRANT SELECT ON wpl.idempotency_records TO wpl_app')
    op.execute('GRANT INSERT (actor_id,operation,scope_kind,scope_id,org_id,request_key,request_hash,response_status,response) ON wpl.idempotency_records TO wpl_app')


def downgrade():
    op.execute('REVOKE INSERT (actor_id,operation,scope_kind,scope_id,org_id,request_key,request_hash,response_status,response) ON wpl.idempotency_records FROM wpl_app')
    op.execute('REVOKE SELECT ON wpl.idempotency_records FROM wpl_app')
    op.execute('DROP POLICY own_idempotency_insert ON wpl.idempotency_records')
    op.execute('DROP POLICY own_idempotency_read ON wpl.idempotency_records')
    op.execute('DROP FUNCTION wpl.idempotency_access(uuid,uuid,character varying,uuid,character varying)')
