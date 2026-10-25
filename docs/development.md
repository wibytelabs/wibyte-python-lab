# Local development checks

P01 establishes repeatable local checks for the existing React/FastAPI lab.
Run these checks before proposing the next phase. Passing them proves the
listed local contracts; it does not establish GitHub, Supabase, GKE, email,
authenticated browser, or production readiness.

## Prerequisites and exact commands

Use Linux with a local Docker Engine at /var/run/docker.sock, Docker Compose
v2, and host Python 3.10 or newer. Python 3.14.4 was used for local acceptance
and is selected in CI. Docker bind mounts must support the current user's
UID/GID; remote daemons and remapped/rootless configurations are unverified.
No host Node, npm, Python application packages, private env, or provider
credentials are required.

From the repository root, run:

    PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_local.py --prepare

The first run downloads missing pinned Node runtime layers and builds a
dedicated backend dependency image from the existing pinned requirements.
It may access the public image registry, PyPI, and npm. It does not contact
application providers or start Compose services. No application image tags
are overwritten. Later runs use:

    PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_local.py

The absolute script path works from any directory. The command always
reinstalls frontend dependencies with npm ci in a disposable copy; it never
changes package.json or package-lock.json. Missing prerequisites/images,
failed/timed-out children, empty Python suites and skipped Python cases
produce nonzero results. Success ends with the explicit PASS summary.

## Runtimes and isolation

The backend test image uses the Python 3.14 base digest already declared
in backend/Dockerfile and backend/requirements.txt. Its tag is
wpl-p01-checks:<hash-of-requirements-and-test-Dockerfile>. It contains only
runtime/dependencies, not application source or private configuration.
The Node 22 image digest matches frontend/Dockerfile. Host distro Node
22.22.1 lacked TypeScript support, so the supported test path uses the
official pinned image rather than host TypeScript stripping.

The runner copies an allowlist of code, migrations, frontend assets,
manifests and tests to a new temporary directory. It includes new source
files without requiring staging. It excludes private dotenv files,
databases, .git, backups, credentials and scratch; symlinks are refused.
The snapshot is traversable by the unprivileged container user. Original
source is never mounted or made writable.

Backend tests have no network and no Docker socket. Their root and source
mount are read-only, with a bounded 256 MiB /tmp tmpfs. Synthetic settings
select /tmp/fixture.db; config precedence tests make additional disposable
source/dotenv copies there. Docker domain operations are mocked.

Frontend URL/request tests also run offline without importing Supabase.
Only npm dependency installation has network access. Production build and
lint run in subsequent offline containers, using the same disposable copy
and synthetic Vite values. Their source-copy mount is writable for build
artifacts. Containers have CPU, memory and PID bounds, dropped capabilities,
and no-new-privileges. No host socket, provider credential or real env file
is mounted in any test container.

Setup tests run on the host against disposable fixtures with a clean
environment and private temporary HOME/Docker configuration. The real
Docker CLI is used only for synthetic Compose config parsing.

## URL and authenticated request contract

apiUrls.ts resolves missing or empty VITE_API_URL to same-origin /api.
Relative /api and /api/, absolute local origins with optional /api, and
absolute HTTPS API prefixes are supported. Endpoint joining preserves the
prefix. Terminal derives ws from HTTP and wss from HTTPS using URL parsing.
An explicitly configured HTTP backend remains HTTP; HTTPS pages still
require a compatible backend transport to avoid browser mixed-content blocks.

Bases with credentials, unsupported schemes, queries or fragments are
rejected. Endpoint origins/traversal are rejected. Authenticated requests
must stay within the resolved origin and path prefix before session lookup.

apiClient.ts contains the dependency-injected fetch implementation.
api.ts binds it to Supabase getSession and browser fetch once. App keeps
its include-credentials default; Settings keeps its browser default.
Caller options, headers, Request input, body, signal and raw Response remain
available. Uploads receive no forced JSON content type. Terminal retains
the first authenticate frame and existing xterm/Run/Stop lifecycle.
Settings temporarily retains its apiUrl prop, supplied by the shared API_URL.

## Idle configuration

Omitted WPL_IDLE_MINUTES defaults to 35. Fresh setup and the example use 35.
Explicit positive values, including 30 and 45, remain authoritative.
Process environment overrides a dotenv value. Zero, negative and noninteger
values fail validation. P01 does not rewrite an installation's backend/.env;
running services retain their loaded values until a deliberate later restart.

## Evidence and optional integration checks

The runner executes setup, backend/config/route/migration/idle regressions,
pure frontend URL/auth/upload tests, runner failure/isolation tests, build,
and lint. Original setup/backend regressions are retained. Current counts
and exact output belong in planning/reports/P01-completion.md.

Two existing App Git-status exhaustive-deps warnings remain; lint exits zero.
The initial seven lint errors were fixed by separating the reset-password
route from the component with authentication hooks and removing an unused
callback parameter. Existing TestClient and legacy Docker-builder warnings
are not provider validation or failed tests.

The existing scripts/test_compose_local.py smoke remains separate and
requires WPL_RUN_DOCKER_TESTS=1. It uses existing development images,
host networking and a Docker socket, so it does not certify this unbuilt
candidate. Its disposable resources have unique labels and cleanup checks.
Do not enable it or rebuild/restart live services merely to run unit tests.

Authenticated browser smoke needs an authorized disposable session and
synthetic repository. It covers login/settings, files, Python stdin/Stop,
GUI, Git status and Commit & Push. Provider consent, repo deletion, cloud
spend and active-student expiry tests are outside P01. Record unrun smoke
explicitly for architect disposition; do not present mock checks as a pass.

## CI, troubleshooting and cleanup

.github/workflows/checks.yml targets the confirmed development repository
and runs this same command on pushes/PRs/manual dispatch. Contents permission
is read-only; checkout does not persist credentials. There are no provider
secrets, cloud identities, deployments, package publishing or privileged PR
triggers. Python is selected explicitly; actions use the documented v7
majors: https://github.com/actions/checkout and
https://github.com/actions/setup-python. A remote Actions run is separate
evidence and is not implied by local YAML validation.

For missing Docker/Compose or socket access, resolve the prerequisite and
retry. A missing image requires --prepare. Registry/npm/PyPI failures are
blocked dependency evidence; do not upgrade locks to conceal them.
Permission errors should be diagnosed on the disposable mount and UID/GID;
never chmod private configuration or student data to repair a test.

Owned temporary source/dependency/build directories are removed on exit.
Each test container is uniquely labeled; cleanup verifies its label and
deletes its inspected container ID. The dedicated dependency image remains
as a local cache. If removing it later, inspect its exact ID and
wpl.check.image=p01 label; never use broad Docker prune commands.
A forced kill or daemon failure can leave owned scratch requiring inspection.

Existing ignore rules already cover Python bytecode/venvs and frontend
node_modules/dist. New runner artifacts stay outside the repository, so
no broader ignore patterns are needed. Tests, handoff and report remain
versionable. Historical VPS/auth docs are retained with pointers here.

## P01 review corrections

Signup and confirmation resend use the production createAccountLookup helper
with the shared URL resolver, including missing/empty same-origin /api fallback.
It sends the existing public POST JSON email request with no session lookup,
bearer injection or credentials override. Its actual implementation is tested
with injected fetch and synthetic responses, without initializing Supabase.

Mandatory frontend modules are declared once in FRONTEND_TESTS, checked as
prerequisites, copied into the allowlisted snapshot and passed to
scripts/run_frontend_tests.mjs. The harness executes as a file in the pinned
Node image, forwards the built-in spec reporter diagnostics, and evaluates
runtime test:summary events after diagnostics flush. Every requested module
must produce a completed per-file summary with positive registered test count;
all registered tests must pass, with zero failures, skips, TODOs or cancellations.
One cumulative summary must agree with those module counts. No fixed case
total is embedded in the guard. A synthetic file-import pass from an empty
module is insufficient because it has no registered-test per-file summary.

Offline policy tests exercise passing, skipped, TODO, assertion/loader failure,
cancelled, empty, early-exit and timed-out fixtures in disposable directories.
Host tests verify rejection stops the global runner and preserves ownership
cleanup after failure/timeout. These synthetic failures are expected test
inputs, not failed real mandatory contract cases. Existing outer timeouts,
container limits, clean environment and cleanup remain in place.


## P02.1 disposable tenant database checkpoint

The legacy SQLite config, Alembic chain and startup remain unchanged. The independent
foundation factory takes injected FoundationSettings and does not read dotenv,
connect on construction, migrate or import Docker/legacy startup. New features default
off (WPL_FOUNDATION_ENABLED=false); no live flag/config is changed in this checkpoint.
WPL_APPLICATION_DATABASE_URL is the non-owner runtime identity; only the explicit
migration tool receives WPL_MIGRATION_DATABASE_URL. Pool defaults: two connections,
zero overflow; connect, pool, query, lock and idle transaction timeouts are bounded.
WPL_WORKER_DATABASE_URL is currently synthetic role-test input, not production wiring.

Pinned fixture: PostgreSQL 17.11, provisional pending actual provider compatibility.
Image: postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Driver pins: psycopg[binary]==3.3.6 and psycopg-binary==3.3.6. Dedicated content-hashed
check images are built without overwriting application images or restarting services.
From /tmp, run the standalone checkpoint group:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_foundation.py

Add --prepare for missing pinned image preparation, which finishes before fixtures.
The full check_local.py command and its existing CI step invoke this group mandatorily.
Standalone foundation PASS means this checkpoint only, not P02 completion. Empty or
skipped mandatory unittest suites fail; frontend registered-case policy is unchanged.

Fixtures use an owned internal network, no published DB ports, tmpfs-only data and
random disposable credentials. Only the DB container retains its bootstrap superuser.
Tests receive distinct owner/runtime/worker identities in a clean environment, with
an allowlisted read-only source snapshot, no Docker socket, provider data or private env.
Cleanup verifies ownership and removes exact inspected IDs; errors, failed inspection
and foreign labels cannot silently produce PASS. No broad prune/removal is used.
Failure/timeout cleanup contracts use mocked Docker responses; actual fixture runs
supply separate normal cleanup evidence. Fixture readiness polling is bounded.

Bootstrap creates private wpl owned by wpl_migrator, plus wpl_app and wpl_worker with
no owner/superuser/BYPASSRLS/create-db/create-role/replication privilege. Tests exercise
actual attributes, schema ownership, denied DDL/owner-role assumption/escalation and
version-ledger access, pooled commit/rollback/error, fresh/repeat/concurrent migration,
actual advisory-lock waiting and disposable downgrade/re-upgrade/schema recreation.
Tenant tables, RLS policies and worker domain permissions follow in later checkpoints;
P02.1 alone does not prove tenant authorization.

scripts/migrate_foundation.py requires an explicit migration URL and the already
provisioned dedicated owner/private schema. It holds a transaction advisory lock over
the Alembic version check and upgrade; versioning is separate in wpl.alembic_version.
No import/startup auto-DDL, remote default or dotenv fallback exists. Do not run the
migration tool against configured real infrastructure in P02. Disposable downgrade
and target recreation are test operations, not a live-data rollback procedure.
Provider compatibility, deployed activation and remote Actions remain unverified.
Tenant business tables/policy/jobs/APIs/frontend/import/file-safety work remain later
P02 checkpoints. No service restart or real migration is part of this checkpoint.
