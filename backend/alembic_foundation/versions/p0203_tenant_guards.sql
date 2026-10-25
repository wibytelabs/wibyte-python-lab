CREATE FUNCTION wpl.version_entity() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,wpl AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Entity identity is immutable';
    END IF;
    NEW.version := OLD.version+1;
    NEW.updated_at := clock_timestamp();
    NEW.access_epoch := OLD.access_epoch;
    IF (TG_TABLE_NAME='users' AND NEW.global_state IS DISTINCT FROM OLD.global_state) THEN
        NEW.access_epoch := OLD.access_epoch+1;
    END IF;
    RETURN NEW;
END;
$$
-- statement --
CREATE FUNCTION wpl.version_scoped_entity() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,wpl AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Entity identity is immutable';
    END IF;
    IF TG_TABLE_NAME IN ('cohorts','organization_memberships') THEN
        IF NEW.org_id IS DISTINCT FROM OLD.org_id THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Entity scope is immutable';
        END IF;
    END IF;
    NEW.version := OLD.version+1;
    NEW.updated_at := clock_timestamp();
    -- Counters can only advance, at most once per row mutation. Trigger-owned role
    -- and assignment changes request advancement; caller input cannot reset epochs.
    NEW.access_epoch := CASE WHEN NEW.access_epoch>OLD.access_epoch
        THEN OLD.access_epoch+1 ELSE OLD.access_epoch END;
    IF NEW.status IS DISTINCT FROM OLD.status THEN NEW.access_epoch := OLD.access_epoch+1; END IF;
    IF TG_TABLE_NAME='organizations' THEN
        IF NEW.primary_admin_membership_id IS DISTINCT FROM OLD.primary_admin_membership_id THEN
            NEW.access_epoch := OLD.access_epoch+1;
        END IF;
    ELSIF TG_TABLE_NAME='organization_memberships' THEN
        IF OLD.user_id IS NOT NULL AND NEW.user_id IS DISTINCT FROM OLD.user_id THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Verified membership identity is immutable';
        END IF;
        IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN NEW.access_epoch := OLD.access_epoch+1; END IF;
    END IF;
    RETURN NEW;
END;
$$
-- statement --
CREATE FUNCTION wpl.lock_membership_parents() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
DECLARE v_org uuid; v_member uuid; c record;
BEGIN
    IF TG_OP='UPDATE' AND NEW.org_id IS DISTINCT FROM OLD.org_id THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Membership scope is immutable';
    END IF;
    IF TG_OP='UPDATE' AND TG_TABLE_NAME='organization_roles' THEN
        IF NEW.membership_id IS DISTINCT FROM OLD.membership_id THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Role membership identity is immutable';
        END IF;
    END IF;
    v_org := COALESCE(NEW.org_id,OLD.org_id);
    IF TG_TABLE_NAME='organization_memberships' THEN v_member := COALESCE(NEW.id,OLD.id);
    ELSE v_member := COALESCE(NEW.membership_id,OLD.membership_id);
    END IF;
    -- A real parent UPDATE serializes competing writes even under repeatable read.
    UPDATE wpl.organizations SET version=version+1 WHERE id=v_org;
    FOR c IN SELECT DISTINCT cohort_id FROM wpl.cohort_memberships
             WHERE org_id=v_org AND membership_id=v_member ORDER BY cohort_id LOOP
        UPDATE wpl.cohorts SET version=version+1,access_epoch=access_epoch+1 WHERE org_id=v_org AND id=c.cohort_id;
    END LOOP;
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$
-- statement --
CREATE FUNCTION wpl.lock_cohort_parent() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
BEGIN
    IF TG_OP='UPDATE' AND (NEW.org_id,NEW.cohort_id,NEW.membership_id) IS DISTINCT FROM
        (OLD.org_id,OLD.cohort_id,OLD.membership_id) THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Cohort membership scope is immutable';
    END IF;
    UPDATE wpl.organizations SET version=version+1 WHERE id=COALESCE(NEW.org_id,OLD.org_id);
    UPDATE wpl.cohorts SET version=version+1,access_epoch=access_epoch+1
        WHERE org_id=COALESCE(NEW.org_id,OLD.org_id) AND id=COALESCE(NEW.cohort_id,OLD.cohort_id);
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$
-- statement --
CREATE FUNCTION wpl.check_primary() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
DECLARE o wpl.organizations%ROWTYPE; m record; v_org uuid;
BEGIN
    IF TG_TABLE_NAME='organizations' THEN v_org := NEW.id;
    ELSE v_org := COALESCE(NEW.org_id,OLD.org_id);
    END IF;
    SELECT * INTO o FROM wpl.organizations WHERE id=v_org;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT membership.status,membership.user_id,u.global_state INTO m
        FROM wpl.organization_memberships membership LEFT JOIN wpl.users u ON u.id=membership.user_id
        WHERE membership.org_id=o.id AND membership.id=o.primary_admin_membership_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23503',MESSAGE='Designated primary membership is missing';
    END IF;
    IF m.status NOT IN ('active','invite_pending') OR NOT EXISTS (
        SELECT 1 FROM wpl.organization_roles WHERE org_id=o.id AND membership_id=o.primary_admin_membership_id AND role='admin') THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Designated primary must retain admin membership';
    END IF;
    IF m.status='invite_pending' AND o.status<>'pending' THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Unaccepted primary requires pending organization';
    END IF;
    IF o.status='active' AND (m.status<>'active' OR m.user_id IS NULL OR m.global_state IS DISTINCT FROM 'active') THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Active organization requires an active accepted primary';
    END IF;
    IF TG_TABLE_NAME='organizations' THEN
    IF TG_OP='UPDATE' AND OLD.primary_admin_membership_id IS DISTINCT FROM NEW.primary_admin_membership_id THEN
        IF NOT EXISTS (SELECT 1 FROM wpl.organization_memberships membership JOIN wpl.users u ON u.id=membership.user_id
            JOIN wpl.organization_roles r ON r.org_id=membership.org_id AND r.membership_id=membership.id AND r.role='admin'
            WHERE membership.org_id=NEW.id AND membership.id=NEW.primary_admin_membership_id
            AND membership.status='active' AND u.global_state='active') THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Transfer target must be an active eligible admin';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM wpl.organization_memberships membership JOIN wpl.organization_roles r
            ON r.org_id=membership.org_id AND r.membership_id=membership.id AND r.role='admin'
            WHERE membership.org_id=OLD.id AND membership.id=OLD.primary_admin_membership_id AND membership.status='active') THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Transfer retains the former primary as admin';
        END IF;
    END IF;
    END IF;
    RETURN NULL;
END;
$$
-- statement --
CREATE FUNCTION wpl.check_cohort_instructor() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
DECLARE c record; v_org uuid; v_cohort uuid; v_member uuid;
BEGIN
    v_org := COALESCE(NEW.org_id,OLD.org_id);
    IF TG_TABLE_NAME='cohorts' THEN v_cohort := NEW.id;
    ELSIF TG_TABLE_NAME='cohort_memberships' THEN v_cohort := COALESCE(NEW.cohort_id,OLD.cohort_id);
    ELSIF TG_TABLE_NAME='organization_memberships' THEN v_member := COALESCE(NEW.id,OLD.id);
    ELSE v_member := COALESCE(NEW.membership_id,OLD.membership_id);
    END IF;
    FOR c IN SELECT cohort.id,cohort.org_id FROM wpl.cohorts cohort WHERE cohort.org_id=v_org AND cohort.status='active'
        AND ((v_cohort IS NOT NULL AND cohort.id=v_cohort) OR (v_member IS NOT NULL AND EXISTS (
            SELECT 1 FROM wpl.cohort_memberships cm WHERE cm.org_id=cohort.org_id
              AND cm.cohort_id=cohort.id AND cm.membership_id=v_member))) LOOP
        IF NOT EXISTS (SELECT 1 FROM wpl.cohort_memberships cm
            JOIN wpl.organization_memberships m ON m.org_id=cm.org_id AND m.id=cm.membership_id
            JOIN wpl.users u ON u.id=m.user_id
            JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='instructor'
            WHERE cm.org_id=c.org_id AND cm.cohort_id=c.id AND cm.role='instructor'
              AND cm.status='active' AND m.status='active' AND u.global_state='active') THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Active cohort requires an active assigned instructor';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$
-- statement --
CREATE FUNCTION wpl.check_invitation_binding() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
DECLARE v_org uuid; v_member uuid; m record;
BEGIN
    v_org := COALESCE(NEW.org_id,OLD.org_id);
    IF TG_TABLE_NAME='invitations' THEN v_member := COALESCE(NEW.membership_id,OLD.membership_id);
    ELSE v_member := COALESCE(NEW.id,OLD.id);
    END IF;
    SELECT membership.status,membership.user_id,i.status AS invitation_status,i.accepted_user_id INTO m
        FROM wpl.organization_memberships membership JOIN wpl.invitations i
          ON i.org_id=membership.org_id AND i.id=membership.invitation_id AND i.membership_id=membership.id
        WHERE membership.org_id=v_org AND membership.id=v_member;
    IF FOUND AND m.status='active' AND (m.invitation_status<>'accepted' OR m.accepted_user_id IS DISTINCT FROM m.user_id) THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Active invited membership requires verified invitation binding';
    END IF;
    RETURN NULL;
END;
$$
-- statement --
CREATE FUNCTION wpl.global_security_recovery() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
DECLARE o record; c record;
BEGIN
    IF NEW.global_state='active' OR NEW.global_state IS NOT DISTINCT FROM OLD.global_state THEN RETURN NEW; END IF;
    FOR o IN SELECT org.id FROM wpl.organizations org JOIN wpl.organization_memberships m
        ON m.org_id=org.id AND m.id=org.primary_admin_membership_id
        WHERE m.user_id=NEW.id AND org.status='active' ORDER BY org.id LOOP
        UPDATE wpl.organizations SET status='recovery_required' WHERE id=o.id;
        INSERT INTO wpl.audit_events(id,org_id,action,reason,target_type,target_id,changes)
            VALUES (gen_random_uuid(),o.id,'global_security_recovery','Primary identity blocked','organization',o.id,
                    jsonb_build_object('blocked_user_id',NEW.id));
    END LOOP;
    FOR c IN SELECT DISTINCT cohort.id,cohort.org_id FROM wpl.cohorts cohort
        JOIN wpl.cohort_memberships cm ON cm.org_id=cohort.org_id AND cm.cohort_id=cohort.id
        JOIN wpl.organization_memberships m ON m.org_id=cm.org_id AND m.id=cm.membership_id
        WHERE m.user_id=NEW.id AND cm.role='instructor' AND cohort.status='active' ORDER BY cohort.org_id,cohort.id LOOP
        UPDATE wpl.organizations SET version=version+1 WHERE id=c.org_id;
        UPDATE wpl.cohorts SET version=version+1,access_epoch=access_epoch+1 WHERE id=c.id;
        IF NOT EXISTS (SELECT 1 FROM wpl.cohort_memberships cm JOIN wpl.organization_memberships m
            ON m.org_id=cm.org_id AND m.id=cm.membership_id JOIN wpl.users u ON u.id=m.user_id
            JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='instructor'
            WHERE cm.org_id=c.org_id AND cm.cohort_id=c.id AND cm.role='instructor' AND cm.status='active'
              AND m.status='active' AND u.global_state='active' AND u.id<>NEW.id) THEN
            UPDATE wpl.cohorts SET status='recovery_required' WHERE id=c.id;
            INSERT INTO wpl.audit_events(id,org_id,action,reason,target_type,target_id,changes)
                VALUES (gen_random_uuid(),c.org_id,'global_security_recovery','Final instructor identity blocked','cohort',c.id,
                        jsonb_build_object('blocked_user_id',NEW.id));
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$

-- statement --
CREATE FUNCTION wpl.advance_role_epoch() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,wpl AS $$
BEGIN
    UPDATE wpl.organization_memberships SET access_epoch=access_epoch+1
        WHERE org_id=COALESCE(NEW.org_id,OLD.org_id) AND id=COALESCE(NEW.membership_id,OLD.membership_id);
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$
