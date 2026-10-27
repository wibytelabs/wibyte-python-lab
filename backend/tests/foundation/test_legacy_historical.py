"""Supported old schema is archived explicitly without inventing credential validity."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from backend.app.domains.migration.snapshot import ARCHIVE_POLICY,HISTORICAL,HEAD,SnapshotError,inspect_snapshot
from legacy_fixture import historical_fixture,STUDENT,OTHER,ACCESS,REFRESH

ROOT=Path(__file__).resolve().parents[3]


class HistoricalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=historical_fixture(Path(self.directory.name)/'historical.snapshot.sqlite3')

    def inspect(self,policy=ARCHIVE_POLICY):
        return inspect_snapshot(self.path,hashlib.sha256(self.path.read_bytes()).hexdigest(),historical_policy=policy)

    def test_explicit_old_schema_read_preserves_source_and_actual_revision_without_upgrade_or_stamp(self):
        before=self.path.read_bytes();modified=self.path.stat().st_mtime_ns;snapshot=self.inspect()
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(self.path.stat().st_mtime_ns,modified)
        self.assertEqual(snapshot.source_revision,HISTORICAL)
        self.assertEqual(snapshot.report()['source_revision'],HISTORICAL)
        self.assertEqual(snapshot.report()['counts'],{'students':2,'github_connections':1,'github_repositories':1,'labs':1})
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT version_num FROM alembic_version').fetchone()[0],HISTORICAL)
        print('Actual populated historical compatibility: original revision/bytes retained; explicit archival plan marks credentials for reauthorization, no migration/stamp/provider call.',flush=True)

    def test_missing_profile_refresh_and_expiry_values_remain_absent_and_all_old_credentials_are_disabled(self):
        snapshot=self.inspect();credential=next(row for row in snapshot.records if row.kind=='github_connections')
        self.assertEqual(credential.values['access_token'],ACCESS)
        for field in ('refresh_token','access_token_expires_at','refresh_token_expires_at'):
            self.assertNotIn(field,credential.values)
        profile=next(row for row in snapshot.records if row.kind=='students')
        for field in ('name','email','updated_at'):self.assertNotIn(field,profile.values)
        report=snapshot.report();self.assertEqual(report['disabled_credential_records'],1)
        self.assertEqual(report['credentials'],'historical_credentials_require_reauthorization')
        self.assertEqual(report['historical_policy'],ARCHIVE_POLICY)
        self.assertEqual(report['identity_binding'],'explicit_mapping_required')
        self.assertEqual(report['organization_assignment'],'none')
        for value in (ACCESS,REFRESH,'synthetic-owner'):
            self.assertNotIn(value,json.dumps(report)+repr(snapshot)+repr(snapshot.records))

    def test_default_and_unknown_policy_cannot_silently_adopt_historical_schema(self):
        for policy in (None,'automatic_upgrade','infer_expiry',''):
            with self.subTest(policy=policy):
                with self.assertRaises(SnapshotError):self.inspect(policy)

    def test_policy_does_not_adopt_an_unknown_or_partially_upgraded_revision(self):
        for revision in ('3e58a6eb699a','unknown',HEAD):
            with self.subTest(revision=revision):
                with sqlite3.connect(self.path) as connection:connection.execute('UPDATE alembic_version SET version_num=?',(revision,))
                with self.assertRaises(SnapshotError):self.inspect()
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE alembic_version SET version_num=?',(HISTORICAL,))
            connection.execute('ALTER TABLE github_connections ADD COLUMN refresh_token TEXT')
        with self.assertRaises(SnapshotError) as rejected:self.inspect()
        self.assertEqual(rejected.exception.code,'unsupported_source_columns')

    def test_old_schema_still_rejects_cross_owner_repository_binding_and_missing_credentials(self):
        with sqlite3.connect(self.path) as connection:connection.execute('UPDATE labs SET student_id=?',(OTHER,))
        with self.assertRaises(SnapshotError) as rejected:self.inspect()
        self.assertEqual(rejected.exception.code,'repository_owner_mismatch')
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE labs SET student_id=?',(STUDENT,))
            connection.execute("UPDATE github_connections SET access_token=''")
        with self.assertRaises(SnapshotError):self.inspect()

    def test_actual_cli_requires_explicit_archival_policy_and_preserves_old_revision_in_safe_report(self):
        command=[sys.executable,str(ROOT/'scripts/rehearse_legacy.py'),'--snapshot',str(self.path),'--sha256',hashlib.sha256(self.path.read_bytes()).hexdigest()]
        settings={'cwd':'/tmp','capture_output':True,'text':True,'timeout':10,'env':{'PATH':os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1'}}
        rejected=subprocess.run(command,**settings);self.assertEqual(rejected.returncode,2)
        result=subprocess.run(command+['--historical-policy',ARCHIVE_POLICY],**settings)
        self.assertEqual(result.returncode,0,result.stderr);report=json.loads(result.stdout)
        self.assertEqual(report['source_revision'],HISTORICAL);self.assertEqual(report['disabled_credential_records'],1)
        self.assertNotIn(ACCESS,result.stdout+result.stderr)
