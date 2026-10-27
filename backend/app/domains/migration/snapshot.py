"""Bounded read-only snapshot validation. No env, provider, ORM or target connection."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from types import MappingProxyType
from uuid import UUID,uuid5

HEAD='7d8e63fb45c3'
HISTORICAL='553a7ddf4183'
ARCHIVE_POLICY='archive_for_reauthorization'
MAX_BYTES=64*1024*1024
MAX_ROWS=10000
NAMESPACE=UUID('fbbd719c-e560-45e8-9f1c-5ec9f556b02f')
COLUMNS={
    'students':('id','name','email','created_at','updated_at'),
    'github_connections':('id','student_id','github_user_id','github_username','access_token','refresh_token',
        'access_token_expires_at','refresh_token_expires_at','connected_at','updated_at'),
    'github_repositories':('id','student_id','github_repo_id','owner','name','full_name','default_branch','created_at','updated_at'),
    'labs':('id','student_id','github_repository_id','container_id','status','created_at','last_activity_at'),
}

class SnapshotError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__('Legacy snapshot rejected: '+code+'. No source or target changes were made.')

@dataclass(frozen=True)
class LegacyRecord:
    kind: str
    source_id: UUID
    target_id: UUID
    owner_source_id: UUID
    values: object=field(repr=False)

@dataclass(frozen=True)
class Snapshot:
    checksum: str
    records: tuple[LegacyRecord,...]=field(repr=False)
    source_revision: str=HEAD

    def report(self):
        counts={name:sum(row.kind==name for row in self.records) for name in COLUMNS}
        identifiers=[[row.kind,str(row.source_id),str(row.target_id),str(row.owner_source_id)] for row in self.records]
        mapping_hash=hashlib.sha256(json.dumps(identifiers,separators=(',',':')).encode()).hexdigest()
        return {'mode':'dry_run','source_revision':self.source_revision,'source_sha256':self.checksum,'counts':counts,
            'mapping_sha256':mapping_hash,'personal_records':len(self.records),'target_mutations':0,
            'identity_binding':'explicit_mapping_required','organization_assignment':'none',
            'credentials':'historical_credentials_require_reauthorization' if self.source_revision==HISTORICAL else 'private_source_only_not_printed',
            'disabled_credential_records':counts['github_connections'] if self.source_revision==HISTORICAL else 0,
            'historical_policy':ARCHIVE_POLICY if self.source_revision==HISTORICAL else 'none','workspace_files':'not_read_or_exported'}

def reject(code):raise SnapshotError(code)

def _read(path,expected):
    if not isinstance(path,Path) or not path.is_absolute() or not path.name.endswith('.snapshot.sqlite3'):
        reject('explicit_snapshot_path_required')
    if not isinstance(expected,str) or re.fullmatch(r'[0-9a-f]{64}',expected) is None:reject('source_checksum_required')
    for suffix in ('-wal','-shm','-journal'):
        if os.path.lexists(str(path)+suffix):reject('snapshot_sidecar_present')
    descriptor=None
    try:
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        before=os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:reject('private_regular_copy_required')
        if before.st_uid!=os.getuid() or before.st_mode&0o077:reject('private_snapshot_permissions_required')
        if not 512<=before.st_size<=MAX_BYTES:reject('snapshot_size_invalid')
        chunks=[];size=0
        while True:
            chunk=os.read(descriptor,min(1024*1024,MAX_BYTES+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if size>MAX_BYTES:reject('snapshot_size_invalid')
        after=os.fstat(descriptor)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(
            after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):reject('snapshot_changed_during_read')
        data=b''.join(chunks)
        if not data.startswith(b'SQLite format 3\x00') or hashlib.sha256(data).hexdigest()!=expected:reject('source_checksum_or_format_invalid')
        return data
    except OSError:raise SnapshotError('snapshot_unavailable_or_unsafe') from None
    finally:
        if descriptor is not None:os.close(descriptor)

def _uuid(value):
    try:
        result=UUID(value)
        if str(result)!=value or result.int==0:reject('invalid_source_uuid')
        return result
    except (ValueError,TypeError,AttributeError):raise SnapshotError('invalid_source_uuid') from None

def _text(value,maximum,*,nullable=False):
    if nullable and value is None:return
    if not isinstance(value,str) or not 1<=len(value)<=maximum or any(ord(char)<32 or ord(char)==127 for char in value):reject('invalid_source_text')

def _time(value):
    try:
        result=datetime.fromisoformat(value)
        if result.tzinfo is None:result=result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc).isoformat()
    except (ValueError,TypeError,OverflowError):raise SnapshotError('invalid_source_timestamp') from None

def inspect_snapshot(path: Path,expected_sha256: str,*,historical_policy: str | None=None) -> Snapshot:
    if historical_policy not in (None,ARCHIVE_POLICY):reject('unsupported_historical_policy')
    data=_read(path,expected_sha256)
    connection=sqlite3.connect(':memory:')
    try:
        connection.deserialize(data)
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024*1024)
        ticks=[0]
        def bound():
            ticks[0]+=1
            return int(ticks[0]>10000)
        connection.set_progress_handler(bound,1000)
        if connection.execute('PRAGMA quick_check(1)').fetchone()!=('ok',):reject('source_integrity_failed')
        objects=connection.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
        allowed=set(COLUMNS)|{'alembic_version','inactivity_notices'}
        if any(kind!='table' or name not in allowed or not sql or 'CREATE VIRTUAL' in sql.upper() for kind,name,sql in objects):reject('unsupported_source_schema')
        if not (set(COLUMNS)|{'alembic_version'})<=set(name for _kind,name,_sql in objects):reject('missing_source_tables')
        revisions=connection.execute('SELECT version_num FROM alembic_version').fetchall()
        if len(revisions)!=1 or revisions[0][0] not in (HEAD,HISTORICAL):reject('historical_revision_requires_review')
        revision=revisions[0][0]
        if revision==HISTORICAL and historical_policy!=ARCHIVE_POLICY:reject('historical_revision_requires_review')
        columns_by_table=dict(COLUMNS)
        if revision==HISTORICAL:
            # Read the original schema directly. Never apply/stamp a failed revision,
            # invent a refresh token/expiry or turn an old credential into active access.
            columns_by_table['students']=('id','created_at')
            columns_by_table['github_connections']=tuple(column for column in COLUMNS['github_connections']
                if column not in ('refresh_token','access_token_expires_at','refresh_token_expires_at'))
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:reject('orphan_source_relationship')
        tables={}
        for name,columns in columns_by_table.items():
            actual={item[1] for item in connection.execute('PRAGMA table_info('+name+')')}
            if not set(columns)<=actual:reject('missing_source_columns')
            if actual!=set(columns):reject('unsupported_source_columns')
            result=connection.execute('SELECT '+','.join(columns)+' FROM '+name+' ORDER BY id LIMIT ?', (MAX_ROWS+1,)).fetchall()
            if len(result)>MAX_ROWS:reject('source_row_bound_exceeded')
            tables[name]=[dict(zip(columns,row)) for row in result]
        if sum(map(len,tables.values()))>25000:reject('source_row_bound_exceeded')
        owners={};repositories={};seen={name:set() for name in COLUMNS};connections=set();github_users=set();repo_ids=set();repo_names=set()
        records=[]
        for name,rows in tables.items():
            for row in rows:
                source=_uuid(row['id'])
                if source in seen[name]:reject('duplicate_source_identity')
                seen[name].add(source)
                owner=source if name=='students' else _uuid(row['student_id'])
                if name=='students':
                    owners[source]=True
                    _text(row.get('name'),100,nullable=True);_text(row.get('email'),255,nullable=True)
                elif owner not in owners:reject('orphan_source_relationship')
                for column in row:
                    if column.endswith('_at'):row[column]=_time(row[column])
                if name=='github_connections':
                    if owner in connections:reject('ambiguous_connection_owner')
                    connections.add(owner)
                    value=row['github_user_id']
                    if not isinstance(value,str) or re.fullmatch(r'[1-9][0-9]{0,63}',value) is None:reject('invalid_github_identity')
                    if value in github_users:reject('ambiguous_github_identity')
                    github_users.add(value)
                    _text(row['github_username'],255)
                    for column in ('access_token','refresh_token'):
                        if column in row:_text(row[column],512)
                elif name=='github_repositories':
                    value=row['github_repo_id']
                    if not isinstance(value,str) or re.fullmatch(r'[1-9][0-9]{0,63}',value) is None:reject('invalid_repository_identity')
                    for column in ('owner','name'):
                        _text(row[column],255)
                        if re.fullmatch(r'[A-Za-z0-9_.-]+',row[column]) is None or row[column] in ('.','..'):reject('invalid_repository_name')
                    if row['full_name']!=row['owner']+'/'+row['name']:reject('repository_owner_name_mismatch')
                    _text(row['default_branch'],255)
                    full=row['full_name'].lower()
                    if value in repo_ids or full in repo_names:reject('ambiguous_repository_identity')
                    repo_ids.add(value);repo_names.add(full);repositories[source]=owner
                elif name=='labs':
                    _text(row['container_id'],128);_text(row['status'],32)
                    reference=row['github_repository_id']
                    if reference is not None and repositories.get(_uuid(reference))!=owner:reject('repository_owner_mismatch')
                records.append(LegacyRecord(name,source,uuid5(NAMESPACE,name+':'+str(source)),owner,MappingProxyType(row)))
        return Snapshot(expected_sha256,tuple(records),revision)
    except sqlite3.Error:raise SnapshotError('source_database_invalid_or_bounded') from None
    finally:connection.close()
