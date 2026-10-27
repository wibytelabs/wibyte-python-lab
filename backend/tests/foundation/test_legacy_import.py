"""Confirmed personal archival import into the actual owned disposable Postgres target."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID,uuid4
import psycopg
from psycopg import sql
from backend.app.domains.jobs.payloads import PayloadCipher,PayloadKeyUnavailable,EncryptedPayload
from backend.app.domains.migration.snapshot import ARCHIVE_POLICY,inspect_snapshot,HISTORICAL
from backend.app.domains.migration.importer import RehearsalError,prepare_import,import_prepared,credential_binding
from backend.app.domains.migration.cli_inputs import FileKeys,read_bindings
from backend.app.foundation.migrate import migrate
from legacy_fixture import fixture,historical_fixture,STUDENT,OTHER,REPOSITORY,ACCESS,REFRESH
from test_payloads import SyntheticKeys
from test_schema import connect

ROOT=Path(__file__).resolve().parents[3]


class LegacyImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=fixture(Path(self.directory.name)/'generated.snapshot.sqlite3')
        self.namespace='fixture-'+uuid4().hex
        self.owner=os.environ['WPL_REHEARSAL_OWNER']
        self.keys=SyntheticKeys();self.cipher=PayloadCipher(self.keys)

    def snapshot(self,path=None):
        path=path or self.path
        return inspect_snapshot(path,hashlib.sha256(path.read_bytes()).hexdigest(),historical_policy=ARCHIVE_POLICY)

    def prepare(self,**kwargs):
        return prepare_import(self.snapshot(),self.namespace,'Synthetic personal migration rehearsal',self.cipher,**kwargs)

    def run_import(self,prepared=None):
        prepared=prepared or self.prepare()
        with connect() as connection:
            return import_prepared(connection,prepared,fixture_owner=self.owner,confirm_source_sha256=prepared.source_checksum)

    def count(self):
        with connect() as connection:
            return connection.execute('SELECT count(*) FROM wpl.legacy_import_artifacts WHERE source_namespace=%s',(self.namespace,)).fetchone()[0]

    def test_import_maps_all_personal_records_and_reconciles_source_uuid_owner_repository_and_counts(self):
        source=self.path.read_bytes();prepared=self.prepare()
        with connect() as connection:
            before=connection.execute('SELECT (SELECT count(*) FROM wpl.users),(SELECT count(*) FROM wpl.organizations),(SELECT count(*) FROM wpl.organization_memberships)').fetchone()
        result=self.run_import(prepared);self.assertEqual(result['artifact_count'],5);self.assertEqual(result['scope'],'personal')
        self.assertEqual(result['organizations_created'],0);self.assertEqual(result['memberships_created'],0)
        with connect() as connection:
            after=connection.execute('SELECT (SELECT count(*) FROM wpl.users),(SELECT count(*) FROM wpl.organizations),(SELECT count(*) FROM wpl.organization_memberships)').fetchone()
            self.assertEqual(before,after)
            rows=connection.execute('SELECT source_kind,source_id,target_id,owner_source_id,owner_user_id,repository_source_id FROM wpl.legacy_import_artifacts WHERE source_namespace=%s',(self.namespace,)).fetchall()
            self.assertEqual({(row[0],row[1],row[2]) for row in rows},{(row.kind,row.source_id,row.target_id) for row in prepared.rows})
            self.assertTrue(all(row[4] is None for row in rows))
            lab=next(row for row in rows if row[0]=='labs');self.assertEqual(lab[3],UUID(STUDENT));self.assertEqual(lab[5],UUID(REPOSITORY))
            mappings=connection.execute('SELECT count(*) FROM wpl.migration_mappings WHERE source_namespace=%s AND reconciliation_state=\'imported\'',(self.namespace,)).fetchone()[0]
            self.assertEqual(mappings,5)
        self.assertEqual(self.path.read_bytes(),source)
        print('Actual disposable legacy import: five personal artifacts/mappings reconciled; source bytes, existing users/orgs/memberships unchanged; no runtime activation.',flush=True)

    def test_actual_ciphertext_round_trip_and_private_metadata_never_contain_raw_tokens(self):
        prepared=self.prepare();self.run_import(prepared)
        credential=next(row for row in prepared.rows if row.kind=='github_connections')
        with connect() as connection:
            row=connection.execute('SELECT metadata,key_reference,ciphertext,credential_state,scope_kind FROM wpl.legacy_import_artifacts WHERE source_namespace=%s AND source_kind=\'github_connections\'',(self.namespace,)).fetchone()
        self.assertEqual(row[3:],('reauthorization_required','personal'))
        for value in (ACCESS,REFRESH):self.assertNotIn(value,json.dumps(row[0]));self.assertNotIn(value.encode(),bytes(row[2]))
        clear=self.cipher.decrypt(EncryptedPayload(row[1],bytes(row[2])),credential_binding(self.namespace,credential.owner_target_id,credential.target_id))
        self.assertEqual(clear['access_token'],ACCESS);self.assertEqual(clear['refresh_token'],REFRESH)
        self.assertNotIn(ACCESS,repr(prepared));self.assertNotIn(REFRESH,repr(prepared.rows))

    def test_new_pool_same_source_replay_keeps_original_ciphertext_and_one_committed_archive(self):
        first=self.prepare();second=self.prepare();a=next(row for row in first.rows if row.envelope);b=next(row for row in second.rows if row.envelope)
        self.assertNotEqual(a.envelope.ciphertext,b.envelope.ciphertext)
        self.assertFalse(self.run_import(first)['replayed']);self.assertTrue(self.run_import(second)['replayed']);self.assertEqual(self.count(),5)
        with connect() as connection:
            stored=connection.execute('SELECT ciphertext FROM wpl.legacy_import_artifacts WHERE source_namespace=%s AND source_kind=\'github_connections\'',(self.namespace,)).fetchone()[0]
        self.assertEqual(bytes(stored),a.envelope.ciphertext)

    def test_two_actual_migrator_connections_serialize_same_namespace_and_return_one_replayed_result(self):
        prepared=self.prepare()
        with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(lambda _index:self.run_import(prepared),range(2)))
        self.assertEqual(sorted(result['replayed'] for result in results),[False,True]);self.assertEqual(self.count(),5)
        print('Actual concurrent disposable imports: one committed archive, one reconciled replay; stable UUID/owner/repository mappings and original ciphertext retained.',flush=True)

    def test_changed_source_or_identity_binding_conflicts_without_overwriting_prior_archive(self):
        self.run_import()
        with sqlite3.connect(self.path) as connection:connection.execute("UPDATE students SET name='Changed synthetic profile' WHERE id=?",(STUDENT,))
        with self.assertRaises(RehearsalError) as rejected:self.run_import()
        self.assertEqual(rejected.exception.code,'source_namespace_conflict');self.assertEqual(self.count(),5)

    def test_explicit_binding_requires_existing_distinct_uuid_and_does_not_approve_or_assign_tenant(self):
        user=uuid4()
        with connect() as connection:connection.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'pending')",(user,))
        prepared=self.prepare(identity_bindings={UUID(STUDENT):user});result=self.run_import(prepared)
        self.assertEqual(result['identity_bindings'],1)
        with connect() as connection:
            self.assertEqual(connection.execute('SELECT global_state FROM wpl.users WHERE id=%s',(user,)).fetchone()[0],'pending')
            self.assertEqual(connection.execute('SELECT count(*) FROM wpl.organization_memberships WHERE user_id=%s',(user,)).fetchone()[0],0)
            self.assertEqual(connection.execute('SELECT count(*) FROM wpl.legacy_import_artifacts WHERE source_namespace=%s AND owner_user_id=%s',(self.namespace,user)).fetchone()[0],4)
        for mapping in ({UUID(STUDENT):user,UUID(OTHER):user},{uuid4():user},{UUID(STUDENT):'duplicate@example.invalid'}):
            with self.subTest(mapping_type='explicit IDs'):
                with self.assertRaises(RehearsalError):self.prepare(identity_bindings=mapping)
        another=prepare_import(self.snapshot(),self.namespace,'Synthetic personal migration rehearsal',self.cipher,identity_bindings={UUID(STUDENT):uuid4()})
        with self.assertRaises(RehearsalError):self.run_import(another)
        self.assertEqual(self.count(),5)

    def test_missing_bound_identity_or_bad_confirmation_and_target_marker_create_no_rows(self):
        prepared=self.prepare(identity_bindings={UUID(STUDENT):uuid4()})
        with self.assertRaises(RehearsalError):self.run_import(prepared)
        prepared=self.prepare()
        with connect() as connection:
            for owner,confirmation in ((self.owner,'0'*64),('0'*32,prepared.source_checksum)):
                with self.assertRaises(RehearsalError):import_prepared(connection,prepared,fixture_owner=owner,confirm_source_sha256=confirmation)
        with connect('APPLICATION') as connection:
            with self.assertRaises(RehearsalError):import_prepared(connection,prepared,fixture_owner=self.owner,confirm_source_sha256=prepared.source_checksum)
        self.assertEqual(self.count(),0)

    def test_real_mapping_constraint_failure_rolls_back_prior_artifacts_and_run_even_when_caught(self):
        prepared=self.prepare();constraint='fixture_import_'+uuid4().hex
        with connect() as owner:owner.execute(sql.SQL('ALTER TABLE wpl.migration_mappings ADD CONSTRAINT {} CHECK(source_namespace<>{}) NOT VALID').format(sql.Identifier(constraint),sql.Literal(self.namespace)))
        try:
            with connect() as connection:
                connection.execute('SELECT 1')
                with self.assertRaises(RehearsalError):import_prepared(connection,prepared,fixture_owner=self.owner,confirm_source_sha256=prepared.source_checksum)
                self.assertEqual(connection.execute('SELECT count(*) FROM wpl.legacy_import_runs WHERE source_namespace=%s',(self.namespace,)).fetchone()[0],0)
                self.assertEqual(connection.execute('SELECT count(*) FROM wpl.legacy_import_artifacts WHERE source_namespace=%s',(self.namespace,)).fetchone()[0],0)
            self.assertEqual(self.count(),0)
        finally:
            with connect() as owner:owner.execute(sql.SQL('ALTER TABLE wpl.migration_mappings DROP CONSTRAINT {}').format(sql.Identifier(constraint)))
        self.assertFalse(self.run_import(prepared)['replayed'])

    def test_outer_rollback_discards_all_rows_and_replay_refuses_corrupted_reconciliation(self):
        prepared=self.prepare()
        with connect() as connection:
            connection.execute('SELECT 1')
            import_prepared(connection,prepared,fixture_owner=self.owner,confirm_source_sha256=prepared.source_checksum)
            connection.rollback()
        self.assertEqual(self.count(),0);self.run_import(prepared)
        with connect() as connection:connection.execute("UPDATE wpl.migration_mappings SET source_checksum=repeat('0',64) WHERE source_namespace=%s",(self.namespace,))
        with self.assertRaises(RehearsalError) as rejected:self.run_import(prepared)
        self.assertEqual(rejected.exception.code,'mapping_reconciliation_failed');self.assertEqual(self.count(),5)

    def test_app_worker_cannot_read_archive_secrets_and_actual_archive_rows_are_immutable(self):
        self.run_import()
        for kind in ('APPLICATION','WORKER'):
            with connect(kind) as connection:
                for table in ('legacy_import_runs','legacy_import_artifacts'):
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):connection.execute(sql.SQL('SELECT * FROM wpl.{}').format(sql.Identifier(table)))
                    connection.rollback()
        with connect() as connection:
            for table in ('legacy_import_runs','legacy_import_artifacts'):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with connection.transaction():connection.execute(sql.SQL('DELETE FROM wpl.{} WHERE source_namespace=%s').format(sql.Identifier(table)),(self.namespace,))
            with self.assertRaises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute('''INSERT INTO wpl.legacy_import_artifacts(source_namespace,target_id,source_kind,source_id,owner_source_id,metadata,
                        source_checksum,credential_state) VALUES (%s,%s,'labs',%s,%s,%s,%s,'none')''',
                        (self.namespace,uuid4(),uuid4(),UUID(STUDENT),psycopg.types.json.Jsonb({'access_token':ACCESS}),'0'*64))
        self.assertEqual(self.count(),5)

    def test_historical_credentials_stay_encrypted_disabled_and_missing_refresh_expiry_remain_unknown(self):
        historical=historical_fixture(Path(self.directory.name)/'historical.snapshot.sqlite3');snapshot=self.snapshot(historical)
        prepared=prepare_import(snapshot,self.namespace,'Synthetic personal migration rehearsal',self.cipher)
        self.assertEqual(self.run_import(prepared)['source_revision'],HISTORICAL)
        credential=next(row for row in prepared.rows if row.envelope)
        clear=self.cipher.decrypt(credential.envelope,credential_binding(self.namespace,credential.owner_target_id,credential.target_id))
        self.assertEqual(clear['access_token'],ACCESS)
        for key in ('refresh_token','access_token_expires_at','refresh_token_expires_at'):self.assertNotIn(key,clear)
        with connect() as connection:self.assertEqual(connection.execute("SELECT credential_state FROM wpl.legacy_import_artifacts WHERE source_namespace=%s AND source_kind='github_connections'",(self.namespace,)).fetchone()[0],'reauthorization_required')

    def test_key_failure_is_before_target_connection_and_private_mapping_key_inputs_are_bounded(self):
        class MissingKeys:
            def current_reference(self):return 'fixture/missing'
            def resolve(self,_reference):raise RuntimeError(ACCESS)
        with patch.object(psycopg,'connect',side_effect=AssertionError('No target connection in preparation')):
            with self.assertRaises(PayloadKeyUnavailable) as rejected:prepare_import(self.snapshot(),self.namespace,'Synthetic migration reason',PayloadCipher(MissingKeys()))
        self.assertNotIn(ACCESS,str(rejected.exception));self.assertEqual(self.count(),0)
        key=Path(self.directory.name)/'key';key.write_bytes(b'k'*32);key.chmod(0o600)
        self.assertEqual(FileKeys(key,'fixture/key').resolve('fixture/key'),b'k'*32)
        key.chmod(0o644)
        with self.assertRaises(RehearsalError):FileKeys(key,'fixture/key')
        bindings=Path(self.directory.name)/'bindings.json';bindings.write_text('{"'+STUDENT+'":"'+OTHER+'","'+STUDENT+'":"'+OTHER+'"}');bindings.chmod(0o600)
        with self.assertRaises(RehearsalError):read_bindings(bindings)

    def test_actual_cli_confirmed_import_commits_then_replays_and_rejects_nonfixture_target_without_details(self):
        key=Path(self.directory.name)/'key';key.write_bytes(b'k'*32);key.chmod(0o600)
        checksum=hashlib.sha256(self.path.read_bytes()).hexdigest()
        command=[sys.executable,str(ROOT/'scripts/rehearse_legacy.py'),'--snapshot',str(self.path),'--sha256',checksum,
            '--confirm-disposable-import','--confirm-source-sha256',checksum,'--disposable-target-url',os.environ['WPL_MIGRATION_DATABASE_URL'],
            '--fixture-owner',self.owner,'--source-namespace',self.namespace,'--reason','Synthetic personal migration rehearsal','--key-file',str(key),'--key-reference','fixture/key']
        settings={'cwd':'/tmp','capture_output':True,'text':True,'timeout':20,'env':{'PATH':os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'}}
        first=subprocess.run(command,**settings);self.assertEqual(first.returncode,0,first.stderr);self.assertFalse(json.loads(first.stdout)['replayed'])
        second=subprocess.run(command,**settings);self.assertEqual(second.returncode,0,second.stderr);self.assertTrue(json.loads(second.stdout)['replayed'])
        self.assertNotIn(ACCESS,first.stdout+first.stderr+second.stdout+second.stderr)
        denied=subprocess.run(command+['--disposable-target-url','postgresql://synthetic:private-dsn-marker@external.invalid/production'],**settings)
        self.assertEqual(denied.returncode,2);self.assertNotIn('private-dsn-marker',denied.stdout+denied.stderr)
