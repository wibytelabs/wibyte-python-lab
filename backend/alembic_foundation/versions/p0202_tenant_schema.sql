CREATE TABLE wpl.users (
    id uuid PRIMARY KEY,
    full_name varchar(160) NOT NULL DEFAULT '',
    verified_email varchar(254),
    global_state varchar(16) NOT NULL DEFAULT 'pending' CHECK (global_state IN ('pending','active','suspended','declined')),
    access_epoch bigint NOT NULL DEFAULT 1 CHECK (access_epoch > 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
-- statement --
CREATE TABLE wpl.platform_roles (
    user_id uuid NOT NULL REFERENCES wpl.users(id),
    capability varchar(24) NOT NULL CHECK (capability IN ('orgs','users','recovery','executives','observe','approvals')),
    grantor_id uuid REFERENCES wpl.users(id),
    reason varchar(1000) NOT NULL CHECK (length(trim(reason)) BETWEEN 5 AND 1000),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, capability)
)
-- statement --
CREATE TABLE wpl.organizations (
    id uuid PRIMARY KEY,
    name varchar(160) NOT NULL CHECK (length(trim(name)) > 0),
    organization_type varchar(24) NOT NULL CHECK (organization_type IN ('school','university','training','other')),
    contact_email varchar(254) NOT NULL,
    home_region varchar(64) NOT NULL CHECK (length(trim(home_region)) > 0),
    status varchar(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','suspended','recovery_required')),
    primary_admin_membership_id uuid NOT NULL,
    provisioning_identity varchar(192) NOT NULL UNIQUE CHECK (length(provisioning_identity) > 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    access_epoch bigint NOT NULL DEFAULT 1 CHECK (access_epoch > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
-- statement --
CREATE INDEX organizations_directory ON wpl.organizations (status, created_at, id)
-- statement --
CREATE TABLE wpl.organization_memberships (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES wpl.organizations(id),
    user_id uuid REFERENCES wpl.users(id),
    invitation_id uuid,
    status varchar(16) NOT NULL CHECK (status IN ('invite_pending','active','suspended','removed')),
    access_epoch bigint NOT NULL DEFAULT 1 CHECK (access_epoch > 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    joined_at timestamptz,
    removed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id), UNIQUE (org_id, user_id), UNIQUE (org_id, invitation_id),
    CHECK (user_id IS NOT NULL OR (status='invite_pending' AND invitation_id IS NOT NULL)),
    CHECK (status <> 'invite_pending' OR invitation_id IS NOT NULL)
)
-- statement --
CREATE INDEX memberships_user_contexts ON wpl.organization_memberships (user_id, status, org_id)
-- statement --
CREATE TABLE wpl.organization_roles (
    org_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    role varchar(16) NOT NULL CHECK (role IN ('admin','instructor','student')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, membership_id, role),
    FOREIGN KEY (org_id, membership_id) REFERENCES wpl.organization_memberships(org_id,id)
)
-- statement --
ALTER TABLE wpl.organizations ADD CONSTRAINT organizations_primary_same_org
    FOREIGN KEY (id, primary_admin_membership_id) REFERENCES wpl.organization_memberships(org_id,id)
    DEFERRABLE INITIALLY DEFERRED
-- statement --
CREATE TABLE wpl.invitations (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES wpl.organizations(id),
    membership_id uuid NOT NULL,
    intended_email varchar(254) NOT NULL CHECK (intended_email=lower(trim(intended_email)) AND length(intended_email)>3),
    intended_roles varchar(16)[] NOT NULL CHECK (cardinality(intended_roles)>0 AND intended_roles <@ ARRAY['admin','instructor','student']::varchar[]),
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash)=32),
    status varchar(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked','expired')),
    expires_at timestamptz NOT NULL,
    accepted_user_id uuid REFERENCES wpl.users(id),
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id,id), UNIQUE (org_id,membership_id), UNIQUE (org_id,membership_id,id),
    FOREIGN KEY (org_id,membership_id) REFERENCES wpl.organization_memberships(org_id,id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (expires_at>created_at),
    CHECK ((status='accepted' AND accepted_user_id IS NOT NULL AND accepted_at IS NOT NULL)
        OR (status<>'accepted' AND accepted_user_id IS NULL AND accepted_at IS NULL))
)
-- statement --
ALTER TABLE wpl.organization_memberships ADD CONSTRAINT memberships_invitation_same_org
    FOREIGN KEY (org_id,id,invitation_id) REFERENCES wpl.invitations(org_id,membership_id,id) DEFERRABLE INITIALLY DEFERRED
-- statement --
CREATE INDEX invitations_pending_expiry ON wpl.invitations (org_id,status,expires_at,id)
-- statement --
CREATE TABLE wpl.primary_admin_transfers (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES wpl.organizations(id),
    actor_id uuid NOT NULL REFERENCES wpl.users(id),
    from_membership_id uuid NOT NULL,
    to_membership_id uuid NOT NULL,
    expected_version integer NOT NULL CHECK (expected_version>0),
    confirmation_hash bytea NOT NULL CHECK (octet_length(confirmation_hash)=32),
    status varchar(16) NOT NULL CHECK (status IN ('preview','completed','expired','cancelled')),
    reason varchar(1000),
    expires_at timestamptz NOT NULL,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id,id),
    CHECK (from_membership_id <> to_membership_id),
    CHECK ((status='completed') = (completed_at IS NOT NULL)),
    FOREIGN KEY (org_id,from_membership_id) REFERENCES wpl.organization_memberships(org_id,id),
    FOREIGN KEY (org_id,to_membership_id) REFERENCES wpl.organization_memberships(org_id,id)
)
-- statement --
CREATE UNIQUE INDEX transfers_one_preview ON wpl.primary_admin_transfers (org_id) WHERE status='preview'
-- statement --
CREATE TABLE wpl.cohorts (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES wpl.organizations(id),
    name varchar(160) NOT NULL CHECK (length(trim(name))>0),
    slug varchar(80) NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    status varchar(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','archived','recovery_required')),
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    access_epoch bigint NOT NULL DEFAULT 1 CHECK (access_epoch>0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id,id), UNIQUE (org_id,slug)
)
-- statement --
CREATE TABLE wpl.cohort_memberships (
    org_id uuid NOT NULL,
    cohort_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    role varchar(16) NOT NULL CHECK (role IN ('instructor','student')),
    status varchar(16) NOT NULL CHECK (status IN ('active','removed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id,cohort_id,membership_id,role),
    FOREIGN KEY (org_id,cohort_id) REFERENCES wpl.cohorts(org_id,id),
    FOREIGN KEY (org_id,membership_id) REFERENCES wpl.organization_memberships(org_id,id)
)
-- statement --
CREATE INDEX cohort_memberships_member ON wpl.cohort_memberships (org_id,membership_id,status,cohort_id)
-- statement --
CREATE TABLE wpl.secret_payloads (
    id uuid PRIMARY KEY,
    scope_kind varchar(16) NOT NULL CHECK (scope_kind IN ('platform','tenant','personal')),
    scope_id uuid NOT NULL,
    org_id uuid REFERENCES wpl.organizations(id),
    owner_user_id uuid REFERENCES wpl.users(id),
    key_reference varchar(128) NOT NULL CHECK (length(key_reference)>0),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 16 AND 65536),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope_kind,scope_id,id),
    CHECK ((scope_kind='tenant' AND org_id IS NOT NULL AND scope_id=org_id AND owner_user_id IS NULL)
        OR (scope_kind='personal' AND owner_user_id IS NOT NULL AND scope_id=owner_user_id AND org_id IS NULL)
        OR (scope_kind='platform' AND scope_id='00000000-0000-0000-0000-000000000000'::uuid AND org_id IS NULL AND owner_user_id IS NULL))
)
-- statement --
CREATE TABLE wpl.jobs (
    id uuid PRIMARY KEY,
    scope_kind varchar(16) NOT NULL CHECK (scope_kind IN ('platform','tenant','personal')),
    scope_id uuid NOT NULL,
    org_id uuid REFERENCES wpl.organizations(id),
    owner_user_id uuid REFERENCES wpl.users(id),
    actor_id uuid NOT NULL REFERENCES wpl.users(id),
    kind varchar(48) NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]*$'),
    dedup_key varchar(128) NOT NULL CHECK (length(dedup_key)>0),
    state varchar(16) NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','succeeded','dead','cancelled')),
    private_payload_id uuid,
    lease_owner uuid,
    lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation>=0),
    lease_until timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
    available_at timestamptz NOT NULL DEFAULT now(),
    last_error_code varchar(64) CHECK (last_error_code ~ '^[a-z0-9_]+$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope_kind,scope_id,id), UNIQUE (scope_kind,scope_id,kind,dedup_key),
    FOREIGN KEY (scope_kind,scope_id,private_payload_id) REFERENCES wpl.secret_payloads(scope_kind,scope_id,id),
    CHECK ((state='running' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL)
        OR (state<>'running' AND lease_owner IS NULL AND lease_until IS NULL)),
    CHECK ((scope_kind='tenant' AND org_id IS NOT NULL AND scope_id=org_id AND owner_user_id IS NULL)
        OR (scope_kind='personal' AND owner_user_id IS NOT NULL AND scope_id=owner_user_id AND org_id IS NULL)
        OR (scope_kind='platform' AND scope_id='00000000-0000-0000-0000-000000000000'::uuid AND org_id IS NULL AND owner_user_id IS NULL))
)
-- statement --
CREATE INDEX jobs_claim ON wpl.jobs (state,available_at,created_at,id) WHERE state IN ('queued','running')
-- statement --
CREATE INDEX jobs_org_status ON wpl.jobs (org_id,created_at,id)
-- statement --
CREATE TABLE wpl.outbox (
    id uuid PRIMARY KEY,
    scope_kind varchar(16) NOT NULL,
    scope_id uuid NOT NULL,
    job_id uuid NOT NULL,
    event_kind varchar(48) NOT NULL CHECK (event_kind ~ '^[a-z][a-z0-9_]*$'),
    dedup_key varchar(128) NOT NULL CHECK (length(dedup_key)>0),
    state varchar(16) NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','dispatched')),
    created_at timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,
    FOREIGN KEY (scope_kind,scope_id,job_id) REFERENCES wpl.jobs(scope_kind,scope_id,id),
    UNIQUE (scope_kind,scope_id,event_kind,dedup_key),
    CHECK ((state='dispatched') = (dispatched_at IS NOT NULL))
)
-- statement --
CREATE INDEX outbox_dispatch ON wpl.outbox (state,created_at,id) WHERE state='pending'
-- statement --
CREATE TABLE wpl.idempotency_records (
    actor_id uuid NOT NULL REFERENCES wpl.users(id),
    operation varchar(64) NOT NULL CHECK (length(operation)>0),
    scope_kind varchar(16) NOT NULL CHECK (scope_kind IN ('platform','tenant','personal')),
    scope_id uuid NOT NULL,
    org_id uuid REFERENCES wpl.organizations(id),
    request_key varchar(128) NOT NULL CHECK (length(request_key)>0),
    request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    response_status integer NOT NULL CHECK (response_status IN (200,201,202,204)),
    response jsonb NOT NULL CHECK (jsonb_typeof(response)='object' AND octet_length(response::text)<=16384),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (actor_id,operation,scope_kind,scope_id,request_key),
    CHECK ((scope_kind='tenant' AND org_id IS NOT NULL AND scope_id=org_id)
        OR (scope_kind='personal' AND scope_id=actor_id AND org_id IS NULL)
        OR (scope_kind='platform' AND scope_id='00000000-0000-0000-0000-000000000000'::uuid AND org_id IS NULL))
)
-- statement --
CREATE TABLE wpl.audit_events (
    id uuid PRIMARY KEY,
    actor_id uuid REFERENCES wpl.users(id),
    org_id uuid REFERENCES wpl.organizations(id),
    action varchar(64) NOT NULL CHECK (action ~ '^[a-z][a-z0-9_]*$'),
    reason varchar(1000),
    target_type varchar(48) NOT NULL,
    target_id uuid NOT NULL,
    changes jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(changes)='object' AND octet_length(changes::text)<=16384),
    created_at timestamptz NOT NULL DEFAULT now()
)
-- statement --
CREATE INDEX audit_org_history ON wpl.audit_events (org_id,created_at,id)
-- statement --
CREATE TABLE wpl.migration_mappings (
    id uuid PRIMARY KEY,
    source_namespace varchar(64) NOT NULL CHECK (length(source_namespace)>0),
    source_kind varchar(32) NOT NULL,
    source_id varchar(192) NOT NULL,
    target_kind varchar(32) NOT NULL,
    target_id uuid NOT NULL,
    reconciliation_state varchar(16) NOT NULL CHECK (reconciliation_state IN ('validated','imported','rejected')),
    source_checksum char(64) NOT NULL CHECK (source_checksum ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_namespace,source_kind,source_id), UNIQUE (source_namespace,target_kind,target_id)
)
