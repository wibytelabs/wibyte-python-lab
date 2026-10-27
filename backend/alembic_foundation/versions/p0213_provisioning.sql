CREATE FUNCTION wpl.provision_organization(body jsonb,p_request_key varchar,organization uuid,member uuid,invitation uuid,
    job uuid,payload uuid,token_digest bytea,key_ref varchar,encrypted bytea,intent varchar)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
DECLARE actor uuid; digest text; existing wpl.idempotency_records%ROWTYPE; receipt jsonb;
    value jsonb; current_version integer;
BEGIN
    actor:=wpl.ctx_uuid('wpl.actor_id');
    IF wpl.ctx_scope() IS DISTINCT FROM 'platform' OR wpl.ctx_uuid('wpl.org_id') IS NOT NULL
       OR NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
    IF p_request_key IS NULL OR p_request_key !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR body IS NULL OR jsonb_typeof(body)<>'object'
       OR NOT body ?& ARRAY['name','organization_type','contact_email','home_region','primary_admin_email','reason']
       OR body-ARRAY['name','organization_type','contact_email','home_region','primary_admin_email','reason']<>'{}'::jsonb THEN
        RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
    FOR value IN SELECT e.value FROM jsonb_each(body) e LOOP
        IF jsonb_typeof(value)<>'string' THEN RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
    END LOOP;
    IF length(body->>'name') NOT BETWEEN 1 AND 160 OR body->>'name'<>trim(body->>'name') OR body->>'name' ~ '[[:cntrl:]]'
       OR body->>'organization_type' NOT IN ('school','university','training','other')
       OR body->>'home_region' !~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'
       OR length(trim(body->>'reason')) NOT BETWEEN 5 AND 1000 THEN
        RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
    FOR value IN SELECT body->'contact_email' UNION ALL SELECT body->'primary_admin_email' LOOP
        IF length(value#>>'{}') NOT BETWEEN 3 AND 254 OR value#>>'{}'<>lower(trim(value#>>'{}'))
           OR value#>>'{}' !~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' THEN
            RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
    END LOOP;
    digest:=encode(sha256(convert_to(body::text,'UTF8')),'hex');
    PERFORM pg_advisory_xact_lock(hashtextextended('wpl.org.create.v1:'||actor::text||':'||p_request_key,0));
    IF NOT wpl.platform_capability('orgs') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
    SELECT r.* INTO existing FROM wpl.idempotency_records r WHERE r.actor_id=actor AND r.operation='create_organization'
        AND r.scope_kind='platform' AND r.scope_id='00000000-0000-0000-0000-000000000000'::uuid AND r.request_key=p_request_key;
    IF FOUND THEN
        IF existing.request_hash<>digest THEN RETURN jsonb_build_object('error','idempotency_conflict'); END IF;
        RETURN jsonb_build_object('receipt',existing.response,'replayed',true);
    END IF;
    IF organization IS NULL OR member IS NULL OR invitation IS NULL OR job IS NULL OR payload IS NULL
       OR '00000000-0000-0000-0000-000000000000'::uuid=ANY(ARRAY[organization,member,invitation,job,payload])
       OR token_digest IS NULL OR octet_length(token_digest)<>32 OR key_ref IS NULL
       OR key_ref !~ '^[A-Za-z0-9_.:/-]{1,128}$' OR encrypted IS NULL
       OR octet_length(encrypted) NOT BETWEEN 34 AND 32800 OR substring(encrypted FROM 1 FOR 4)<>decode('57504c31','hex')
       OR intent IS NULL OR intent !~ '^[0-9a-f]{64}$' THEN RETURN jsonb_build_object('error','invalid_provisioning'); END IF;
    INSERT INTO wpl.organizations(id,name,organization_type,contact_email,home_region,primary_admin_membership_id,provisioning_identity)
        VALUES(organization,body->>'name',body->>'organization_type',body->>'contact_email',body->>'home_region',member,
            'platform:'||actor::text||':'||encode(sha256(convert_to(p_request_key,'UTF8')),'hex'));
    INSERT INTO wpl.organization_memberships(id,org_id,invitation_id,status) VALUES(member,organization,invitation,'invite_pending');
    INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES(organization,member,'admin');
    INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,token_hash,expires_at)
        VALUES(invitation,organization,member,body->>'primary_admin_email',ARRAY['admin']::varchar[],token_digest,statement_timestamp()+interval '1 day');
    INSERT INTO wpl.secret_payloads(id,scope_kind,scope_id,org_id,key_reference,ciphertext)
        VALUES(payload,'tenant',organization,organization,key_ref,encrypted);
    INSERT INTO wpl.jobs(id,scope_kind,scope_id,org_id,actor_id,kind,dedup_key,private_payload_id,intent_hash)
        VALUES(job,'tenant',organization,organization,actor,'deliver_primary_invitation','primary_invitation:'||organization::text,payload,intent);
    INSERT INTO wpl.outbox(id,scope_kind,scope_id,job_id,event_kind,dedup_key)
        VALUES(gen_random_uuid(),'tenant',organization,job,'delivery_requested','delivery:'||job::text);
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),actor,organization,'organization_provisioned',trim(body->>'reason'),'organization',organization,
            jsonb_build_object('status','pending','primary_admin_membership_id',member,'invitation_status','pending','job_id',job,'delivery_status','pending_integration'));
    INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES(gen_random_uuid(),actor,organization,'job_enqueued','Initial primary invitation queued','job',job,
            jsonb_build_object('job_kind','deliver_primary_invitation','delivery_status','pending_integration'));
    SELECT o.version INTO current_version FROM wpl.organizations o WHERE o.id=organization;
    receipt:=jsonb_build_object('org_id',organization,'status','pending','primary_admin_membership_id',member,
        'invitation_status','pending','job_id',job,'delivery_status','pending_integration','version',current_version);
    INSERT INTO wpl.idempotency_records(actor_id,operation,scope_kind,scope_id,request_key,request_hash,response_status,response)
        VALUES(actor,'create_organization','platform','00000000-0000-0000-0000-000000000000'::uuid,p_request_key,digest,201,receipt);
    RETURN jsonb_build_object('receipt',receipt,'replayed',false);
END
$$
