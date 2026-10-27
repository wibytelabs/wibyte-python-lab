"""Confirmed, marker-checked fixture import; archives grant no runtime authority."""
from dataclasses import dataclass,field
import hashlib
import json
import re
from types import MappingProxyType
from uuid import UUID,uuid5
import psycopg
from psycopg.types.json import Jsonb
from backend.app.domains.jobs.payloads import PayloadBinding,PayloadCipher,PayloadScope,EncryptedPayload
from backend.app.domains.migration.snapshot import Snapshot,NAMESPACE,COLUMNS

SECRET_FIELDS={'access_token','refresh_token','access_token_expires_at','refresh_token_expires_at'}

class RehearsalError(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__('Disposable import rejected: '+code+'. Details redacted.')

@dataclass(frozen=True)
class ArchiveRow:
    kind: str
    source_id: UUID
    target_id: UUID
    owner_source_id: UUID
    owner_target_id: UUID
    owner_user_id: UUID | None
    repository_source_id: UUID | None
    checksum: str=field(repr=False)
    metadata: object=field(repr=False)
    envelope: EncryptedPayload | None=field(repr=False)

@dataclass(frozen=True)
class PreparedImport:
    namespace: str
    source_checksum: str
    source_revision: str
    intent_hash: str
    reason: str=field(repr=False)
    rows: tuple[ArchiveRow,...]=field(repr=False)


def reject(code):raise RehearsalError(code)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def credential_binding(namespace,owner_target_id,target_id):
    return PayloadBinding(PayloadScope.PERSONAL,owner_target_id,owner_target_id,
        uuid5(NAMESPACE,'legacy-import:'+namespace),target_id,'legacy_credential_archive')


def prepare_import(snapshot: Snapshot,namespace: str,reason: str,cipher: PayloadCipher,*,identity_bindings=None):
    if not isinstance(snapshot,Snapshot) or not isinstance(cipher,PayloadCipher):reject('explicit_snapshot_and_cipher_required')
    if not isinstance(namespace,str) or re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,63}',namespace) is None:reject('invalid_source_namespace')
    if not isinstance(reason,str) or not 5<=len(reason.strip())<=1000 or any(ord(char)<32 or ord(char)==127 for char in reason):reject('reason_required')
    bindings={} if identity_bindings is None else identity_bindings
    owners={row.source_id:row.target_id for row in snapshot.records if row.kind=='students'}
    if (not isinstance(bindings,dict) or any(not isinstance(key,UUID) or key not in owners or not isinstance(value,UUID) or value.int==0 for key,value in bindings.items())
            or len(set(bindings.values()))!=len(bindings)):reject('ambiguous_or_unknown_identity_mapping')
    # Explicit IDs only; profile/email data never participates in identity binding.
    binding_hash=digest(sorted((str(key),str(value)) for key,value in bindings.items()))
    intent=digest([snapshot.checksum,snapshot.source_revision,binding_hash,reason.strip()])
    rows=[]
    for record in snapshot.records:
        if record.kind not in COLUMNS or record.owner_source_id not in owners:reject('invalid_snapshot_plan')
        values=dict(record.values)
        metadata={key:value for key,value in values.items() if key not in SECRET_FIELDS}
        secret={key:value for key,value in values.items() if key in SECRET_FIELDS}
        owner_target=owners[record.owner_source_id]
        envelope=None
        if record.kind=='github_connections':
            # Keys/crypto resolve here, before any target connection or transaction.
            envelope=cipher.encrypt({'source_revision':snapshot.source_revision,**secret},
                credential_binding(namespace,owner_target,record.target_id))
        elif secret:reject('invalid_snapshot_plan')
        repository=UUID(values['github_repository_id']) if record.kind=='labs' and values['github_repository_id'] else None
        checksum=digest([record.kind,str(record.source_id),values,str(bindings.get(record.owner_source_id))])
        rows.append(ArchiveRow(record.kind,record.source_id,record.target_id,record.owner_source_id,owner_target,
            bindings.get(record.owner_source_id),repository,checksum,MappingProxyType(metadata),envelope))
    return PreparedImport(namespace,snapshot.checksum,snapshot.source_revision,intent,reason.strip(),tuple(rows))


def _row_values(row):
    return [row.kind,str(row.source_id),str(row.target_id),str(row.owner_source_id),str(row.owner_user_id) if row.owner_user_id else None,
        str(row.repository_source_id) if row.repository_source_id else None,dict(row.metadata),row.checksum,
        row.envelope.key_reference if row.envelope else None,
        hashlib.sha256(row.envelope.ciphertext).hexdigest() if row.envelope else None]


def _archive_hash(values):return digest(sorted(values,key=lambda row:(row[0],row[1])))


def _target(connection,owner):
    if not isinstance(owner,str) or re.fullmatch(r'[0-9a-f]{32}',owner) is None:reject('owned_disposable_target_required')
    info=connection.info
    if info.host!='fixture-db' or info.dbname!='wpl_fixture' or info.user!='wpl_migrator':reject('owned_disposable_target_required')
    identity=connection.execute('''SELECT current_user,current_database(),shobj_description(d.oid,'pg_database'),
        n.nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user),r.rolsuper,r.rolbypassrls
        FROM pg_database d CROSS JOIN pg_namespace n CROSS JOIN pg_roles r
        WHERE d.datname=current_database() AND n.nspname='wpl' AND r.rolname=current_user''').fetchone()
    if identity!=('wpl_migrator','wpl_fixture','wpl.disposable.rehearsal:'+owner,True,False,False):reject('owned_disposable_target_required')


def _reconcile(connection,prepared,archive_hash):
    rows=connection.execute('''SELECT source_kind,source_id,target_id,owner_source_id,owner_user_id,repository_source_id,
        metadata,source_checksum,key_reference,ciphertext,scope_kind,credential_state
        FROM wpl.legacy_import_artifacts WHERE source_namespace=%s ORDER BY source_kind,source_id''',(prepared.namespace,)).fetchall()
    values=[]
    for row in rows:
        kind,source,target,owner,user,repository,metadata,checksum,reference,ciphertext,scope,state=row
        if scope!='personal' or state!=('reauthorization_required' if kind=='github_connections' else 'none'):reject('archive_reconciliation_failed')
        values.append([kind,str(source),str(target),str(owner),str(user) if user else None,str(repository) if repository else None,
            metadata,checksum,reference,hashlib.sha256(bytes(ciphertext)).hexdigest() if ciphertext is not None else None])
    if len(rows)!=len(prepared.rows) or _archive_hash(values)!=archive_hash:reject('archive_reconciliation_failed')
    expected={(row.kind,str(row.source_id),str(row.target_id),row.checksum) for row in prepared.rows}
    mappings=connection.execute('''SELECT source_kind,source_id,target_id,source_checksum,target_kind,reconciliation_state
        FROM wpl.migration_mappings WHERE source_namespace=%s''',(prepared.namespace,)).fetchall()
    actual={(kind,source,str(target),checksum) for kind,source,target,checksum,target_kind,state in mappings
        if target_kind=='legacy_archive' and state=='imported'}
    if len(mappings)!=len(expected) or actual!=expected:reject('mapping_reconciliation_failed')
    # Compare immutable metadata/checksums against the current prepared request as
    # well as the stored archive hash; a fresh nonce need not match a committed retry.
    projected={tuple(row[:6])+ (digest(row[6]),row[7]) for row in values}
    required={tuple(value[:6])+(digest(value[6]),value[7]) for value in map(_row_values,prepared.rows)}
    if projected!=required:reject('archive_reconciliation_failed')


def import_prepared(connection,prepared: PreparedImport,*,fixture_owner: str,confirm_source_sha256: str):
    if not isinstance(prepared,PreparedImport) or confirm_source_sha256!=prepared.source_checksum:reject('explicit_import_confirmation_required')
    try:
        with connection.transaction():
            _target(connection,fixture_owner)
            connection.execute("SET LOCAL statement_timeout='5000ms'")
            connection.execute("SET LOCAL lock_timeout='3000ms'")
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,7319))',(prepared.namespace,))
            bound={row.owner_user_id for row in prepared.rows if row.owner_user_id}
            if bound:
                found={row[0] for row in connection.execute('SELECT id FROM wpl.users WHERE id=ANY(%s)',(list(bound),))}
                if found!=bound:reject('mapped_identity_not_present')
            existing=connection.execute('''SELECT source_checksum,source_revision,intent_hash,archive_hash,artifact_count,credential_count
                FROM wpl.legacy_import_runs WHERE source_namespace=%s''',(prepared.namespace,)).fetchone()
            count=sum(row.kind=='github_connections' for row in prepared.rows)
            if existing:
                if (existing[0],existing[1],existing[2],existing[4],existing[5])!=(prepared.source_checksum,prepared.source_revision,prepared.intent_hash,len(prepared.rows),count):
                    reject('source_namespace_conflict')
                _reconcile(connection,prepared,existing[3])
                replayed=True
            else:
                archive_hash=_archive_hash(list(map(_row_values,prepared.rows)))
                connection.execute('''INSERT INTO wpl.legacy_import_runs(source_namespace,source_checksum,source_revision,intent_hash,
                    archive_hash,artifact_count,credential_count,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (prepared.namespace,prepared.source_checksum,prepared.source_revision,prepared.intent_hash,archive_hash,len(prepared.rows),count,prepared.reason))
                for row in prepared.rows:
                    connection.execute('''INSERT INTO wpl.legacy_import_artifacts(source_namespace,target_id,source_kind,source_id,owner_source_id,
                        owner_user_id,repository_source_id,metadata,source_checksum,credential_state,key_reference,ciphertext)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (prepared.namespace,row.target_id,row.kind,row.source_id,row.owner_source_id,row.owner_user_id,row.repository_source_id,
                         Jsonb(dict(row.metadata)),row.checksum,'reauthorization_required' if row.envelope else 'none',
                         row.envelope.key_reference if row.envelope else None,row.envelope.ciphertext if row.envelope else None))
                    connection.execute('''INSERT INTO wpl.migration_mappings(id,source_namespace,source_kind,source_id,target_kind,
                        target_id,reconciliation_state,source_checksum) VALUES (%s,%s,%s,%s,'legacy_archive',%s,'imported',%s)''',
                        (uuid5(NAMESPACE,prepared.namespace+':'+row.kind+':'+str(row.source_id)),prepared.namespace,row.kind,str(row.source_id),row.target_id,row.checksum))
                _reconcile(connection,prepared,archive_hash)
                replayed=False
            return {'mode':'disposable_import','source_namespace':prepared.namespace,'source_sha256':prepared.source_checksum,
                'source_revision':prepared.source_revision,'artifact_count':len(prepared.rows),'encrypted_credential_count':count,
                'credentials':'reauthorization_required','scope':'personal','identity_bindings':len(bound),'replayed':replayed,
                'organizations_created':0,'memberships_created':0,'runtime_activation':'none'}
    except psycopg.Error:raise RehearsalError('target_import_failed') from None
