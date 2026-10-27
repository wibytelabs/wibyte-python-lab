CREATE FUNCTION wpl.primary_transfer_allowed(p_org uuid) RETURNS boolean
LANGUAGE sql VOLATILE SET search_path=pg_catalog,wpl AS $$
    SELECT p_org=wpl.ctx_uuid('wpl.org_id') AND (
        (wpl.tenant_admin(p_org) AND EXISTS(SELECT 1 FROM wpl.organizations o
            JOIN wpl.organization_memberships m ON m.org_id=o.id AND m.id=o.primary_admin_membership_id
            WHERE o.id=p_org AND m.user_id=wpl.ctx_uuid('wpl.actor_id')))
        OR (wpl.recovery_target(p_org) AND EXISTS(SELECT 1 FROM wpl.organizations o
            WHERE o.id=p_org AND o.status='recovery_required')))
$$
-- statement --
CREATE FUNCTION wpl.preview_primary_transfer(p_org uuid,p_target uuid,p_expected integer,
    p_reason varchar,p_transfer uuid,p_confirmation_hash bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE item wpl.organizations%ROWTYPE; prior wpl.primary_admin_transfers%ROWTYPE;
    deadline timestamptz; actor uuid:=wpl.ctx_uuid('wpl.actor_id'); mode text:=wpl.ctx_scope();
BEGIN
    IF NOT COALESCE(wpl.primary_transfer_allowed(p_org),false) THEN
        RETURN jsonb_build_object('error','forbidden'); END IF;
    IF p_expected IS NULL OR p_expected<1 OR p_target IS NULL OR p_transfer IS NULL
       OR p_reason IS NULL OR length(trim(p_reason)) NOT BETWEEN 5 AND 1000
       OR p_reason ~ '[[:cntrl:]]' OR p_confirmation_hash IS NULL OR octet_length(p_confirmation_hash)<>32 THEN
        RETURN jsonb_build_object('error','invalid_preview'); END IF;
    SELECT o.* INTO item FROM wpl.organizations o WHERE o.id=p_org FOR UPDATE;
    IF NOT COALESCE(wpl.primary_transfer_allowed(p_org),false) THEN
        RETURN jsonb_build_object('error','forbidden'); END IF;
    IF item.version<>p_expected THEN RETURN jsonb_build_object('error','version_conflict'); END IF;
    IF p_target=item.primary_admin_membership_id OR NOT EXISTS(
        SELECT 1 FROM wpl.organization_memberships m JOIN wpl.users u ON u.id=m.user_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='admin'
        WHERE m.org_id=p_org AND m.id=p_target AND m.status='active' AND u.global_state='active') THEN
        RETURN jsonb_build_object('error','target_ineligible'); END IF;
    SELECT t.* INTO prior FROM wpl.primary_admin_transfers t WHERE t.org_id=p_org AND t.status='preview';
    IF FOUND AND prior.expires_at>clock_timestamp() AND prior.actor_id<>actor THEN
        RETURN jsonb_build_object('error','preview_in_progress'); END IF;
    UPDATE wpl.primary_admin_transfers t SET status=CASE WHEN t.expires_at<=clock_timestamp() THEN 'expired' ELSE 'cancelled' END
        WHERE t.org_id=p_org AND t.status='preview';
    deadline:=clock_timestamp()+interval '5 minutes';
    INSERT INTO wpl.primary_admin_transfers(id,org_id,actor_id,from_membership_id,to_membership_id,
        expected_version,confirmation_hash,status,reason,expires_at,authorization_scope)
        VALUES(p_transfer,p_org,actor,item.primary_admin_membership_id,p_target,p_expected,
            p_confirmation_hash,'preview',trim(p_reason),deadline,mode);
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),actor,p_org,'primary_transfer_previewed',trim(p_reason),'primary_transfer',p_transfer,
            jsonb_build_object('from_membership_id',item.primary_admin_membership_id,'to_membership_id',p_target,
                'expected_version',p_expected,'authorization_scope',mode));
    RETURN jsonb_build_object('transfer_id',p_transfer,'org_id',p_org,
        'from_membership_id',item.primary_admin_membership_id,'to_membership_id',p_target,
        'expected_version',p_expected,'expires_at',deadline,'authorization_scope',mode);
END
$$
