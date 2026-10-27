CREATE TABLE wpl.legacy_import_runs (
    source_namespace varchar(64) PRIMARY KEY CHECK (source_namespace ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
    source_checksum char(64) NOT NULL CHECK (source_checksum ~ '^[0-9a-f]{64}$'),
    source_revision varchar(32) NOT NULL CHECK (source_revision IN ('553a7ddf4183','7d8e63fb45c3')),
    intent_hash char(64) NOT NULL CHECK (intent_hash ~ '^[0-9a-f]{64}$'),
    archive_hash char(64) NOT NULL CHECK (archive_hash ~ '^[0-9a-f]{64}$'),
    artifact_count integer NOT NULL CHECK (artifact_count BETWEEN 0 AND 25000),
    credential_count integer NOT NULL CHECK (credential_count BETWEEN 0 AND 10000),
    reason varchar(1000) NOT NULL CHECK (length(reason) BETWEEN 5 AND 1000),
    created_at timestamptz NOT NULL DEFAULT now()
)
-- statement --
CREATE TABLE wpl.legacy_import_artifacts (
    source_namespace varchar(64) NOT NULL REFERENCES wpl.legacy_import_runs(source_namespace),
    target_id uuid NOT NULL,
    source_kind varchar(32) NOT NULL CHECK (source_kind IN ('students','github_connections','github_repositories','labs')),
    source_id uuid NOT NULL,
    owner_source_kind varchar(32) NOT NULL DEFAULT 'students' CHECK (owner_source_kind='students'),
    owner_source_id uuid NOT NULL,
    owner_user_id uuid REFERENCES wpl.users(id),
    scope_kind varchar(16) NOT NULL DEFAULT 'personal' CHECK (scope_kind='personal'),
    repository_source_kind varchar(32) NOT NULL DEFAULT 'github_repositories' CHECK (repository_source_kind='github_repositories'),
    repository_source_id uuid,
    metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata)='object' AND octet_length(metadata::text)<=16384
        AND NOT metadata ?| ARRAY['access_token','refresh_token','access_token_expires_at','refresh_token_expires_at']),
    source_checksum char(64) NOT NULL CHECK (source_checksum ~ '^[0-9a-f]{64}$'),
    credential_state varchar(32) NOT NULL CHECK (credential_state IN ('none','reauthorization_required')),
    key_reference varchar(128),
    ciphertext bytea,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(source_namespace,target_id), UNIQUE(source_namespace,source_kind,source_id),
    FOREIGN KEY(source_namespace,owner_source_kind,owner_source_id)
        REFERENCES wpl.legacy_import_artifacts(source_namespace,source_kind,source_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(source_namespace,repository_source_kind,repository_source_id)
        REFERENCES wpl.legacy_import_artifacts(source_namespace,source_kind,source_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (repository_source_id IS NULL OR source_kind='labs'),
    CHECK ((source_kind='github_connections' AND credential_state='reauthorization_required'
        AND key_reference IS NOT NULL AND key_reference ~ '^[A-Za-z0-9_.:/-]{1,128}$' AND ciphertext IS NOT NULL
        AND octet_length(ciphertext) BETWEEN 34 AND 32800 AND substring(ciphertext FROM 1 FOR 4)=decode('57504c31','hex'))
        OR (source_kind<>'github_connections' AND credential_state='none' AND key_reference IS NULL AND ciphertext IS NULL))
)
-- statement --
CREATE INDEX legacy_archive_owner ON wpl.legacy_import_artifacts(source_namespace,owner_source_id,source_kind)
