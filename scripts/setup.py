#!/usr/bin/env python3
"""Configure and start the existing single-host Linux Compose deployment."""

import argparse
from decimal import Decimal, InvalidOperation
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "backend" / ".env"
REQUIRED = (
    "WPL_PUBLIC_URL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY", "WPL_GITHUB_CLIENT_ID",
    "WPL_GITHUB_CLIENT_SECRET", "WPL_SECRET_KEY",
)


class SetupError(Exception):
    pass


def origin(value, name):
    value = value.strip().rstrip("/")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise SetupError(f"{name} has an invalid host or port.") from None
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username or parts.password or parts.path
            or parts.query or parts.fragment or any(c.isspace() for c in value)
            or (port is not None and not 1 <= port <= 65535)):
        raise SetupError(f"{name} must be an HTTP(S) origin without a path or credentials.")
    return value


def loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def integer(value, name, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise SetupError(f"{name} must be a positive integer.") from None
    if result <= 0 or (maximum is not None and result > maximum):
        raise SetupError(f"{name} is outside the supported range.")
    return result


def validate(values):
    for name in REQUIRED:
        value = values.get(name, "")
        if not value or value.startswith("YOUR_") or "\n" in value or "\r" in value:
            raise SetupError(f"Supply a real value for {name}.")
    public = origin(values["WPL_PUBLIC_URL"], "WPL_PUBLIC_URL")
    supabase = origin(values["SUPABASE_URL"], "SUPABASE_URL")
    if "YOUR_PROJECT" in supabase or urlsplit(supabase).scheme != "https":
        raise SetupError("SUPABASE_URL must be the project's HTTPS origin, without /rest/v1/.")
    if values["SUPABASE_PUBLISHABLE_KEY"].startswith("sb_secret_"):
        raise SetupError("A secret Supabase key must not be used as the publishable key.")
    if values["SUPABASE_SECRET_KEY"].startswith("sb_publishable_"):
        raise SetupError("SUPABASE_SECRET_KEY requires a backend secret key.")
    if len(values["WPL_SECRET_KEY"]) < 32:
        raise SetupError("WPL_SECRET_KEY must contain at least 32 characters; preserve an existing key.")
    # Compose serves /api and /gui at the same public origin.
    if values.get("WPL_API_BASE_URL", public + "/api").rstrip("/") != public + "/api":
        raise SetupError("For Compose, omit WPL_API_BASE_URL or set it to WPL_PUBLIC_URL/api.")
    if values.get("WPL_GUI_BASE_URL", public).rstrip("/") != public:
        raise SetupError("For Compose, omit WPL_GUI_BASE_URL or set it to WPL_PUBLIC_URL.")
    port = integer(values.get("WPL_HTTP_PORT", "8080"), "WPL_HTTP_PORT", 65535)
    if port == 8000:
        raise SetupError("WPL_HTTP_PORT cannot be 8000; that port is used by the backend.")
    if values.get("WPL_LISTEN_ADDRESS", "127.0.0.1") not in ("127.0.0.1", "0.0.0.0"):
        raise SetupError("This deployment supports WPL_LISTEN_ADDRESS=127.0.0.1 or 0.0.0.0.")
    parts = urlsplit(public)
    if parts.scheme == "http":
        if not loopback(parts.hostname) or parts.hostname == "::1":
            raise SetupError("This wizard supports local IPv4 HTTP or HTTPS behind a TLS proxy.")
        if (parts.port or 80) != port:
            raise SetupError("For local HTTP, the public URL port must match WPL_HTTP_PORT.")
    for name, default in (("WPL_LAB_PIDS_LIMIT", 256), ("WPL_IDLE_MINUTES", 30)):
        integer(values.get(name, default), name)
    if not re.fullmatch(r"[1-9][0-9]*(?:[bkmgBKMG])?", values.get("WPL_LAB_MEMORY", "1g")):
        raise SetupError("WPL_LAB_MEMORY must be positive bytes or a value such as 512m or 1g.")
    if not values.get("WPL_LAB_IMAGE", "wpl-student:dev").strip():
        raise SetupError("WPL_LAB_IMAGE must not be empty.")
    try:
        cpu = Decimal(values.get("WPL_LAB_CPUS", "0.25"))
    except InvalidOperation:
        raise SetupError("WPL_LAB_CPUS must be a positive number.") from None
    if not cpu.is_finite() or cpu <= 0 or cpu * 10**9 != (cpu * 10**9).to_integral_value():
        raise SetupError("WPL_LAB_CPUS must be positive with at most nine decimal places.")
    return public, port


def compose_args(env_file=ENV_FILE):
    return ["docker", "compose", "--project-directory", str(ROOT),
            "--env-file", str(env_file), "-f", str(ROOT / "compose.yaml")]


def capture(command, message):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        # Compose errors can contain configuration values. Do not echo captured output.
        raise SetupError(message)
    return result.stdout


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def prerequisites():
    if not sys.platform.startswith("linux"):
        raise SetupError("The current deployment requires Linux host networking.")
    if not shutil.which("docker"):
        raise SetupError("Install Docker Engine and Docker Compose first; see docs/setup.md.")
    capture(["docker", "compose", "version"], "Docker Compose is unavailable.")
    os_type = capture(["docker", "info", "--format", "{{.OSType}}"],
                      "Cannot access Docker. Check that it is running and your account has access.")
    if os_type.strip() != "linux":
        raise SetupError("A local Linux Docker Engine is required.")
    docker_socket = Path("/var/run/docker.sock")
    if not docker_socket.exists() or not stat.S_ISSOCK(docker_socket.stat().st_mode):
        raise SetupError("Expected a local Docker socket at /var/run/docker.sock.")
    print("Docker and Compose prerequisites passed.")


def read_configuration():
    if not ENV_FILE.is_file():
        raise SetupError("No backend/.env exists. Run ./wpl setup to configure a fresh installation.")
    output = capture(compose_args() + ["config", "--format", "json"],
                     "Compose configuration is invalid. Check backend/.env and compose.yaml.")
    config = json.loads(output)
    # Compose config is re-loadable: literal dollars are exported as $$.
    def decoded(mapping):
        return {key: value.replace("$$", "$") if isinstance(value, str) else value
                for key, value in mapping.items()}
    values = decoded(config["services"]["backend"]["environment"])
    public, port = validate(values | decoded(config["services"]["web"]["environment"]))
    args = decoded(config["services"]["web"]["build"]["args"])
    expected = {
        "VITE_API_URL": public + "/api",
        "VITE_SUPABASE_URL": values["SUPABASE_URL"],
        "VITE_SUPABASE_PUBLISHABLE_KEY": values["SUPABASE_PUBLISHABLE_KEY"],
    }
    if any(args.get(key) != value for key, value in expected.items()):
        raise SetupError("Frontend and backend settings disagree. Remove conflicting shell environment overrides.")
    return values, public, port


def managed_services():
    ids = capture(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=wpl"],
                  "Cannot inspect existing WPL containers.").split()
    running = set()
    for container_id in ids:
        output = capture(["docker", "inspect", "--format",
                          '{{json .Config.Labels}}|{{.State.Running}}', container_id],
                         "Cannot inspect an existing WPL container.")
        labels_text, state = output.strip().rsplit("|", 1)
        labels = json.loads(labels_text)
        directory = labels.get("com.docker.compose.project.working_dir", "")
        if not directory or Path(directory).resolve() != ROOT:
            raise SetupError("Another checkout owns the 'wpl' Compose project on this Docker Engine.")
        if state == "true":
            running.add(labels.get("com.docker.compose.service"))
    return running


def check_ports(port):
    running = managed_services()
    for service, number in (("backend", 8000), ("web", port)):
        if service in running:
            continue
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", number))
        except OSError:
            raise SetupError(f"Port {number} is occupied. Stop the conflicting service before starting WPL.") from None


def show_urls(public, port):
    print(f"\nWebsite / Supabase Site URL: {public}")
    print(f"Supabase redirect URLs: {public} and {public}/reset-password")
    print(f"GitHub App homepage: {public}")
    print(f"GitHub App redirect URI: {public}/api/github/callback")
    if urlsplit(public).scheme == "https":
        print(f"HTTPS prerequisite: a TLS proxy forwarding this origin to http://127.0.0.1:{port}.")
        print("The TLS proxy must support WebSocket upgrades and keep all paths unchanged.")
        print("This setup command does not provision DNS or certificates.")


def prompt(label, default=None, hidden=False):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        reader = getpass.getpass if hidden else input
        value = reader(label + suffix + ": ").strip() or default
        if value and "\n" not in value and "\r" not in value:
            return value
        print("A value is required.")


def dotenv_text(values):
    # Single quotes prevent Compose expansion of $, #, whitespace and backslashes.
    def quote(value):
        return "'" + value.replace("'", "\\'") + "'"
    return "# Generated by ./wpl setup. Keep this file private.\n" + "".join(
        f"{key}={quote(value)}\n" for key, value in values.items()
    )


def fresh_configuration():
    public = origin(prompt("Public website URL", "http://localhost:8080"), "Public URL")
    parts = urlsplit(public)
    if parts.scheme == "http" and (not loopback(parts.hostname) or parts.hostname == "::1"):
        raise SetupError("Use localhost HTTP for local testing, or HTTPS with an external TLS proxy.")
    port = str(parts.port or 80) if parts.scheme == "http" else prompt("Internal HTTP port", "8080")
    values = {
        "WPL_PUBLIC_URL": public,
        "WPL_HTTP_PORT": port,
        "WPL_LISTEN_ADDRESS": "127.0.0.1",
        "WPL_DATABASE_PATH": "data/wpl.db",
        "SUPABASE_URL": prompt("Supabase project URL (without /rest/v1/)"),
        "SUPABASE_PUBLISHABLE_KEY": prompt("Supabase publishable key", hidden=True),
        "SUPABASE_SECRET_KEY": prompt("Supabase backend secret key", hidden=True),
        "WPL_GITHUB_CLIENT_ID": prompt("GitHub App Client ID (not App ID)"),
        "WPL_GITHUB_CLIENT_SECRET": prompt("GitHub App client secret", hidden=True),
        "WPL_SECRET_KEY": secrets.token_urlsafe(48),
        "WPL_LAB_IMAGE": "wpl-student:dev",
        "WPL_LAB_MEMORY": "1g",
        "WPL_LAB_CPUS": "0.25",
        "WPL_LAB_PIDS_LIMIT": "256",
        "WPL_IDLE_MINUTES": "30",
    }
    public, port = validate(values)
    check_ports(port)
    show_urls(public, port)
    print("\nBefore starting:")
    print("- Run supabase/001_profiles_and_access.sql once in a FRESH Supabase project.")
    print("  For an existing compatible project, verify its profiles table instead of rerunning that SQL.")
    print("- Enable Supabase Email and confirmation; save the Site URL and redirects above.")
    print("- Register a GitHub App with expiring tokens and Administration/Contents read-write.")
    print("- Install that App on each student's GitHub account (All repositories for newly created repos).")
    print("- Built-in Supabase email only supports project team addresses; Resend is optional/deferred.")
    if input("Are these service settings (and TLS, if applicable) ready? [y/N]: ").strip().lower() not in ("y", "yes"):
        raise SetupError("Setup cancelled; no configuration was saved.")
    descriptor = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(dotenv_text(values))
    print("Saved backend/.env privately. Preserve it when moving this installation.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check prerequisites/configuration without writing, building or starting.")
    parser.add_argument("--urls", action="store_true", help="Print configured external-service URLs without changing anything.")
    options = parser.parse_args(argv)
    if options.check and options.urls:
        parser.error("Choose --check or --urls.")
    if options.urls:
        _, public, port = read_configuration()
        show_urls(public, port)
        return
    prerequisites()
    if not ENV_FILE.exists():
        if options.check:
            raise SetupError("No configuration exists yet. Run ./wpl setup.")
        if (ROOT / "wpl.db").exists() or (ROOT / "data" / "wpl.db").exists():
            raise SetupError("Database exists without backend/.env. Restore its configuration before proceeding.")
        fresh_configuration()
    else:
        print("Reusing backend/.env; no settings or signing secrets will be rewritten.")
    values, public, port = read_configuration()
    check_ports(port)
    data = ROOT / "data"
    if not (data / "wpl.db").exists() and (ROOT / "wpl.db").exists():
        raise SetupError("A legacy root wpl.db exists. Back it up and migrate it to data/wpl.db first; see docs/setup.md.")
    print("Configuration and port checks passed.")
    if options.check:
        print("Read-only check complete. No files or services changed.")
        return
    data.mkdir(mode=0o700, exist_ok=True)
    image = values.get("WPL_LAB_IMAGE", "wpl-student:dev")
    print("\nBuilding the student image...")
    run(["docker", "build", "-t", image, str(ROOT / "container")])
    print("\nBuilding and starting the backend/web services; migrations run at backend startup...")
    run(compose_args() + ["up", "-d", "--build", "--wait", "--wait-timeout", "120"])
    show_urls(public, port)
    print("\nServices started. Verify signup/approval, lab execution, GitHub and GUI in the browser.")
    print("Use ./wpl status and ./wpl logs --follow for service status and troubleshooting.")


if __name__ == "__main__":
    try:
        main()
    except (SetupError, OSError, json.JSONDecodeError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("Setup stopped: a build/start command failed. Review its output; use ./wpl logs for startup failures.", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.", file=sys.stderr)
        sys.exit(1)
