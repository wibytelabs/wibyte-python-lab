"""Persist explicit simulated/provider acknowledgement, never infer delivery."""
from alembic import op
revision='p0211_delivery_execution'
down_revision='p0210_worker_transitions'
branch_labels=None
depends_on=None
FUNCTION='acknowledge_delivery(uuid,uuid,bigint,character varying)'


def upgrade():
    op.execute("""ALTER TABLE wpl.jobs ADD COLUMN delivery_status varchar(24) NOT NULL
        DEFAULT 'pending_integration' CHECK (delivery_status IN ('pending_integration','simulated','provider_accepted'))""")
    op.execute('GRANT SELECT (delivery_status) ON wpl.jobs TO wpl_app')
    op.execute('''CREATE FUNCTION wpl.acknowledge_delivery(job uuid,worker uuid,generation bigint,ack varchar)
        RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        DECLARE result_state varchar;
        BEGIN
            IF ack IS NULL OR ack NOT IN ('simulated','provider_accepted') THEN
                RAISE EXCEPTION 'Invalid delivery acknowledgement' USING ERRCODE='22023';
            END IF;
            result_state:=wpl.finish_delivery(job,worker,generation,'success',NULL);
            IF result_state='succeeded' THEN
                UPDATE wpl.jobs j SET delivery_status=ack WHERE j.id=job;
                INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
                    SELECT gen_random_uuid(),j.actor_id,j.org_id,'job_acknowledged','Delivery adapter acknowledged',
                        'job',j.id,jsonb_build_object('worker_id',worker,'lease_generation',generation,'delivery_status',ack)
                    FROM wpl.jobs j WHERE j.id=job;
            END IF;
            RETURN result_state;
        END
        $$''')
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{FUNCTION} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{FUNCTION} TO wpl_worker')


def downgrade():
    op.execute(f'DROP FUNCTION wpl.{FUNCTION}')
    op.execute('REVOKE SELECT (delivery_status) ON wpl.jobs FROM wpl_app')
    op.execute('ALTER TABLE wpl.jobs DROP COLUMN delivery_status')
