"""P02.1: synthetic identities against an actual disposable PostgreSQL server."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import psycopg
from psycopg import pq
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.foundation.settings import FoundationSettings, FoundationConfigurationError, postgres_url
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.migrate import migrate, MIGRATION_LOCK, FoundationMigrationError

def driver_url(value):
    return postgres_url(value, "fixture").set(drivername="postgresql").render_as_string(hide_password=False)

class ConfigurationTests(unittest.TestCase):
    def test_disabled_defaults_need_no_private_or_legacy_settings(self):
        self.assertFalse(FoundationSettings.from_mapping({}).enabled)
        self.assertFalse(FoundationSettings.from_mapping({"WPL_APPLICATION_DATABASE_URL": "invalid"}).enabled)
        with self.assertRaises(FoundationConfigurationError):
            FoundationSettings.from_mapping({"WPL_FOUNDATION_ENABLED": "yes"})

    def test_configuration_is_bounded_and_errors_do_not_echo_credentials(self):
        for value in ("", "secret", "sqlite:///fixture.db", "postgresql://user:secret@host/db?options=unsafe"):
            with self.subTest(value=value):
                with self.assertRaises(FoundationConfigurationError) as result:
                    postgres_url(value, "WPL_APPLICATION_DATABASE_URL")
                self.assertNotIn("secret", str(result.exception))
        with self.assertRaises(FoundationConfigurationError):
            FoundationSettings(enabled=True)
        with self.assertRaises(FoundationConfigurationError):
            FoundationSettings(pool_size=100)

    def test_factory_and_imports_do_not_connect_or_load_legacy(self):
        code = """
import socket, sys
from unittest.mock import patch
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
    from backend.app.domains.identity.settings import IdentitySettings
    from backend.app.domains.identity.verification import build_verifier
    from backend.app.domains.identity.types import VerifiedIdentity
    from backend.app.domains.authorization.context import RequestContext, RequestScope
    from backend.app.domains.authorization.policy import require_tenant_admin
    from backend.app.domains.organizations.service import set_member_status, replace_roles, complete_primary_transfer
    from backend.app.domains.cohorts.service import set_instructors
    from backend.app.domains.jobs.payloads import PayloadCipher, PayloadBinding, PayloadScope
    from backend.app.domains.jobs.idempotency import execute_idempotent, TenantOperation, MutationResult
    from backend.app.domains.jobs.enqueue import prepare_invitation, enqueue_invitation
    from backend.app.domains.jobs.leases import claim_deliveries, renew_delivery
    from backend.app.domains.jobs.transitions import load_delivery, authorize_delivery, finish_delivery
    from backend.app.domains.jobs.execution import process_delivery, DeliveryAcknowledgement
    from backend.app.domains.organizations.directory import require_organization_directory
    from backend.app.domains.organizations.metadata import change_organization
    from backend.app.domains.organizations.requests import OrganizationPatch, OrganizationStatus, OrganizationCreate
    from backend.app.domains.organizations.provisioning import prepare_organization, create_organization, find_organization_creation
    from backend.app.domains.jobs.transitions import DeliveryMaterial
    from backend.app.foundation.app import create_app
    from backend.app.foundation.settings import FoundationSettings, postgres_url
    app = create_app(FoundationSettings())
    assert app.state.foundation_database is None
    app = create_app(FoundationSettings(enabled=True, application_database_url=postgres_url(
        'postgresql://synthetic:synthetic@fixture-db/wpl_fixture', 'fixture')),
        identity_settings=IdentitySettings(provider_url='https://provider.example.invalid',publishable_key='synthetic-public'))
    app.state.foundation_database.close()
    app.state.foundation_verifier.close()
assert not any(name in sys.modules for name in ('backend.app.main','backend.app.config','backend.app.db.database','docker'))
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", code], cwd=directory, timeout=20,
                env={"PATH": os.defpath, "PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner_url = os.environ["WPL_MIGRATION_DATABASE_URL"]
        cls.app_url = os.environ["WPL_APPLICATION_DATABASE_URL"]
        for value in (cls.owner_url, cls.app_url, os.environ["WPL_WORKER_DATABASE_URL"]):
            url = postgres_url(value, "fixture")
            if url.host != "fixture-db" or url.database != "wpl_fixture":
                raise RuntimeError("Refusing non-fixture test target.")
        migrate(cls.owner_url)
        cls.database = FoundationDatabase(FoundationSettings.from_mapping(os.environ))

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def test_actual_server_driver_and_role(self):
        self.assertEqual(psycopg.__version__, "3.3.6")
        self.assertEqual(pq.__impl__, "binary")
        with self.database.transaction() as session:
            row = session.execute(text("SELECT current_user,current_database(),current_setting('server_version')")).one()
            self.assertEqual(row[:2], ("wpl_app", "wpl_fixture"))
            self.assertTrue(row[2].startswith("17.11"))
            print("Actual fixture identity:", *row, "Psycopg", psycopg.__version__, flush=True)

    def test_fresh_repeat_concurrent_and_advisory_serialization(self):
        migrate(self.owner_url)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(migrate, [self.owner_url, self.owner_url]))
        with psycopg.connect(driver_url(self.owner_url)) as connection:
            self.assertEqual(connection.execute("SELECT version_num FROM wpl.alembic_version").fetchall(), [(foundation_head(),)])
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(migrate, self.owner_url)
                waiting = False
                deadline = time.monotonic() + 2
                try:
                    while time.monotonic() < deadline:
                        connection.execute("SELECT pg_stat_clear_snapshot()")
                        waiting = connection.execute("""SELECT EXISTS(SELECT 1 FROM pg_stat_activity
                            WHERE application_name='wpl-foundation-migration' AND wait_event='advisory')""").fetchone()[0]
                        if waiting:
                            break
                finally:
                    connection.commit()
                future.result(timeout=15)
                self.assertTrue(waiting, "No observed competing migration advisory-lock wait")
                print("Observed competing migration waiting on actual advisory lock.", flush=True)

    def test_roles_are_nonowners_and_ddl_escalation_is_denied(self):
        self.database.verify_runtime_role()
        with psycopg.connect(driver_url(self.owner_url)) as connection:
            rows = connection.execute("""SELECT rolname,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication
                FROM pg_roles WHERE rolname IN ('wpl_app','wpl_worker') ORDER BY rolname""").fetchall()
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual(row[1:], (False,) * 5)
            ownership = connection.execute("""SELECT pg_get_userbyid(nspowner)
                FROM pg_namespace WHERE nspname='wpl'""").fetchone()[0]
            self.assertEqual(ownership, "wpl_migrator")
            print("Schema owner:", ownership, "Runtime attributes:", rows, flush=True)
        for url in (self.app_url, os.environ["WPL_WORKER_DATABASE_URL"]):
            with psycopg.connect(driver_url(url)) as connection:
                for sql in ("CREATE TABLE wpl.forbidden(id integer)", "CREATE TABLE public.forbidden(id integer)",
                            "CREATE SCHEMA forbidden", "SET ROLE wpl_migrator", "ALTER ROLE wpl_app SUPERUSER",
                            "SELECT * FROM wpl.alembic_version"):
                    with self.subTest(role=connection.info.user, operation=sql):
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            connection.execute(sql)
                        connection.rollback()
        with self.assertRaises(FoundationMigrationError):
            migrate(self.app_url)

    def test_pool_commit_rollback_error_and_timeout_settings(self):
        with psycopg.connect(driver_url(self.owner_url)) as connection:
            connection.execute("CREATE TABLE wpl.transaction_fixture(id integer PRIMARY KEY)")
            connection.execute("GRANT SELECT,INSERT ON wpl.transaction_fixture TO wpl_app")
        try:
            with self.database.transaction() as session:
                session.execute(text("INSERT INTO wpl.transaction_fixture VALUES (1)"))
            with self.assertRaisesRegex(RuntimeError, "fixture rollback"):
                with self.database.transaction() as session:
                    session.execute(text("INSERT INTO wpl.transaction_fixture VALUES (2)"))
                    raise RuntimeError("fixture rollback")
            with self.assertRaises(DBAPIError):
                with self.database.transaction() as session:
                    session.execute(text("SELECT 1/0"))
            with self.database.transaction() as session:
                self.assertEqual(session.execute(text("SELECT id FROM wpl.transaction_fixture")).scalars().all(), [1])
                for name, value in (("statement_timeout", "5s"), ("lock_timeout", "2s"), ("idle_in_transaction_session_timeout", "10s")):
                    self.assertEqual(session.execute(text("SELECT current_setting(:key)"), {"key": name}).scalar_one(), value)
            self.assertEqual(self.database.engine.pool.size(), 2)
            self.assertEqual(self.database.engine.pool.checkedout(), 0)
        finally:
            with psycopg.connect(driver_url(self.owner_url)) as connection:
                connection.execute("DROP TABLE wpl.transaction_fixture")

    def test_schema_owner_is_rejected_as_application_role(self):
        database = FoundationDatabase(FoundationSettings(enabled=True, application_database_url=postgres_url(self.owner_url, "fixture")))
        try:
            with self.assertRaises(FoundationConfigurationError):
                database.verify_runtime_role()
        finally:
            database.close()

    def test_z_disposable_downgrade_and_reupgrade(self):
        migrate(self.owner_url, "base", downgrade=True)
        with psycopg.connect(driver_url(self.owner_url)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM wpl.alembic_version").fetchone()[0], 0)
        migrate(self.owner_url)


def foundation_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(Config('/app/backend/alembic_foundation.ini')).get_current_head()
