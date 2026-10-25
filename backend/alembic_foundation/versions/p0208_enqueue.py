"""Tenant invitation delivery intent only; worker/platform policies follow."""
from pathlib import Path
from alembic import op
revision='p0208_enqueue'
down_revision='p0207_idempotency'
branch_labels=None
depends_on=None
FUNCTIONS=(
    'delivery_target_allowed(uuid,uuid,character varying,bytea)',
    'payload_enqueue_allowed(uuid,character varying,uuid)',
    'job_enqueue_allowed(uuid,uuid,character varying,uuid,character varying)',
    'job_read_allowed(uuid,uuid,character varying,uuid)',
    'outbox_enqueue_allowed(uuid,character varying,uuid,character varying,character varying)',
    'outbox_read_allowed(uuid,character varying,uuid)',
    'job_audit_allowed(uuid,uuid,uuid)',
)
JOB_COLUMNS='id,scope_kind,scope_id,org_id,actor_id,kind,state,intent_hash,attempts,max_attempts,last_error_code,created_at,updated_at'
PAYLOAD_INSERT='id,scope_kind,scope_id,org_id,key_reference,ciphertext'
JOB_INSERT='id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key,private_payload_id,intent_hash'
OUTBOX_INSERT='id,scope_kind,scope_id,job_id,event_kind,dedup_key'


def upgrade():
    op.execute("ALTER TABLE wpl.jobs ADD COLUMN intent_hash char(64) CHECK (intent_hash IS NULL OR intent_hash ~ '^[0-9a-f]{64}$')")
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for function in FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION wpl.{function} FROM PUBLIC,wpl_app,wpl_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{function} TO wpl_app')
    op.execute("""CREATE POLICY tenant_payload_insert ON wpl.secret_payloads FOR INSERT TO wpl_app
        WITH CHECK (wpl.payload_enqueue_allowed(org_id,scope_kind,scope_id) AND owner_user_id IS NULL
          AND key_reference ~ '^[A-Za-z0-9_.:/-]{1,128}$' AND octet_length(ciphertext) BETWEEN 34 AND 32800
          AND substring(ciphertext FROM 1 FOR 4)=decode('57504c31','hex'))""")
    op.execute(f'GRANT INSERT ({PAYLOAD_INSERT}) ON wpl.secret_payloads TO wpl_app')
    op.execute("""CREATE POLICY tenant_jobs_read ON wpl.jobs FOR SELECT TO wpl_app
        USING (intent_hash IS NOT NULL AND kind='deliver_invitation'
          AND wpl.job_read_allowed(actor_id,org_id,scope_kind,scope_id))""")
    op.execute("""CREATE POLICY tenant_jobs_insert ON wpl.jobs FOR INSERT TO wpl_app
        WITH CHECK (wpl.job_enqueue_allowed(actor_id,org_id,scope_kind,scope_id,kind)
          AND intent_hash IS NOT NULL AND private_payload_id IS NOT NULL AND owner_user_id IS NULL
          AND state='queued' AND attempts=0 AND max_attempts=5 AND lease_generation=0
          AND lease_owner IS NULL AND lease_until IS NULL AND last_error_code IS NULL
          AND dedup_key='invitation:'||actor_id::text||':'||id::text)""")
    op.execute(f'GRANT SELECT ({JOB_COLUMNS}) ON wpl.jobs TO wpl_app')
    op.execute(f'GRANT INSERT ({JOB_INSERT}) ON wpl.jobs TO wpl_app')
    op.execute("""CREATE POLICY tenant_outbox_read ON wpl.outbox FOR SELECT TO wpl_app
        USING (wpl.outbox_read_allowed(job_id,scope_kind,scope_id))""")
    op.execute("""CREATE POLICY tenant_outbox_insert ON wpl.outbox FOR INSERT TO wpl_app
        WITH CHECK (state='pending' AND dispatched_at IS NULL
          AND wpl.outbox_enqueue_allowed(job_id,scope_kind,scope_id,event_kind,dedup_key))""")
    op.execute('GRANT SELECT ON wpl.outbox TO wpl_app')
    op.execute(f'GRANT INSERT ({OUTBOX_INSERT}) ON wpl.outbox TO wpl_app')
    op.execute("""CREATE POLICY tenant_job_audit_insert ON wpl.audit_events FOR INSERT TO wpl_app
        WITH CHECK (action='job_enqueued' AND target_type='job' AND reason='Invitation delivery queued'
          AND changes=jsonb_build_object('job_kind','deliver_invitation','delivery_status','pending_integration')
          AND wpl.job_audit_allowed(org_id,actor_id,target_id))""")


def downgrade():
    op.execute('DROP POLICY tenant_job_audit_insert ON wpl.audit_events')
    op.execute(f'REVOKE INSERT ({OUTBOX_INSERT}) ON wpl.outbox FROM wpl_app')
    op.execute('REVOKE SELECT ON wpl.outbox FROM wpl_app')
    op.execute('DROP POLICY tenant_outbox_insert ON wpl.outbox')
    op.execute('DROP POLICY tenant_outbox_read ON wpl.outbox')
    op.execute(f'REVOKE INSERT ({JOB_INSERT}) ON wpl.jobs FROM wpl_app')
    op.execute(f'REVOKE SELECT ({JOB_COLUMNS}) ON wpl.jobs FROM wpl_app')
    op.execute('DROP POLICY tenant_jobs_insert ON wpl.jobs')
    op.execute('DROP POLICY tenant_jobs_read ON wpl.jobs')
    op.execute(f'REVOKE INSERT ({PAYLOAD_INSERT}) ON wpl.secret_payloads FROM wpl_app')
    op.execute('DROP POLICY tenant_payload_insert ON wpl.secret_payloads')
    for function in reversed(FUNCTIONS):op.execute(f'DROP FUNCTION wpl.{function}')
    op.execute('ALTER TABLE wpl.jobs DROP COLUMN intent_hash')
