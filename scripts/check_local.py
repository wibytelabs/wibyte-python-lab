#!/usr/bin/env python3
"""Credential-free local checks; --prepare downloads/builds isolated test runtimes."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NODE_IMAGE = "node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c"
FILES = (
    "alembic.ini", "backend/alembic_foundation.ini", "backend/requirements.txt", "scripts/Dockerfile.checks",
    "scripts/setup.py", "scripts/test_setup.py", "scripts/test_deployment.py",
    "scripts/test_idle_defaults.py", "scripts/check_local.py",
    "scripts/test_check_local.py", "scripts/check_foundation.py",
    "scripts/test_check_foundation.py", "scripts/migrate_foundation.py", "scripts/run_frontend_tests.mjs", "frontend/package.json",
    "frontend/package-lock.json", "frontend/index.html",
    "frontend/eslint.config.js", "frontend/vite.config.ts",
    "frontend/tsconfig.json", "frontend/tsconfig.app.json",
    "frontend/tsconfig.node.json",
)
FRONTEND_TESTS = (
    "frontend/tests/apiUrls.test.mjs",
    "frontend/tests/apiClient.test.mjs",
    "frontend/tests/accountLookup.test.mjs",
    "frontend/tests/frontendPolicy.test.mjs",
)
TREES = {
    "backend/app": {".py"},
    "backend/alembic": {".py", ".mako"},
    "backend/alembic_foundation": {".py", ".mako", ".sql"},
    "backend/tests/foundation": {".py"},
    "frontend/src": {".ts", ".tsx", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp"},
    "frontend/public": {".svg", ".png", ".ico", ".jpg", ".webp", ".txt"},
    "frontend/tests": {".mjs"},
}


class CheckError(Exception):
    pass


def run_checked(label, command, *, timeout, env, cwd=None, capture=False, check=True):
    print("CHECK:", label, flush=True)
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, timeout=timeout,
            text=True, capture_output=capture,
        )
    except FileNotFoundError:
        raise CheckError(f"{label}: required executable is missing.") from None
    except subprocess.TimeoutExpired:
        raise CheckError(f"{label}: timed out after {timeout} seconds.") from None
    if check and result.returncode:
        raise CheckError(f"{label}: failed with exit code {result.returncode}.")
    return result


def copy_sources(source, destination):
    def copy_file(relative):
        original = source / relative
        if any(p.is_symlink() for p in (original, *original.parents) if p != source.parent):
            raise CheckError("Source snapshot refuses symlinks.")
        if not original.is_file():
            raise CheckError(f"Required source file missing: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        target.chmod(0o644)

    for relative in FILES:
        copy_file(Path(relative))
    for relative, suffixes in TREES.items():
        directory = source / relative
        if directory.is_symlink():
            raise CheckError("Source snapshot refuses symlink directories.")
        for original in sorted(directory.rglob("*")):
            if original.is_symlink():
                raise CheckError("Source snapshot refuses symlinks.")
            if (original.is_file() and original.suffix in suffixes
                    and not any(p.startswith(".") for p in original.relative_to(directory).parts)):
                copy_file(original.relative_to(source))
    destination.chmod(0o755)
    for path in destination.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)


def host_environment(home):
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home), "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "DOCKER_CONFIG": str(home / "docker"),
    }


def prerequisites(root, env):
    if not sys.platform.startswith("linux") or sys.version_info < (3, 10):
        raise CheckError("Use Linux and Python 3.10 or newer.")
    if not shutil.which("docker", path=env["PATH"]):
        raise CheckError("Docker CLI is missing; install local Docker Engine and Compose v2.")
    for relative in FILES:
        if not (root / relative).is_file():
            raise CheckError(f"Required source/lockfile missing: {relative}")
    for relative in FRONTEND_TESTS:
        if not (root / relative).is_file():
            raise CheckError(f"Required contract tests missing: {relative}")
    run_checked("Compose prerequisite", ["docker", "compose", "version"],
                timeout=20, env=env, capture=True)
    result = run_checked("Local Docker prerequisite",
                         ["docker", "info", "--format", "{{.OSType}}"],
                         timeout=20, env=env, capture=True)
    if result.stdout.strip() != "linux":
        raise CheckError("A local Linux Docker Engine is required.")


def image_exists(image, env):
    return run_checked("Runtime image prerequisite",
                       ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                       timeout=20, env=env, capture=True, check=False).returncode == 0


def backend_image(root):
    digest = hashlib.sha256(
        (root / "backend/requirements.txt").read_bytes() +
        (root / "scripts/Dockerfile.checks").read_bytes()
    ).hexdigest()[:16]
    return "wpl-p01-checks:" + digest


def prepare_images(root, home, env, prepare):
    backend = backend_image(root)
    missing_node = not image_exists(NODE_IMAGE, env)
    missing_backend = not image_exists(backend, env)
    if (missing_node or missing_backend) and not prepare:
        raise CheckError("Test runtime image missing. Run this command again with --prepare.")
    if missing_node:
        run_checked("Pull pinned Node runtime", ["docker", "pull", NODE_IMAGE],
                    timeout=300, env=env)
    if missing_backend:
        context = home / "image-context"
        (context / "backend").mkdir(parents=True)
        shutil.copyfile(root / "backend/requirements.txt", context / "backend/requirements.txt")
        shutil.copyfile(root / "scripts/Dockerfile.checks", context / "Dockerfile")
        run_checked("Build isolated pinned backend dependencies",
                    ["docker", "build", "-t", backend, str(context)],
                    timeout=900, env=env)
    for label, image in (("Node runtime identity", NODE_IMAGE), ("Backend runtime identity", backend)):
        result = run_checked(label, ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                             timeout=20, env=env, capture=True)
        print(label + ": " + result.stdout.strip(), flush=True)
    return backend


def run_container(label, image, snapshot, command, settings, env, *, network=False, writable=False, timeout=180):
    owner = uuid4().hex
    name = "wpl-check-" + owner
    arguments = [
        "docker", "run", "--rm", "--pull=never", "--name", name,
        "--label", "wpl.check.run=" + owner,
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit", "256", "--memory", "2g", "--cpus", "2",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--mount", f"type=bind,src={snapshot},dst=/app" + ("" if writable else ",readonly"),
        "--workdir", "/app", "--entrypoint", "/usr/bin/env",
    ]
    if not network:
        arguments += ["--network", "none"]
    arguments += [image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                  "LANG=C.UTF-8", "TMPDIR=/tmp"]
    arguments += [f"{key}={value}" for key, value in settings.items()]
    arguments += command
    try:
        return run_checked(label, arguments, timeout=timeout, env=env)
    finally:
        inspected = run_checked(
            "Owned test container cleanup check",
            ["docker", "container", "inspect", "--format",
             '{{.Id}}|{{index .Config.Labels "wpl.check.run"}}', name],
            timeout=20, env=env, capture=True, check=False,
        )
        if inspected.returncode == 0:
            identity, _, observed_owner = inspected.stdout.strip().partition("|")
            if observed_owner != owner or not identity:
                raise CheckError("Refusing cleanup: test container ownership differs.")
            run_checked("Remove owned test container", ["docker", "rm", "-f", identity],
                        timeout=30, env=env)


def unit_code(root, patterns):
    return (
        "import sys,unittest; "
        f"sys.path.insert(0,{str(root)!r}); "
        "loader=unittest.TestLoader(); suite=unittest.TestSuite(); " +
        "; ".join(
            f"cases=loader.discover({str(root / 'scripts')!r},pattern={p!r}); "
            "cases.countTestCases() or sys.exit('No tests discovered'); suite.addTests(cases)"
            for p in patterns
        ) +
        "; result=unittest.TextTestRunner(verbosity=2).run(suite); "
        "sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)"
    )


def run_frontend_contracts(snapshot, env):
    return run_container(
        "Frontend mandatory contracts and result policy", NODE_IMAGE, snapshot,
        ["node", "--experimental-strip-types", "/app/scripts/run_frontend_tests.mjs",
         *("/app/" + relative for relative in FRONTEND_TESTS)],
        {}, env,
    )


def execute(prepare):
    with tempfile.TemporaryDirectory(prefix="wpl-check-") as directory:
        owned = Path(directory)
        owned.chmod(0o755)
        home = owned / "home"
        home.mkdir()
        env = host_environment(home)
        prerequisites(ROOT, env)
        backend = prepare_images(ROOT, home, env, prepare)
        snapshot = owned / "source"
        snapshot.mkdir()
        copy_sources(ROOT, snapshot)

        run_checked("Runner failure/isolation contracts",
                    [sys.executable, "-c", unit_code(snapshot, ["test_check_local.py", "test_check_foundation.py"])],
                    timeout=90, env=env, cwd=snapshot)
        run_checked("Setup regressions (no skipped cases accepted)",
                    [sys.executable, "-c", unit_code(snapshot, ["test_setup.py"])],
                    timeout=90, env=env, cwd=snapshot)
        run_container(
            "Backend regressions and idle configuration", backend, snapshot,
            ["python", "-c", unit_code(Path("/app"), ["test_deployment.py", "test_idle_defaults.py"])],
            {
                "PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
                "WPL_PUBLIC_URL": "http://localhost:8080",
                "WPL_DATABASE_PATH": "/tmp/fixture.db",
                "WPL_SECRET_KEY": "synthetic-" * 8,
                "SUPABASE_URL": "https://supabase.example.invalid",
                "SUPABASE_PUBLISHABLE_KEY": "synthetic-public",
                "SUPABASE_SECRET_KEY": "synthetic-secret",
                "WPL_GITHUB_CLIENT_ID": "synthetic-client",
                "WPL_GITHUB_CLIENT_SECRET": "synthetic-secret",
            }, env,
        )
        run_frontend_contracts(snapshot, env)
        run_checked("Mandatory disposable Postgres foundation",
                    [sys.executable, str(snapshot / "scripts/check_foundation.py"),
                     *(["--prepare"] if prepare else [])],
                    timeout=600, env=env, cwd=snapshot)
        frontend_settings = {
            "npm_config_userconfig": "/tmp/npm-user.conf",
            "npm_config_globalconfig": "/tmp/npm-global.conf",
            "npm_config_cache": "/tmp/npm-cache",
            "CI": "true", "VITE_API_URL": "/api",
            "VITE_SUPABASE_URL": "https://supabase.example.invalid",
            "VITE_SUPABASE_PUBLISHABLE_KEY": "synthetic-public",
        }
        run_container(
            "Frontend locked dependency installation", NODE_IMAGE, snapshot,
            ["npm", "--prefix", "/app/frontend", "ci", "--no-audit", "--no-fund"],
            frontend_settings, env, network=True, writable=True, timeout=300,
        )
        for task in ("build", "lint"):
            run_container(
                "Frontend " + task, NODE_IMAGE, snapshot,
                ["npm", "--prefix", "/app/frontend", "run", task],
                frontend_settings, env, writable=True,
            )
        print("PASS: all mandatory local checks completed; no skipped suites.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true",
                        help="Pull pinned Node/build isolated backend image if missing, then run checks.")
    options = parser.parse_args(argv)
    try:
        execute(options.prepare)
    except (CheckError, OSError) as error:
        print("FAIL:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
