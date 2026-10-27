"""Current-authority create receipt lookup and redacted initial-job status."""
from alembic import op
revision='p0214_provisioning_reads'
down_revision='p0213_provisioning'
branch_labels=None
depends_on=None
FUNCTIONS=('organization_creation_receipt(jsonb,character varying)','platform_primary_job(uuid,uuid)')


def upgrade():
    op.execute('''CREATE FUNCTION wpl.organization_creation_receipt(body jsonb,p_request_key varchar)
        RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        DECLARE item wpl.idempotency_records%ROWTYPE; digest text;
        BEGIN
            IF wpl.ctx_scope() IS DISTINCT FROM 'platform' OR wpl.ctx_uuid('wpl.org_id') IS NOT NULL
               OR NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
            IF body IS NULL OR jsonb_typeof(body)<>'object' OR octet_length(body::text)>16384
               OR p_request_key IS NULL OR p_request_key !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' THEN
                RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
            SELECT r.* INTO item FROM wpl.idempotency_records r WHERE r.actor_id=wpl.ctx_uuid('wpl.actor_id')
                AND r.operation='create_organization' AND r.scope_kind='platform'
                AND r.scope_id='00000000-0000-0000-0000-000000000000'::uuid AND r.request_key=p_request_key;
            IF NOT FOUND THEN RETURN NULL; END IF;
            digest:=encode(sha256(convert_to(body::text,'UTF8')),'hex');
            IF item.request_hash<>digest THEN RETURN jsonb_build_object('error','idempotency_conflict'); END IF;
            RETURN jsonb_build_object('receipt',item.response,'replayed',true);
        END
        $$''')
    op.execute('''CREATE FUNCTION wpl.platform_primary_job(org uuid,job uuid)
        RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        BEGIN
            IF wpl.ctx_scope() IS DISTINCT FROM 'platform' OR wpl.ctx_uuid('wpl.org_id') IS DISTINCT FROM org
               OR NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
            RETURN (SELECT jsonb_build_object('job_id',j.id,'kind',j.kind,'state',j.state,'delivery_status',j.delivery_status,
                'attempts',j.attempts,'max_attempts',j.max_attempts,'last_error_code',j.last_error_code,
                'created_at',j.created_at,'updated_at',j.updated_at) FROM wpl.jobs j
                WHERE j.id=job AND j.scope_kind='tenant' AND j.scope_id=org AND j.org_id=org
                  AND j.owner_user_id IS NULL AND j.kind='deliver_primary_invitation' AND j.intent_hash IS NOT NULL);
        END
        $$''')
    for function in FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_app')


def downgrade():
    for function in reversed(FUNCTIONS):op.execute(f'DROP FUNCTION wpl.{function}')
