"""Narrow executive metadata/status operation, not direct privileged columns."""
from alembic import op
revision='p0212_executive_metadata'
down_revision='p0211_delivery_execution'
branch_labels=None
depends_on=None
FUNCTION='change_organization(uuid,integer,character varying,character varying,character varying,character varying,character varying,character varying)'


def upgrade():
    op.execute('''CREATE FUNCTION wpl.change_organization(org uuid,expected integer,operation varchar,
        new_name varchar,new_email varchar,new_region varchar,new_status varchar,reason_text varchar)
        RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        DECLARE item wpl.organizations%ROWTYPE; prior_version integer; prior_status varchar; changed_fields jsonb;
        BEGIN
            IF wpl.ctx_scope() IS DISTINCT FROM 'platform' OR wpl.ctx_uuid('wpl.org_id') IS DISTINCT FROM org
               OR NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
            IF operation IS NULL OR operation NOT IN ('metadata','status') OR expected IS NULL OR expected<1
               OR reason_text IS NULL OR length(trim(reason_text)) NOT BETWEEN 5 AND 1000 THEN
                RETURN jsonb_build_object('error','invalid_change'); END IF;
            IF operation='metadata' THEN
                IF new_status IS NOT NULL OR (new_name IS NULL AND new_email IS NULL AND new_region IS NULL)
                   OR (new_name IS NOT NULL AND (length(trim(new_name)) NOT BETWEEN 1 AND 160 OR new_name ~ '[[:cntrl:]]'))
                   OR (new_email IS NOT NULL AND (length(new_email) NOT BETWEEN 3 AND 254 OR new_email<>lower(trim(new_email))
                        OR new_email !~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'))
                   OR (new_region IS NOT NULL AND new_region !~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') THEN
                    RETURN jsonb_build_object('error','invalid_change'); END IF;
            ELSIF new_status IS NULL OR new_status NOT IN ('active','suspended')
                OR new_name IS NOT NULL OR new_email IS NOT NULL OR new_region IS NOT NULL THEN
                RETURN jsonb_build_object('error','invalid_change'); END IF;
            SELECT o.* INTO item FROM wpl.organizations o WHERE o.id=org FOR UPDATE;
            IF NOT FOUND THEN RETURN NULL; END IF;
            IF NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
            IF item.version<>expected THEN RETURN jsonb_build_object('error','version_conflict'); END IF;
            prior_version:=item.version; prior_status:=item.status;
            IF operation='status' THEN
                IF item.status='recovery_required' THEN RETURN jsonb_build_object('error','recovery_required'); END IF;
                IF NOT EXISTS(SELECT 1 FROM wpl.organization_memberships m JOIN wpl.users u ON u.id=m.user_id
                    JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id
                    WHERE m.org_id=org AND m.id=item.primary_admin_membership_id AND m.status='active'
                    AND u.global_state='active' AND r.role='admin') THEN
                    RETURN jsonb_build_object('error','primary_not_active'); END IF;
                IF item.status<>new_status THEN
                    UPDATE wpl.organizations o SET status=new_status WHERE o.id=org RETURNING o.* INTO item;
                    changed_fields:=jsonb_build_object('from',prior_status,'to',item.status);
                END IF;
            ELSE
                SELECT COALESCE(jsonb_agg(field_name),'[]'::jsonb) INTO changed_fields FROM (
                    SELECT 'name'::text AS field_name WHERE new_name IS NOT NULL AND trim(new_name)<>item.name
                    UNION ALL SELECT 'contact_email' WHERE new_email IS NOT NULL AND new_email<>item.contact_email
                    UNION ALL SELECT 'home_region' WHERE new_region IS NOT NULL AND new_region<>item.home_region) fields;
                IF changed_fields<>'[]'::jsonb THEN
                    UPDATE wpl.organizations o SET name=COALESCE(trim(new_name),o.name),
                        contact_email=COALESCE(new_email,o.contact_email),home_region=COALESCE(new_region,o.home_region)
                        WHERE o.id=org RETURNING o.* INTO item;
                    changed_fields:=jsonb_build_object('fields',changed_fields);
                END IF;
            END IF;
            IF item.version<>prior_version THEN
                INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
                    VALUES(gen_random_uuid(),wpl.ctx_uuid('wpl.actor_id'),org,
                        CASE WHEN operation='status' THEN 'organization_status_changed' ELSE 'organization_metadata_changed' END,
                        trim(reason_text),'organization',org,changed_fields||jsonb_build_object('prior_version',prior_version,'version',item.version));
            END IF;
            RETURN jsonb_build_object('id',item.id,'name',item.name,'contact_email',item.contact_email,
                'home_region',item.home_region,'status',item.status,'version',item.version,'access_epoch',item.access_epoch);
        END
        $$''')
    op.execute(f'REVOKE ALL ON FUNCTION wpl.{FUNCTION} FROM PUBLIC,wpl_app,wpl_worker')
    op.execute(f'GRANT EXECUTE ON FUNCTION wpl.{FUNCTION} TO wpl_app')


def downgrade():op.execute(f'DROP FUNCTION wpl.{FUNCTION}')
