"""Read-only synthetic snapshots and populated historical-chain compatibility evidence."""
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from sqlalchemy.exc import DBAPIError
from backend.app.domains.migration.snapshot import HEAD,SnapshotError,inspect_snapshot
from legacy_fixture import fixture,upgrade,REVISIONS,STUDENT,OTHER,CONNECTION,REPOSITORY,ACCESS,REFRESH,NOW

ROOT=Path(__file__).resolve().parents[3]

def checksum(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class LegacySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=fixture(Path(self.directory.name)/'generated.snapshot.sqlite3')

    def inspect(self):return inspect_snapshot(self.path,checksum(self.path))

    def edit(self,sql,parameters=()):
        with sqlite3.connect(self.path) as connection:connection.execute(sql,parameters)

    def test_actual_empty_historical_chain_generates_current_populated_snapshot_without_legacy_import(self):
        snapshot=self.inspect()
        self.assertEqual(snapshot.report()['source_revision'],HEAD)
        self.assertEqual(snapshot.report()['counts'],{'students':2,'github_connections':1,'github_repositories':1,'labs':1})
        self.assertEqual(snapshot.report()['personal_records'],5)
        for name in ('backend.app.main','backend.app.config','backend.app.db.database'):
            self.assertNotIn(name,sys.modules)
        self.assertEqual(len({record.target_id for record in snapshot.records}),5)
        with self.assertRaises(TypeError):snapshot.records[0].values['name']='changed'

    def test_populated_pre_expiry_historical_revision_fails_explicitly_and_is_not_silently_stamped(self):
        old=Path(self.directory.name)/'historical.snapshot.sqlite3'
        for revision in REVISIONS[:2]:upgrade(old,revision)
        with sqlite3.connect(old) as connection:
            connection.execute('INSERT INTO students VALUES (?,?)',(STUDENT,NOW))
            connection.execute('INSERT INTO github_connections VALUES (?,?,?,?,?,?,?)',
                (CONNECTION,STUDENT,'12345','synthetic-owner',ACCESS,NOW,NOW))
        with self.assertRaises(DBAPIError) as result:upgrade(old,REVISIONS[2])
        self.assertIn('cannot add a not null column',str(result.exception.orig).lower())
        with sqlite3.connect(old) as connection:
            self.assertEqual(connection.execute('SELECT version_num FROM alembic_version').fetchone()[0],REVISIONS[1])
            self.assertEqual(connection.execute('SELECT count(*) FROM github_connections').fetchone()[0],1)
        with self.assertRaises(SnapshotError) as rejected:inspect_snapshot(old,checksum(old))
        self.assertEqual(rejected.exception.code,'historical_revision_requires_review')
        print('Actual populated legacy revision 553a7ddf4183: unchanged NOT NULL token-expiry upgrade rejected; snapshot requires explicit compatibility review, no invented expiry or silent stamp.',flush=True)

    def test_dry_run_changes_neither_source_bytes_nor_actual_disposable_target(self):
        from test_schema import connect
        with connect() as owner:
            before=owner.execute('SELECT (SELECT count(*) FROM wpl.users),(SELECT count(*) FROM wpl.organizations),(SELECT count(*) FROM wpl.migration_mappings)').fetchone()
        original=self.path.read_bytes();before_stat=self.path.stat()
        with patch.object(socket.socket,'connect',side_effect=AssertionError('No target/provider network during dry run')):
            report=self.inspect().report()
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(self.path.stat().st_mtime_ns,before_stat.st_mtime_ns)
        with connect() as owner:
            after=owner.execute('SELECT (SELECT count(*) FROM wpl.users),(SELECT count(*) FROM wpl.organizations),(SELECT count(*) FROM wpl.migration_mappings)').fetchone()
        self.assertEqual(before,after);self.assertEqual(report['target_mutations'],0)
        print('Actual snapshot dry run: source bytes/mtime and disposable users/orgs/mappings unchanged; no target/provider connection in inspector.',flush=True)

    def test_report_and_repr_never_print_profile_credentials_repository_or_container_values(self):
        snapshot=self.inspect();output=json.dumps(snapshot.report())+repr(snapshot)+repr(snapshot.records)
        for value in (ACCESS,REFRESH,'duplicate@example.invalid','Synthetic fixture','synthetic-owner','synthetic-container-id'):
            self.assertNotIn(value,output)
        self.assertEqual(snapshot.report()['identity_binding'],'explicit_mapping_required')
        self.assertEqual(snapshot.report()['organization_assignment'],'none')
        # Duplicate profile emails are preserved as profile data, never used as an identity key.
        students=[record for record in snapshot.records if record.kind=='students']
        self.assertEqual(len(students),2)
        self.assertNotEqual(students[0].target_id,students[1].target_id)

    def test_repeated_snapshot_inspection_has_stable_uuid_and_owner_repository_references(self):
        first=self.inspect();second=self.inspect()
        self.assertEqual(first.report(),second.report())
        identifiers={record.kind:record for record in first.records if record.kind!='students'}
        self.assertEqual(identifiers['github_repositories'].source_id.hex,REPOSITORY.replace('-',''))
        self.assertEqual(str(identifiers['github_repositories'].owner_source_id),STUDENT)
        self.assertEqual(identifiers['labs'].values['github_repository_id'],REPOSITORY)
        self.assertEqual(identifiers['github_connections'].values['access_token'],ACCESS)

    def test_path_checksum_permission_symlink_hardlink_and_sidecar_guards_fail_before_sqlite(self):
        with patch('backend.app.domains.migration.snapshot.sqlite3.connect',side_effect=AssertionError('Guard must run first')):
            for path,value in ((Path('relative.snapshot.sqlite3'),checksum(self.path)),(self.path,'not-a-checksum'),(self.path,'0'*64)):
                with self.subTest(case=str(path)):
                    with self.assertRaises(SnapshotError):inspect_snapshot(path,value)
            os.chmod(self.path,0o644)
            with self.assertRaises(SnapshotError):self.inspect()
            os.chmod(self.path,0o600)
            linked=self.path.with_name('link.snapshot.sqlite3');linked.symlink_to(self.path)
            with self.assertRaises(SnapshotError):inspect_snapshot(linked,checksum(self.path))
            linked.unlink();os.link(self.path,linked)
            with self.assertRaises(SnapshotError):self.inspect()
            linked.unlink()
            sidecar=Path(str(self.path)+'-wal');sidecar.write_bytes(b'synthetic')
            with self.assertRaises(SnapshotError):self.inspect()

    def test_source_integrity_revision_columns_and_extra_executable_schema_are_rejected(self):
        self.edit("UPDATE alembic_version SET version_num='unreviewed'")
        with self.assertRaises(SnapshotError):self.inspect()
        self.edit('UPDATE alembic_version SET version_num=?',(HEAD,))
        self.edit('CREATE VIEW malicious_fixture AS SELECT * FROM students')
        with self.assertRaises(SnapshotError) as result:self.inspect()
        self.assertEqual(result.exception.code,'unsupported_source_schema')
        self.edit('DROP VIEW malicious_fixture')
        self.edit('ALTER TABLE students RENAME COLUMN email TO unknown_email')
        with self.assertRaises(SnapshotError):self.inspect()

    def test_orphan_and_cross_owner_repository_relationships_are_not_importable(self):
        self.edit('UPDATE labs SET student_id=?',(OTHER,))
        with self.assertRaises(SnapshotError) as result:self.inspect()
        self.assertEqual(result.exception.code,'repository_owner_mismatch')
        self.edit('UPDATE labs SET student_id=?',(STUDENT,))
        self.edit("UPDATE github_repositories SET student_id='99999999-9999-4999-8999-999999999999'")
        with self.assertRaises(SnapshotError):self.inspect()

    def test_repository_provider_identity_name_consistency_and_duplicate_ownership_fail_for_review(self):
        self.edit("UPDATE github_repositories SET full_name='different-owner/synthetic-repo'")
        with self.assertRaises(SnapshotError) as result:self.inspect()
        self.assertEqual(result.exception.code,'repository_owner_name_mismatch')
        self.edit("UPDATE github_repositories SET full_name='synthetic-owner/synthetic-repo',github_repo_id='not-numeric'")
        with self.assertRaises(SnapshotError):self.inspect()
        self.edit("UPDATE github_repositories SET github_repo_id='67890'")
        self.edit('INSERT INTO github_repositories SELECT ?,?,github_repo_id,owner,name,full_name,default_branch,created_at,updated_at FROM github_repositories',
            ('88888888-8888-4888-8888-888888888888',OTHER))
        with self.assertRaises(SnapshotError) as result:self.inspect()
        self.assertEqual(result.exception.code,'ambiguous_repository_identity')

    def test_invalid_source_uuid_timestamp_or_secret_shape_is_sanitized(self):
        for column,value in (('access_token',''),('connected_at','invalid timestamp'),('github_user_id','0001')):
            with self.subTest(field=column):
                with sqlite3.connect(self.path) as connection:
                    original=connection.execute('SELECT '+column+' FROM github_connections').fetchone()[0]
                self.edit('UPDATE github_connections SET '+column+'=?',(value,))
                with self.assertRaises(SnapshotError) as result:self.inspect()
                self.assertNotIn(ACCESS,str(result.exception));self.assertNotIn(REFRESH,str(result.exception))
                self.edit('UPDATE github_connections SET '+column+'=?',(original,))
        self.edit("UPDATE students SET id='not-a-uuid' WHERE id=?",(OTHER,))
        with self.assertRaises(SnapshotError):self.inspect()

    def test_empty_snapshot_is_valid_and_source_size_and_row_work_are_bounded(self):
        empty=fixture(Path(self.directory.name)/'empty.snapshot.sqlite3',populated=False)
        self.assertEqual(inspect_snapshot(empty,checksum(empty)).report()['personal_records'],0)
        with patch('backend.app.domains.migration.snapshot.MAX_BYTES',512):
            with self.assertRaises(SnapshotError):self.inspect()
        with patch('backend.app.domains.migration.snapshot.MAX_ROWS',1):
            with self.assertRaises(SnapshotError) as result:self.inspect()
            self.assertEqual(result.exception.code,'source_row_bound_exceeded')

    def test_actual_cli_defaults_to_dry_run_from_tmp_and_outputs_only_the_safe_report(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/rehearse_legacy.py'),'--snapshot',str(self.path),'--sha256',checksum(self.path)],
            cwd='/tmp',capture_output=True,text=True,timeout=10,env={'PATH':os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['target_mutations'],0)
        self.assertNotIn(ACCESS,result.stdout+result.stderr)
        denied=subprocess.run([sys.executable,str(ROOT/'scripts/rehearse_legacy.py'),'--snapshot',str(self.path),'--sha256','0'*64],
            cwd='/tmp',capture_output=True,text=True,timeout=10,env={'PATH':os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'})
        self.assertEqual(denied.returncode,2);self.assertIn('source_checksum_or_format_invalid',denied.stderr)
