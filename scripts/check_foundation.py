#!/usr/bin/env python3
"""Disposable local Postgres tests. Preparation and fixture execution are separate."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import check_local as shared

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"
OWNER_LABEL = "wpl.foundation.run"

def checked(label, command, env, *, timeout=30, capture=False, check=True, input=None):
    print("CHECK:", label, flush=True)
    try:
        result = subprocess.run(command, env=env, input=input, timeout=timeout,
                                capture_output=capture, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise shared.CheckError(f"{label}: executable unavailable or timeout; details redacted.") from None
    if check and result.returncode:
        raise shared.CheckError(f"{label}: failed with exit code {result.returncode}.")
    return result

FOUNDATION_TESTS = (
    'test_context.py', 'test_database.py', 'test_enqueue.py', 'test_executive_metadata.py', 'test_guards.py', 'test_http.py', 'test_http_platform.py', 'test_idempotency.py', 'test_identity.py',
    'test_mutation_rls.py', 'test_payloads.py', 'test_read_rls.py', 'test_schema.py', 'test_services.py', 'test_worker_execution.py', 'test_worker_leases.py', 'test_worker_transitions.py',
)


def foundation_unit_code(root):
    directory=root/'backend/tests/foundation'
    return (
        "import pathlib,sys,unittest; "
        f"sys.path.insert(0,{str(root)!r}); directory=pathlib.Path({str(directory)!r}); "
        f"expected={FOUNDATION_TESTS!r}; "
        "actual={p.name for p in directory.glob('test_*.py')}; "
        "actual==set(expected) or sys.exit('Missing or undeclared foundation test module'); "
        "loader=unittest.TestLoader(); suite=unittest.TestSuite(); " +
        "; ".join(
            f"cases=loader.discover(str(directory),pattern={name!r}); "
            "cases.countTestCases() or sys.exit('Empty mandatory foundation module'); suite.addTests(cases)"
            for name in FOUNDATION_TESTS
        ) +
        "; result=unittest.TextTestRunner(verbosity=2).run(suite); "
        "sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)"
    )


class Fixture:
    def __init__(self, env):
        self.env = env
        self.owner = uuid4().hex
        self.network = "wpl-p02-net-" + self.owner
        self.database = "wpl-p02-db-" + self.owner
        self.resources = []
        self.passwords = {role: secrets.token_hex(24) for role in ("admin", "migrator", "app", "worker")}

    def register(self, kind, name):
        self.resources.append((kind, name))

    @staticmethod
    def assertion(value, message):
        if not value:
            raise shared.CheckError(message)

    def sql(self, label, sql):
        return checked(label, ["docker", "exec", "-i", self.database, "psql", "-h", "/var/run/postgresql", "-X", "-q",
            "-v", "ON_ERROR_STOP=1", "-U", "wpl_fixture_admin", "-d", "wpl_fixture"],
            self.env, input=sql, capture=True)

    def ready(self, host):
        for attempt in range(60):
            result = checked("Fixture readiness", ["docker", "exec", self.database, "pg_isready", "-h", host,
                "-U", "wpl_fixture_admin", "-d", "wpl_fixture"], self.env, timeout=5, capture=True, check=False)
            if result.returncode == 0:
                return
            time.sleep(0.2)
        logs = checked("Fixture startup diagnostics", ["docker", "logs", "--tail", "30", self.database],
                       self.env, capture=True, check=False)
        print(logs.stdout + logs.stderr, flush=True)
        raise shared.CheckError("Disposable database did not become ready.")

    def start(self):
        self.register("network", self.network)
        result = checked("Create owned internal network", ["docker", "network", "create", "--internal",
            "--label", OWNER_LABEL + "=" + self.owner, self.network], self.env, capture=True)
        print("Fixture network ID:", result.stdout.strip(), flush=True)
        self.register("container", self.database)
        result = checked("Start disposable PostgreSQL 17.11", ["docker", "run", "-d", "--pull=never",
            "--name", self.database, "--label", OWNER_LABEL + "=" + self.owner,
            "--network", self.network, "--network-alias", "fixture-db", "--user", "postgres", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit", "128",
            "--memory", "768m", "--cpus", "1",
            "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,nodev,size=512m,mode=1777",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
            "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,size=8m,mode=1777",
            "-e", "PGDATA=/var/lib/postgresql/data/pgdata", "-e", "POSTGRES_DB=wpl_fixture",
            "-e", "POSTGRES_USER=wpl_fixture_admin", "-e", "POSTGRES_PASSWORD=" + self.passwords["admin"],
            "-e", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust",
            POSTGRES_IMAGE, "postgres", "-c", "unix_socket_directories=/var/run/postgresql",
            "-c", "shared_buffers=16MB", "-c", "max_connections=20"], self.env, capture=True)
        print("Fixture database container ID:", result.stdout.strip(), flush=True)
        self.ready("/var/run/postgresql")
        self.ready("127.0.0.1")  # Excludes entrypoint's temporary socket-only initialization server.
        self.sql("Bootstrap isolated identities and private schema", "\n".join([
            "REVOKE ALL ON DATABASE wpl_fixture FROM PUBLIC;",
            "REVOKE CREATE ON SCHEMA public FROM PUBLIC;",
            *(f"CREATE ROLE wpl_{role} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{self.passwords[role]}';"
              for role in ("migrator", "app", "worker")),
            "GRANT CONNECT ON DATABASE wpl_fixture TO wpl_migrator, wpl_app, wpl_worker;",
            "CREATE SCHEMA wpl AUTHORIZATION wpl_migrator; REVOKE ALL ON SCHEMA wpl FROM PUBLIC;",
            "GRANT USAGE ON SCHEMA wpl TO wpl_app, wpl_worker;"]))
        result = checked("Verify internal network", ["docker", "network", "inspect", self.network], self.env, capture=True)
        self.assertion(json.loads(result.stdout)[0]["Internal"], "Fixture network must be internal")
        result = checked("Verify unpublished ephemeral database", ["docker", "container", "inspect", self.database],
                         self.env, capture=True)
        info = json.loads(result.stdout)[0]
        self.assertion(not info["HostConfig"]["PortBindings"], "No published DB ports allowed")
        self.assertion(all(m["Type"] == "tmpfs" for m in info["Mounts"]), "Only tmpfs DB storage allowed")
        print("Isolation verified: internal network; no published ports; tmpfs data; no host socket/data mount.", flush=True)

    def test(self, image, snapshot, code, label):
        name = "wpl-p02-test-" + uuid4().hex
        self.register("container", name)
        settings = {"PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
                    "WPL_FOUNDATION_ENABLED": "true"}
        for kind, role in (("APPLICATION", "app"), ("MIGRATION", "migrator"), ("WORKER", "worker")):
            settings[f"WPL_{kind}_DATABASE_URL"] = (
                f"postgresql+psycopg://wpl_{role}:{self.passwords[role]}@fixture-db/wpl_fixture?sslmode=disable")
        return checked(label, ["docker", "run", "--rm", "--pull=never", "--name", name,
            "--label", OWNER_LABEL + "=" + self.owner, "--network", self.network,
            "--user", f"{os.getuid()}:{os.getgid()}", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit", "128", "--memory", "768m", "--cpus", "2",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m,mode=1777",
            "--mount", f"type=bind,src={snapshot},dst=/app,readonly", "--workdir", "/app",
            "--entrypoint", "/usr/bin/env", image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp", "LANG=C.UTF-8",
            *(f"{key}={value}" for key, value in settings.items()), "python", "-c", code], self.env, timeout=180)

    def cleanup(self):
        failures = []
        for kind, name in reversed(self.resources):
            try:
                labels = '.Config.Labels' if kind == "container" else '.Labels'
                info = checked("Inspect owned fixture for cleanup", ["docker", kind, "inspect", "--format",
                    '{{.Id}}|{{index ' + labels + ' "' + OWNER_LABEL + '"}}', name], self.env, capture=True, check=False)
                if info.returncode:
                    if "No such" in info.stderr:
                        continue
                    raise shared.CheckError("Cleanup inspection failed; cannot establish ownership.")
                identity, _, owner = info.stdout.strip().partition("|")
                self.assertion(identity and owner == self.owner, "Cleanup ownership mismatch; refusing removal")
                command = ["docker", "rm", "-f", identity] if kind == "container" else ["docker", "network", "rm", identity]
                checked("Remove owned fixture " + identity, command, self.env, capture=True)
            except shared.CheckError as error:
                failures.append(str(error))
        if failures:
            raise shared.CheckError("; ".join(failures))
        print("Fixture cleanup complete: owned resources removed; tmpfs data discarded.", flush=True)

def execute(prepare):
    with tempfile.TemporaryDirectory(prefix="wpl-p02-check-") as directory:
        owned = Path(directory)
        owned.chmod(0o755)
        home = owned / "home"
        home.mkdir()
        env = shared.host_environment(home)
        shared.prerequisites(ROOT, env)
        image = shared.prepare_images(ROOT, home, env, prepare)
        if not shared.image_exists(POSTGRES_IMAGE, env):
            if not prepare:
                raise shared.CheckError("Pinned fixture Postgres missing; use --prepare.")
            checked("Pull pinned fixture Postgres", ["docker", "pull", POSTGRES_IMAGE], env, timeout=300)
        snapshot = owned / "source"
        snapshot.mkdir()
        shared.copy_sources(ROOT, snapshot)
        fixture = Fixture(env)
        try:
            fixture.start()
            code = foundation_unit_code(Path('/app'))
            fixture.test(image, snapshot, code, "Foundation Postgres/configuration/schema tests")
            fixture.sql("Recreate only the owned fixture schema", "DROP SCHEMA wpl CASCADE; CREATE SCHEMA wpl AUTHORIZATION wpl_migrator; REVOKE ALL ON SCHEMA wpl FROM PUBLIC; GRANT USAGE ON SCHEMA wpl TO wpl_app,wpl_worker;")
            fixture.test(image, snapshot, "import os; from backend.app.foundation.migrate import migrate; "
                "from backend.app.foundation.db import FoundationDatabase; from backend.app.foundation.settings import FoundationSettings; "
                "migrate(os.environ['WPL_MIGRATION_DATABASE_URL']); db=FoundationDatabase(FoundationSettings.from_mapping(os.environ)); "
                "db.verify_runtime_role(); db.close(); print('Recreated target: migration and runtime role passed.')", "Recreated-target migration smoke")
        finally:
            fixture.cleanup()
        print("PASS: implemented foundation checks completed; no skipped cases.", flush=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    options = parser.parse_args(argv)
    try:
        execute(options.prepare)
    except (shared.CheckError, OSError) as error:
        print("FAIL:", error, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
