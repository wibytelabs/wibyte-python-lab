CREATE FUNCTION wpl.delivery_target_allowed(org uuid,invitation uuid,recipient varchar,token_digest bytea)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT wpl.tenant_admin(org) AND EXISTS(SELECT 1 FROM wpl.invitations i
        JOIN wpl.organization_memberships m ON m.org_id=i.org_id AND m.id=i.membership_id
        WHERE i.org_id=org AND i.id=invitation AND i.status='pending' AND i.expires_at>statement_timestamp()
          AND i.intended_email=recipient AND i.token_hash=token_digest AND m.status='invite_pending')
$$
-- statement --
CREATE FUNCTION wpl.payload_enqueue_allowed(org uuid,scope varchar,scope_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT scope='tenant' AND scope_uuid=org AND wpl.tenant_admin(org)
$$
-- statement --
CREATE FUNCTION wpl.job_enqueue_allowed(actor uuid,org uuid,scope varchar,scope_uuid uuid,job_kind varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT actor=wpl.ctx_uuid('wpl.actor_id') AND job_kind='deliver_invitation'
        AND wpl.payload_enqueue_allowed(org,scope,scope_uuid)
$$
-- statement --
CREATE FUNCTION wpl.job_read_allowed(actor uuid,org uuid,scope varchar,scope_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT scope='tenant' AND scope_uuid=org AND wpl.tenant_member(org)
        AND (actor=wpl.ctx_uuid('wpl.actor_id') OR wpl.tenant_admin(org))
$$
-- statement --
CREATE FUNCTION wpl.outbox_enqueue_allowed(job uuid,scope varchar,scope_uuid uuid,event varchar,dedup varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT scope='tenant' AND event='delivery_requested' AND dedup='delivery:'||job::text
        AND EXISTS(SELECT 1 FROM wpl.jobs j WHERE j.id=job AND j.scope_kind=scope AND j.scope_id=scope_uuid
          AND j.state='queued' AND j.intent_hash IS NOT NULL AND j.private_payload_id IS NOT NULL
          AND wpl.job_enqueue_allowed(j.actor_id,j.org_id,j.scope_kind,j.scope_id,j.kind))
$$
-- statement --
CREATE FUNCTION wpl.outbox_read_allowed(job uuid,scope varchar,scope_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT EXISTS(SELECT 1 FROM wpl.jobs j WHERE j.id=job AND j.scope_kind=scope AND j.scope_id=scope_uuid
        AND j.intent_hash IS NOT NULL AND j.kind='deliver_invitation'
        AND wpl.job_read_allowed(j.actor_id,j.org_id,j.scope_kind,j.scope_id))
$$
-- statement --
CREATE FUNCTION wpl.job_audit_allowed(org uuid,actor uuid,job uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
    SELECT actor=wpl.ctx_uuid('wpl.actor_id') AND wpl.tenant_admin(org)
      AND EXISTS(SELECT 1 FROM wpl.jobs j WHERE j.id=job AND j.org_id=org AND j.actor_id=actor
        AND j.kind='deliver_invitation' AND j.intent_hash IS NOT NULL AND j.state='queued')
$$
