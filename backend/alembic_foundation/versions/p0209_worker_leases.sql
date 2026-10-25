CREATE FUNCTION wpl.delivery_actor_allowed(actor uuid,org uuid) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.users u
        JOIN wpl.organization_memberships m ON m.user_id=u.id
        JOIN wpl.organizations o ON o.id=m.org_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id
        WHERE u.id=actor AND u.global_state='active' AND o.id=org AND o.status='active'
          AND m.status='active' AND r.role='admin')
$$
-- statement --
CREATE OR REPLACE FUNCTION wpl.tenant_admin(org uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.ctx_scope()='tenant' AND org=wpl.ctx_uuid('wpl.org_id')
        AND wpl.delivery_actor_allowed(wpl.ctx_uuid('wpl.actor_id'),org)
$$
-- statement --
CREATE FUNCTION wpl.claim_deliveries(worker uuid,batch_size integer,lease_seconds integer)
RETURNS TABLE(job_id uuid,actor_id uuid,org_id uuid,lease_generation bigint,lease_until timestamptz,attempts integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE; moment timestamptz; next_state varchar; next_error varchar;
BEGIN
    IF worker IS NULL OR worker='00000000-0000-0000-0000-000000000000'::uuid
       OR batch_size IS NULL OR batch_size<1 OR batch_size>20
       OR lease_seconds IS NULL OR lease_seconds<5 OR lease_seconds>300 THEN
        RAISE EXCEPTION 'Invalid worker claim bounds' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT j.* FROM wpl.jobs j
        WHERE j.kind='deliver_invitation' AND j.scope_kind='tenant' AND j.scope_id=j.org_id
          AND j.owner_user_id IS NULL AND j.intent_hash IS NOT NULL AND j.private_payload_id IS NOT NULL
          AND ((j.state='queued' AND j.available_at<=clock_timestamp())
               OR (j.state='running' AND j.lease_until<=clock_timestamp()))
          AND EXISTS(SELECT 1 FROM wpl.outbox o WHERE o.job_id=j.id AND o.scope_kind=j.scope_kind
               AND o.scope_id=j.scope_id AND o.event_kind='delivery_requested' AND o.dedup_key='delivery:'||j.id::text)
        ORDER BY j.available_at,j.created_at,j.id LIMIT batch_size FOR UPDATE OF j SKIP LOCKED
    LOOP
        moment:=clock_timestamp(); next_state:='running'; next_error:=NULL;
        IF NOT wpl.delivery_actor_allowed(item.actor_id,item.org_id) THEN
            next_state:='cancelled'; next_error:='actor_not_authorized';
        ELSIF item.attempts>=item.max_attempts THEN
            next_state:='dead'; next_error:='attempts_exhausted';
        END IF;
        UPDATE wpl.jobs j SET state=next_state,
            lease_owner=CASE WHEN next_state='running' THEN worker ELSE NULL END,
            lease_generation=j.lease_generation+1,
            lease_until=CASE WHEN next_state='running' THEN moment+make_interval(secs=>lease_seconds) ELSE NULL END,
            attempts=j.attempts+CASE WHEN next_state='running' THEN 1 ELSE 0 END,
            last_error_code=next_error,updated_at=moment WHERE j.id=item.id RETURNING j.* INTO item;
        UPDATE wpl.outbox o SET state='dispatched',dispatched_at=moment
            WHERE o.job_id=item.id AND o.scope_kind=item.scope_kind AND o.scope_id=item.scope_id
              AND o.event_kind='delivery_requested' AND o.dedup_key='delivery:'||item.id::text AND o.state='pending';
        INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
            VALUES(gen_random_uuid(),item.actor_id,item.org_id,
                CASE WHEN next_state='running' THEN 'job_claimed' ELSE 'job_'||next_state END,
                'Worker lease decision','job',item.id,jsonb_build_object('worker_id',worker,
                'lease_generation',item.lease_generation,'attempt',item.attempts,'state',next_state,'error_code',next_error));
        IF next_state='running' THEN
            job_id:=item.id; actor_id:=item.actor_id; org_id:=item.org_id;
            lease_generation:=item.lease_generation; lease_until:=item.lease_until; attempts:=item.attempts;
            RETURN NEXT;
        END IF;
    END LOOP;
END
$$
-- statement --
CREATE FUNCTION wpl.renew_delivery(job uuid,worker uuid,generation bigint,lease_seconds integer)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE; moment timestamptz;
BEGIN
    IF job IS NULL OR worker IS NULL OR worker='00000000-0000-0000-0000-000000000000'::uuid
       OR generation IS NULL OR generation<1 OR lease_seconds IS NULL OR lease_seconds<5 OR lease_seconds>300 THEN
        RAISE EXCEPTION 'Invalid worker lease bounds' USING ERRCODE='22023';
    END IF;
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    moment:=clock_timestamp();
    IF NOT FOUND THEN RETURN false; END IF;
    IF item.kind<>'deliver_invitation' OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=moment THEN
        RETURN false;
    END IF;
    IF NOT wpl.delivery_actor_allowed(item.actor_id,item.org_id) THEN RETURN false; END IF;
    UPDATE wpl.jobs j SET lease_until=GREATEST(j.lease_until,moment+make_interval(secs=>lease_seconds)),updated_at=moment WHERE j.id=job;
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),item.actor_id,item.org_id,'job_lease_renewed','Worker lease renewed','job',item.id,
            jsonb_build_object('worker_id',worker,'lease_generation',generation));
    RETURN true;
END
$$
