CREATE FUNCTION wpl.primary_transfer_receipt_allowed(p_org uuid) RETURNS boolean
LANGUAGE sql VOLATILE SET search_path=pg_catalog,wpl AS $$
    SELECT p_org=wpl.ctx_uuid('wpl.org_id') AND COALESCE(
        (wpl.ctx_scope()='tenant' AND wpl.tenant_admin(p_org)) OR wpl.recovery_target(p_org),false)
$$
-- statement --
CREATE FUNCTION wpl.confirm_primary_transfer(p_org uuid,p_transfer uuid,p_expected integer,
    p_confirmation_hash bytea,p_job uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.organizations%ROWTYPE; transfer wpl.primary_admin_transfers%ROWTYPE;
    actor uuid:=wpl.ctx_uuid('wpl.actor_id'); mode text:=wpl.ctx_scope(); timing text;
    from_user uuid; to_user uuid; result_body jsonb; intent jsonb;
BEGIN
    IF NOT COALESCE(wpl.primary_transfer_receipt_allowed(p_org),false) THEN
        RETURN jsonb_build_object('error','forbidden'); END IF;
    IF p_transfer IS NULL OR p_expected IS NULL OR p_expected<1 OR p_job IS NULL
        OR p_confirmation_hash IS NULL OR octet_length(p_confirmation_hash)<>32 THEN
        RETURN jsonb_build_object('error','invalid_confirmation'); END IF;
    timing:=current_setting('wpl.auth_time',true);
    IF timing IS NULL OR timing !~ '^[0-9]{1,12}$' THEN
        RETURN jsonb_build_object('error','recent_auth_required'); END IF;
    IF timing::numeric NOT BETWEEN extract(epoch FROM clock_timestamp())-300 AND extract(epoch FROM clock_timestamp())+30 THEN
        RETURN jsonb_build_object('error','recent_auth_required'); END IF;
    SELECT t.* INTO transfer FROM wpl.primary_admin_transfers t WHERE t.org_id=p_org AND t.id=p_transfer;
    IF NOT FOUND OR transfer.actor_id<>actor OR transfer.authorization_scope<>mode
       OR transfer.expected_version<>p_expected OR transfer.confirmation_hash<>p_confirmation_hash THEN
        RETURN jsonb_build_object('error','invalid_confirmation'); END IF;
    SELECT m.user_id INTO from_user FROM wpl.organization_memberships m WHERE m.org_id=p_org AND m.id=transfer.from_membership_id;
    SELECT m.user_id INTO to_user FROM wpl.organization_memberships m WHERE m.org_id=p_org AND m.id=transfer.to_membership_id;
    -- Lock identities before the org: security suspension locks its user first
    -- and then updates affected organizations. This also closes the target-global
    -- state race at the designation boundary without an org/user lock inversion.
    PERFORM u.id FROM wpl.users u WHERE u.id IN (actor,from_user,to_user) ORDER BY u.id FOR SHARE;
    IF mode='platform' THEN
        PERFORM r.user_id FROM wpl.platform_roles r WHERE r.user_id=actor AND r.capability='recovery' FOR SHARE;
    END IF;
    SELECT o.* INTO item FROM wpl.organizations o WHERE o.id=p_org FOR UPDATE;
    SELECT t.* INTO transfer FROM wpl.primary_admin_transfers t WHERE t.org_id=p_org AND t.id=p_transfer FOR UPDATE;
    IF NOT COALESCE(wpl.primary_transfer_receipt_allowed(p_org),false) THEN
        RETURN jsonb_build_object('error','forbidden'); END IF;
    -- Long lock waits cannot extend the five-minute authentication window.
    IF timing::numeric NOT BETWEEN extract(epoch FROM clock_timestamp())-300 AND extract(epoch FROM clock_timestamp())+30 THEN
        RETURN jsonb_build_object('error','recent_auth_required'); END IF;
    IF transfer.actor_id<>actor OR transfer.authorization_scope<>mode OR transfer.expected_version<>p_expected
       OR transfer.confirmation_hash<>p_confirmation_hash THEN RETURN jsonb_build_object('error','invalid_confirmation'); END IF;
    IF transfer.status='completed' AND transfer.result IS NOT NULL THEN
        RETURN jsonb_build_object('receipt',transfer.result,'replayed',true); END IF;
    IF NOT COALESCE(wpl.primary_transfer_allowed(p_org),false) THEN
        RETURN jsonb_build_object('error','forbidden'); END IF;
    IF transfer.status<>'preview' OR transfer.expires_at<=clock_timestamp()
       OR transfer.from_membership_id<>item.primary_admin_membership_id THEN
        RETURN jsonb_build_object('error','invalid_confirmation'); END IF;
    IF item.version<>p_expected THEN RETURN jsonb_build_object('error','version_conflict'); END IF;
    IF NOT EXISTS(SELECT 1 FROM wpl.organization_memberships m JOIN wpl.users u ON u.id=m.user_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='admin'
        WHERE m.org_id=p_org AND m.id=transfer.to_membership_id AND m.status='active' AND u.global_state='active') THEN
        RETURN jsonb_build_object('error','target_ineligible'); END IF;
    IF transfer.reason IS NULL OR length(trim(transfer.reason)) NOT BETWEEN 5 AND 1000 THEN
        RETURN jsonb_build_object('error','invalid_confirmation'); END IF;
    UPDATE wpl.organizations o SET primary_admin_membership_id=transfer.to_membership_id,
        status=CASE WHEN mode='platform' THEN 'active' ELSE o.status END
        WHERE o.id=p_org RETURNING o.* INTO item;
    -- The notification contains no credential, token or recipient address. Its
    -- immutable from/to IDs remain in the private transfer row. Delivery integration
    -- is separate; existing invitation workers deliberately ignore this job kind.
    intent:=jsonb_build_object('org_id',p_org,'transfer_id',p_transfer,'actor_id',actor,
        'from_membership_id',transfer.from_membership_id,'to_membership_id',transfer.to_membership_id,
        'authorization_scope',mode,'kind','notify_primary_transfer');
    INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key,intent_hash)
        VALUES(p_job,'tenant',p_org,p_org,actor,'notify_primary_transfer','primary_transfer:'||p_transfer::text,
            encode(sha256(convert_to(intent::text,'UTF8')),'hex'));
    INSERT INTO wpl.outbox(id,scope_kind,scope_id,job_id,event_kind,dedup_key)
        VALUES(gen_random_uuid(),'tenant',p_org,p_job,'primary_transfer_notification_requested','primary_transfer:'||p_transfer::text);
    result_body:=jsonb_build_object('transfer_id',p_transfer,'org_id',p_org,'primary_admin_membership_id',item.primary_admin_membership_id,
        'version',item.version,'access_epoch',item.access_epoch,'status',item.status,
        'job_id',p_job,'delivery_status','pending_integration');
    UPDATE wpl.primary_admin_transfers t SET status='completed',completed_at=clock_timestamp(),result=result_body WHERE t.id=p_transfer;
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),actor,p_org,CASE WHEN mode='platform' THEN 'primary_recovered' ELSE 'primary_transferred' END,
            transfer.reason,'organization',p_org,(intent-'kind')||jsonb_build_object('prior_version',p_expected,'version',item.version));
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),actor,p_org,'job_enqueued','Primary change notification queued','job',p_job,
            jsonb_build_object('kind','notify_primary_transfer','transfer_id',p_transfer,'delivery_status','pending_integration'));
    RETURN jsonb_build_object('receipt',result_body,'replayed',false);
END
$$
