-- Internal context readers are deliberately not executable by runtime roles.
CREATE FUNCTION wpl.ctx_uuid(setting_name text) RETURNS uuid
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,wpl AS $$
DECLARE value text := current_setting(setting_name,true);
BEGIN
    IF value IS NULL OR value !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
        RETURN NULL;
    END IF;
    RETURN value::uuid;
END $$
-- statement --
CREATE FUNCTION wpl.ctx_scope() RETURNS text LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT CASE WHEN wpl.ctx_uuid('wpl.actor_id') IS NOT NULL
        AND ((current_setting('wpl.scope_kind',true) IN ('global','personal') AND NULLIF(current_setting('wpl.org_id',true),'') IS NULL)
          OR (current_setting('wpl.scope_kind',true)='tenant' AND wpl.ctx_uuid('wpl.org_id') IS NOT NULL)
          OR (current_setting('wpl.scope_kind',true)='platform' AND (NULLIF(current_setting('wpl.org_id',true),'') IS NULL OR wpl.ctx_uuid('wpl.org_id') IS NOT NULL)))
        THEN current_setting('wpl.scope_kind',true) ELSE NULL END
$$
-- statement --
CREATE FUNCTION wpl.actor_active() RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.users u WHERE u.id=wpl.ctx_uuid('wpl.actor_id') AND u.global_state='active')
$$
-- statement --
CREATE FUNCTION wpl.platform_capability(cap text) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.ctx_scope()='platform' AND wpl.actor_active() AND EXISTS(
        SELECT 1 FROM wpl.platform_roles r WHERE r.user_id=wpl.ctx_uuid('wpl.actor_id')
        AND r.capability=cap AND (r.expires_at IS NULL OR r.expires_at>statement_timestamp()))
$$
-- statement --
CREATE FUNCTION wpl.tenant_member(org uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.ctx_scope()='tenant' AND org=wpl.ctx_uuid('wpl.org_id') AND wpl.actor_active()
        AND EXISTS(SELECT 1 FROM wpl.organizations o JOIN wpl.organization_memberships m ON m.org_id=o.id
            WHERE o.id=org AND o.status='active' AND m.user_id=wpl.ctx_uuid('wpl.actor_id') AND m.status='active')
$$
-- statement --
CREATE FUNCTION wpl.tenant_admin(org uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.tenant_member(org) AND EXISTS(SELECT 1 FROM wpl.organization_memberships m
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id
        WHERE m.org_id=org AND m.user_id=wpl.ctx_uuid('wpl.actor_id') AND m.status='active' AND r.role='admin')
$$
-- statement --
CREATE FUNCTION wpl.assigned_cohort(org uuid,cohort uuid,required_role text) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.tenant_member(org) AND EXISTS(SELECT 1 FROM wpl.cohorts c
        JOIN wpl.cohort_memberships cm ON cm.org_id=c.org_id AND cm.cohort_id=c.id
        JOIN wpl.organization_memberships m ON m.org_id=cm.org_id AND m.id=cm.membership_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role=cm.role
        WHERE c.org_id=org AND c.id=cohort AND c.status IN ('active','archived')
          AND cm.status='active' AND m.status='active' AND m.user_id=wpl.ctx_uuid('wpl.actor_id')
          AND (required_role IS NULL OR cm.role=required_role))
$$
-- statement --
CREATE FUNCTION wpl.recovery_target(org uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,wpl AS $$
    SELECT org=wpl.ctx_uuid('wpl.org_id') AND wpl.platform_capability('recovery')
$$
-- statement --
-- Only the boolean policy entry points below receive app EXECUTE. Their owner
-- reads private tables without recursive RLS; runtime roles remain non-owners.
CREATE FUNCTION wpl.read_org(org uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.organizations o WHERE o.id=org) AND (
        wpl.tenant_member(org) OR wpl.recovery_target(org)
        OR (wpl.platform_capability('orgs') AND (wpl.ctx_uuid('wpl.org_id') IS NULL OR org=wpl.ctx_uuid('wpl.org_id')))
        OR (wpl.ctx_scope()='global' AND EXISTS(SELECT 1 FROM wpl.organization_memberships m
            WHERE m.org_id=org AND m.user_id=wpl.ctx_uuid('wpl.actor_id'))))
$$
-- statement --
CREATE FUNCTION wpl.read_member(org uuid,member uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.organization_memberships target WHERE target.org_id=org AND target.id=member
        AND (wpl.recovery_target(org)
        OR (wpl.ctx_scope()='global' AND target.user_id=wpl.ctx_uuid('wpl.actor_id'))
        OR (wpl.tenant_member(org) AND (wpl.tenant_admin(org) OR target.user_id=wpl.ctx_uuid('wpl.actor_id')
            OR (target.status='active' AND EXISTS(SELECT 1 FROM wpl.cohort_memberships cm
                WHERE cm.org_id=org AND cm.membership_id=target.id AND cm.status='active'
                  AND wpl.assigned_cohort(org,cm.cohort_id,'instructor')))))))
$$
-- statement --
CREATE FUNCTION wpl.read_user(subject uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    -- SELECT policy must also accept the proposed own row during ON CONFLICT.
    -- Existence is enforced by the outer table scan, not by this permission test.
    SELECT wpl.ctx_scope() IS NOT NULL
        AND (subject=wpl.ctx_uuid('wpl.actor_id') OR wpl.platform_capability('users')
          OR EXISTS(SELECT 1 FROM wpl.organization_memberships m WHERE m.user_id=subject AND wpl.read_member(m.org_id,m.id)))
$$
-- statement --
CREATE FUNCTION wpl.read_cohort(org uuid,cohort uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.cohorts c WHERE c.org_id=org AND c.id=cohort)
        AND (wpl.tenant_admin(org) OR wpl.assigned_cohort(org,cohort,NULL))
$$
-- statement --
CREATE FUNCTION wpl.read_assignment(org uuid,cohort uuid,member uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.read_cohort(org,cohort) AND (wpl.tenant_admin(org) OR wpl.assigned_cohort(org,cohort,'instructor')
        OR EXISTS(SELECT 1 FROM wpl.organization_memberships m WHERE m.org_id=org AND m.id=member
            AND m.status='active' AND m.user_id=wpl.ctx_uuid('wpl.actor_id')))
$$
-- statement --
CREATE FUNCTION wpl.read_platform_role(subject uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.actor_active() AND ((wpl.ctx_scope()='global' AND subject=wpl.ctx_uuid('wpl.actor_id'))
        OR (wpl.ctx_scope()='platform' AND subject=wpl.ctx_uuid('wpl.actor_id')))
$$
