# Repeatable single-host WPL setup

This workflow is for the new independent WiByte Labs installation. The old VPS
instructions in `docs/deployment.md` are reference material, not commands to run
against the old production system.

## Prerequisites

- Linux with a local Docker Engine at `/var/run/docker.sock`, Docker Compose v2,
  Git, Bash and Python 3.10 or newer. Host Node, pip and a Python virtual
  environment are not needed for this Compose workflow.
- Docker access for the account running setup. Docker socket access grants
  host administration capabilities. The backend controls this same Docker Engine.
- Available ports: backend `127.0.0.1:8000` and web `127.0.0.1:8080` by default.
- Your chosen Supabase project and GitHub App credentials. Use independent
  accounts/resources for an independent installation.

On Ubuntu, the packages used for our reference installation were `docker.io`,
`docker-compose-v2`, `git` and `python3`. Enable Docker and give your deployment
account Docker access, then fully log out/in to activate new group membership.
On other distributions, install equivalent packages using their supported
installation process. Setup checks prerequisites; it does not install system
packages, alter groups, change firewalls or configure system services.

## Fresh installation

Clone the intended repository on the new machine, enter it, then run:

```bash
./wpl setup
```

The wizard asks for the browser-facing origin, Supabase project URL and keys,
GitHub App Client ID and client secret. Secret input is hidden. It generates the
WPL signing key once, writes `backend/.env` with mode 0600, prepares `data/`,
builds the student/backend/web images, and starts Compose. SQLite migrations run
automatically before FastAPI starts.

For local testing use `http://localhost:8080`. URLs are derived:

| Purpose | Path at the public origin |
| --- | --- |
| Website / Supabase Site URL | `/` |
| Supabase signup redirect | `/` |
| Supabase password recovery redirect | `/reset-password` |
| API | `/api` |
| Terminal WebSocket | `/api/labs/.../terminal` using `ws` or `wss` |
| GUI | `/gui/...` |
| GitHub App authorization redirect | `/api/github/callback` |

During fresh setup the wizard asks you to finish the external service settings
before starting. It does not create accounts, register/install GitHub Apps,
execute SQL against Supabase, provision DNS or issue certificates.

### Supabase

1. In a fresh project, run `supabase/001_profiles_and_access.sql` once in SQL Editor.
   Do not rerun this initial migration against an existing table.
2. Enable Email authentication and email confirmation.
3. Set Site URL to your public origin; allow the root and `/reset-password` redirects.
4. Supply the project origin without `/rest/v1/`, the publishable key and backend
   secret key. Backend secret keys must never be placed in frontend configuration.
5. Sign up in WPL, confirm email, then manually change that user's profile
   `approval_status` to `approved` using the Supabase dashboard.

Built-in Supabase email sends only to project team addresses. Custom SMTP/Resend
is deferred until a sending domain is available. The saved profile schema records
email at signup. Account roles and email-change synchronization are deferred.

### GitHub

Register a GitHub App using the printed homepage and redirect URI. Keep expiring
user authorization tokens enabled. Disable webhooks. Repository permissions:
Administration and Contents read/write, Metadata read-only. Use Client ID rather
than App ID; create a client secret.

Each student must both install the App on their GitHub account and authorize it
inside WPL. All repositories allows access to new `wibyte-workspace` repositories.
Choose Any account when other accounts must be able to install the App.

## HTTPS/server deployment

For `https://your-domain.example`, provide that origin to setup. The web container
still serves internal HTTP on loopback (8080 by default). A separately configured
TLS proxy must forward the public HTTPS origin to `http://127.0.0.1:8080`, preserve
all paths, and support WebSocket upgrades for terminal and GUI. Configure DNS,
certificates and certificate renewal at that proxy before using the deployment.

The wizard does not yet automate TLS. An HTTPS URL alone does not enable HTTPS.
It will explicitly ask whether the TLS proxy is ready. Local GUI ports stay
loopback-only; the signed-cookie Nginx authorization check remains in place.

The backend and web container use Linux host networking so the proxy can reach
the dynamically allocated loopback GUI ports. Student containers remain separate.
This first deployment supports one WPL Compose project per Docker Engine and
requires the host Docker socket path above. Docker Desktop/remote engines and
distributed workers are outside this setup.

## Existing installation

```bash
./wpl setup --check
./wpl urls
```

These commands do not write configuration, build images or restart anything.
`--check` validates Docker access, saved Compose settings and occupied ports; it
does not verify external credentials or substitute for browser workflow tests.

Running `./wpl setup` again preserves the existing `.env` and signing key, rebuilds
all images and starts/reconciles services. It can replace application containers
when their image or configuration changes. Existing student containers retain
their old image until new labs are created.

Do not run a host backend against the obsolete root `wpl.db`. Compose's current
database is `data/wpl.db`; Compose mounts `data/` at `/data` and overrides the
backend database setting to `/data/wpl.db`. If migrating a legacy root database,
stop its backend first and use SQLite's backup API to copy it into `data/wpl.db`.
Never overwrite an existing `data/wpl.db` without reviewing it and backing it up.
Setup refuses to silently start an empty database when a legacy root database is
present. It also refuses an existing database without its configuration.

For relocation of an existing installation, preserve `backend/.env` (especially
the signing key), make a consistent SQLite backup, and restore it as `data/wpl.db`.
Student containers and live terminal sessions are not portable backups. Push
student work to GitHub before moving machines. Automated backup/restore commands
are still pending.

## Daily commands

```bash
./wpl start                # Build changed app images and start services
./wpl stop                 # Stop backend/web; preserve data and student containers
./wpl restart              # Rebuild and recreate backend/web
./wpl status               # Show service state
./wpl logs --follow        # Stream logs; Ctrl+C stops viewing only
./wpl urls                # Print external redirect settings
```

Use `./wpl setup` after changing the student Dockerfile to rebuild the configured
student image too. Only newly created labs use that image.

`backend/.env` is the source for Compose credentials, public build settings and
deployment URLs. `frontend/.env` is used only by standalone Vite development.
Process environment overrides must agree with the saved settings; setup checks
for mismatched frontend/backend configuration. Never print full Compose config
in reports: it contains secrets. The `.env.example` files contain placeholders.

Application code changes require rebuilding images, normally with `./wpl restart`.
Database model changes require an Alembic migration; editing a model alone does
not alter the database. Alembic and the backend share the configured database URL.

## Validation and remaining work

Our manual reference installation has passed signup/approval/login, password
reset, lab creation/deletion/reopening, Python input and Stop, file operations,
GitHub commit/push and restoration/pull on reopening, Tkinter GUI, access isolation
and inactivity cleanup. Those are user-reported workflow checks, not automated
test coverage. Repeat the workflows after installing on a fresh machine.

Both container health checks are basic readiness checks. An installation is not
fully verified until the actual student workflow passes. Also verify a GUI URL
without a signed cookie returns HTTP 403.

Pending portability work: automatic HTTPS provisioning, backup/restore commands,
a clean-machine end-to-end setup test, configurable upload limits, pinning base
image digests and student dependencies, and review of remaining deployment-specific
documentation. Runtime resource limits and idle timeout already have defaults and
environment settings. No organisation/admin dashboard or distributed worker
architecture is introduced by this deployment toolkit.
