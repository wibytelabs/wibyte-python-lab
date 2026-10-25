CREATE FUNCTION wpl.delivery_payload(job uuid,worker uuid,generation bigint)
RETURNS TABLE(actor_id uuid,org_id uuid,payload_id uuid,key_reference varchar,ciphertext bytea)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE;
BEGIN
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF worker IS NULL OR generation IS NULL OR item.kind<>'deliver_invitation'
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=clock_timestamp()
       OR NOT wpl.delivery_actor_allowed(item.actor_id,item.org_id) THEN RETURN; END IF;
    RETURN QUERY SELECT item.actor_id,item.org_id,p.id,p.key_reference,p.ciphertext
        FROM wpl.secret_payloads p WHERE p.id=item.private_payload_id AND p.scope_kind='tenant'
          AND p.scope_id=item.org_id AND p.org_id=item.org_id AND p.owner_user_id IS NULL;
END
$$
-- statement --
CREATE FUNCTION wpl.authorize_delivery_target(job uuid,worker uuid,generation bigint,invitation uuid,recipient varchar,token_digest bytea,intent varchar)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.jobs%ROWTYPE;
BEGIN
    SELECT j.* INTO item FROM wpl.jobs j WHERE j.id=job FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF worker IS NULL OR generation IS NULL OR item.kind<>'deliver_invitation'
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=clock_timestamp()
       OR NOT wpl.delivery_actor_allowed(item.actor_id,item.org_id) THEN RETURN false; END IF;
    IF intent IS NULL OR item.intent_hash<>intent THEN RETURN false; END IF;
    RETURN EXISTS(SELECT 1 FROM wpl.invitations i
        JOIN wpl.organization_memberships m ON m.org_id=i.org_id AND m.id=i.membership_id
        WHERE i.id=invitation AND i.org_id=item.org_id AND i.status='pending' AND m.status='invite_pending'
          AND i.expires_at>clock_timestamp() AND i.intended_email=recipient AND i.token_hash=token_digest);
END
$$
-- statement --
CREATE FUNCTION wpl.finish_delivery(job uuid,worker uuid,generation bigint,outcome varchar,error_code varchar)
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
    IF worker IS NULL OR generation IS NULL OR item.kind<>'deliver_invitation'
       OR item.scope_kind<>'tenant' OR item.scope_id<>item.org_id OR item.owner_user_id IS NOT NULL
       OR item.intent_hash IS NULL OR item.private_payload_id IS NULL OR item.state<>'running'
       OR item.lease_owner<>worker OR item.lease_generation<>generation OR item.lease_until<=moment THEN RETURN NULL; END IF;
    result_error:=error_code; delay_seconds:=0;
    IF NOT wpl.delivery_actor_allowed(item.actor_id,item.org_id) THEN
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
