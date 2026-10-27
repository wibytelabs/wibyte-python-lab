CREATE FUNCTION wpl.job_delivery_actor_allowed(actor uuid,org uuid,job_kind varchar)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,wpl AS $$
    SELECT CASE job_kind WHEN 'deliver_invitation' THEN wpl.delivery_actor_allowed(actor,org)
        WHEN 'deliver_primary_invitation' THEN EXISTS(SELECT 1 FROM wpl.users u
            JOIN wpl.platform_roles r ON r.user_id=u.id
            JOIN wpl.organizations o ON o.id=org
            WHERE u.id=actor AND u.global_state='active' AND r.capability='orgs'
              AND (r.expires_at IS NULL OR r.expires_at>statement_timestamp()) AND o.status='pending')
        ELSE false END
$$
-- statement --
CREATE OR REPLACE FUNCTION wpl.claim_deliveries(worker uuid,batch_size integer,lease_seconds integer)
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
        WHERE j.kind IN ('deliver_invitation','deliver_primary_invitation') AND j.scope_kind='tenant' AND j.scope_id=j.org_id
          AND j.owner_user_id IS NULL AND j.intent_hash IS NOT NULL AND j.private_payload_id IS NOT NULL
          AND ((j.state='queued' AND j.available_at<=clock_timestamp())
               OR (j.state='running' AND j.lease_until<=clock_timestamp()))
          AND EXISTS(SELECT 1 FROM wpl.outbox o WHERE o.job_id=j.id AND o.scope_kind=j.scope_kind
               AND o.scope_id=j.scope_id AND o.event_kind='delivery_requested' AND o.dedup_key='delivery:'||j.id::text)
        ORDER BY j.available_at,j.created_at,j.id LIMIT batch_size FOR UPDATE OF j SKIP LOCKED
    LOOP
        moment:=clock_timestamp(); next_state:='running'; next_error:=NULL;
        IF NOT wpl.job_delivery_actor_allowed(item.actor_id,item.org_id,item.kind) THEN
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
CREATE OR REPLACE FUNCTION wpl.renew_delivery(job uuid,worker uuid,generation bigint,lease_seconds integer)
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
    IF item.kind NOT IN ('deliver_invitation','deliver_primary_invitation') OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=moment THEN
        RETURN false;
    END IF;
    IF NOT wpl.job_delivery_actor_allowed(item.actor_id,item.org_id,item.kind) THEN RETURN false; END IF;
    UPDATE wpl.jobs j SET lease_until=GREATEST(j.lease_until,moment+make_interval(secs=>lease_seconds)),updated_at=moment WHERE j.id=job;
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),item.actor_id,item.org_id,'job_lease_renewed','Worker lease renewed','job',item.id,
            jsonb_build_object('worker_id',worker,'lease_generation',generation));
    RETURN true;
END
$$
-- statement --
CREATE FUNCTION wpl.delivery_payload(job uuid,worker uuid,generation bigint)
RETURNS TABLE(actor_id uuid,org_id uuid,payload_id uuid,key_reference varchar,ciphertext bytea,kind varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE;
BEGIN
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF worker IS NULL OR generation IS NULL OR item.kind NOT IN ('deliver_invitation','deliver_primary_invitation')
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=clock_timestamp()
       OR NOT wpl.job_delivery_actor_allowed(item.actor_id,item.org_id,item.kind) THEN RETURN; END IF;
    RETURN QUERY SELECT item.actor_id,item.org_id,p.id,p.key_reference,p.ciphertext,item.kind
        FROM wpl.secret_payloads p WHERE p.id=item.private_payload_id AND p.scope_kind='tenant'
          AND p.scope_id=item.org_id AND p.org_id=item.org_id AND p.owner_user_id IS NULL;
END
$$
-- statement --
CREATE OR REPLACE FUNCTION wpl.authorize_delivery_target(job uuid,worker uuid,generation bigint,invitation uuid,recipient varchar,token_digest bytea,intent varchar)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE;
BEGIN
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF worker IS NULL OR generation IS NULL OR item.kind NOT IN ('deliver_invitation','deliver_primary_invitation')
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=clock_timestamp()
       OR NOT wpl.job_delivery_actor_allowed(item.actor_id,item.org_id,item.kind) THEN RETURN false; END IF;
    IF intent IS NULL OR item.intent_hash<>intent THEN RETURN false; END IF;
    RETURN EXISTS(SELECT 1 FROM wpl.invitations i
        JOIN wpl.organization_memberships m ON m.org_id=i.org_id AND m.id=i.membership_id
        WHERE i.id=invitation AND i.org_id=item.org_id AND i.status='pending' AND m.status='invite_pending'
          AND i.expires_at>clock_timestamp() AND i.intended_email=recipient AND i.token_hash=token_digest
          AND (item.kind<>'deliver_primary_invitation' OR EXISTS(SELECT 1 FROM wpl.organizations o
            JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id
            WHERE o.id=item.org_id AND o.status='pending' AND o.primary_admin_membership_id=m.id
              AND m.user_id IS NULL AND m.invitation_id=i.id AND r.role='admin'
              AND i.intended_roles=ARRAY['admin']::varchar[])));
END
$$
-- statement --
CREATE OR REPLACE FUNCTION wpl.finish_delivery(job uuid,worker uuid,generation bigint,outcome varchar,error_code varchar)
RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE; moment timestamptz; result_state varchar; result_error varchar; delay_seconds integer;
BEGIN
    IF outcome IS NULL OR outcome NOT IN ('success','retry','cancel')
       OR (outcome='success' AND error_code IS NOT NULL)
       OR (outcome='retry' AND (error_code IS NULL OR error_code NOT IN ('transport_unavailable','key_unavailable')))
       OR (outcome='cancel' AND (error_code IS NULL OR error_code NOT IN ('payload_invalid','target_unavailable'))) THEN
        RAISE EXCEPTION 'Invalid delivery transition' USING ERRCODE='22023';
    END IF;
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    moment:=clock_timestamp();
    IF worker IS NULL OR generation IS NULL OR item.kind NOT IN ('deliver_invitation','deliver_primary_invitation')
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=moment THEN RETURN NULL; END IF;
    result_error:=error_code; delay_seconds:=0;
    IF NOT wpl.job_delivery_actor_allowed(item.actor_id,item.org_id,item.kind) THEN
        result_state:='cancelled'; result_error:='actor_not_authorized';
    ELSIF outcome='success' THEN result_state:='succeeded';
    ELSIF outcome='cancel' THEN result_state:='cancelled';
    ELSIF item.attempts>=item.max_attempts THEN result_state:='dead';
    ELSE result_state:='queued'; delay_seconds:=LEAST(300,5*power(2,LEAST(9,GREATEST(0,item.attempts-1))))::integer;
    END IF;
    UPDATE wpl.jobs j SET state=result_state,lease_owner=NULL,lease_until=NULL,
        available_at=CASE WHEN result_state='queued' THEN moment+make_interval(secs=>delay_seconds) ELSE j.available_at END,
        last_error_code=result_error,updated_at=moment WHERE j.id=item.id;
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),item.actor_id,item.org_id,
            CASE WHEN result_state='queued' THEN 'job_retry_scheduled' ELSE 'job_'||result_state END,
            'Worker delivery transition','job',item.id,jsonb_build_object('worker_id',worker,
                'lease_generation',generation,'attempt',item.attempts,'state',result_state,
                'error_code',result_error,'retry_delay_seconds',delay_seconds));
    RETURN result_state;
END
$$
