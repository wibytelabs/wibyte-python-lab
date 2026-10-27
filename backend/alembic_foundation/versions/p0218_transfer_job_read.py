"""Narrow redacted transfer-notification status with current scoped authority."""
from alembic import op
revision='p0218_transfer_job_read'
down_revision='p0217_transfer_completion'
branch_labels=None
depends_on=None
ENTRY='primary_transfer_job(uuid,uuid)'


def upgrade():
    op.execute('''CREATE FUNCTION wpl.primary_transfer_job(p_org uuid,p_job uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        DECLARE item wpl.jobs%ROWTYPE;
        BEGIN
            IF NOT COALESCE(wpl.primary_transfer_receipt_allowed(p_org),false) THEN RETURN NULL; END IF;
            SELECT j.* INTO item FROM wpl.jobs j JOIN wpl.primary_admin_transfers t ON t.org_id=j.org_id
                AND t.result->>'job_id'=j.id::text AND t.result->>'transfer_id'=t.id::text
                WHERE j.id=p_job AND j.org_id=p_org AND j.scope_kind='tenant' AND j.scope_id=p_org
                AND j.owner_user_id IS NULL AND j.kind='notify_primary_transfer' AND j.private_payload_id IS NULL
                AND j.actor_id=t.actor_id AND t.status='completed' AND j.dedup_key='primary_transfer:'||t.id::text
                AND j.intent_hash=encode(sha256(convert_to(jsonb_build_object('org_id',p_org,'transfer_id',t.id,
                    'actor_id',t.actor_id,'from_membership_id',t.from_membership_id,
                    'to_membership_id',t.to_membership_id,'authorization_scope',t.authorization_scope,
                    'kind','notify_primary_transfer')::text,'UTF8')),'hex')
                AND EXISTS(SELECT 1 FROM wpl.outbox o WHERE o.job_id=j.id AND o.scope_kind='tenant' AND o.scope_id=p_org
                    AND o.event_kind='primary_transfer_notification_requested' AND o.dedup_key='primary_transfer:'||t.id::text);
            IF NOT FOUND THEN RETURN NULL; END IF;
            RETURN jsonb_build_object('job_id',item.id,'kind',item.kind,'state',item.state,
                'delivery_status',item.delivery_status,'attempts',item.attempts,'max_attempts',item.max_attempts,
                'last_error_code',item.last_error_code,'created_at',item.created_at,'updated_at',item.updated_at);
        END
        $$''')
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{ENTRY} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{ENTRY} TO wpl_app')


def downgrade():op.execute(f'DROP FUNCTION wpl.{ENTRY}')
