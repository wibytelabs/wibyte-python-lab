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


### P02.2 schema and invariant services

Separate revisions add fifteen private tenant/job/mapping tables and deferred
primary/instructor/invitation guards. Foundation SQL migration sources are explicit
allowlisted snapshot inputs. The migration regression follows the actual chain head.
All application tables start with RLS enabled and no runtime grants; scoped RLS/API
behavior is a subsequent P02.3 gate. Narrow temporary grants/policies in one disposable
constraint fixture allow actual wpl_app inserts to exercise composite foreign keys;
they are removed in finally and are not production authorization policies.

Parent row updates serialize membership/role/assignment transitions, including
repeatable-read races; final-state checks run after child mutation even when a
session requests immediate constraints. A designated primary cannot be ordinarily
removed, suspended or demoted. Transfers require an active same-org target admin and
retain the old admin. Active organizations require an active accepted primary; active
cohorts require an active assigned instructor. Security suspension still blocks a
user; affected organizations/unserved cohorts enter audited recovery_required state.
That cohort state is a bounded addition to avoid refusing a necessary global block.
Reactivation/recovery is explicit; global approval does not automatically activate orgs.

Domain services use typed VerifiedIdentity without metadata grants, current DB admin
policy, parent locks, expected versions and sanitized conflicts. Ordinary membership
status/role changes and instructor replacement append audit in the caller transaction;
instructor removal retains the cohort membership history. Role/assignment/status
changes advance appropriate access epochs. Transfer completion validates current
primary, recent auth time, stored actor/version/expiry/confirmation and eligible target;
preview HTTP, executive recovery and notification outbox wiring follow in P02.5/P02.4.
No production provider verifier, debug identity header or bypass flag is introduced.
Synthetic VerifiedIdentity objects are constructed only by fixture tests in this step.

Service policy tests use explicitly labelled fixture owner sessions to isolate domain
behavior; these do not prove runtime RLS. The existing runtime-role constraint tests
remain separate. Real runtime RLS, complete multi-role policy, token verification and
route policy proofs are still mandatory in P02.3. No new endpoint is exposed yet.
Run scripts/check_foundation.py from /tmp for focused proof, then the full local gate
before committing this checkpoint. Keep recorded counts tied to the actual output.


### P02.3 identity verification slice (RLS/API work follows)

New identity settings are explicit injected data, never dotenv/legacy fallback.
WPL_AUTH_MODE defaults to provider_user when this feature's identity settings are
requested. It requires WPL_AUTH_PROVIDER_URL and WPL_AUTH_PUBLISHABLE_KEY. JWT mode
must be explicitly chosen and requires WPL_AUTH_ISSUER, WPL_AUTH_AUDIENCE,
WPL_AUTH_JWKS_URL and WPL_AUTH_ALGORITHMS (ES256 and/or RS256 only). URLs require
HTTPS, with loopback HTTP allowed for injected local fixtures. No HS secret,
algorithm autodetection, debug-user header or public bootstrap endpoint is added.
Disabled legacy/foundation imports do not resolve or require these settings.

Identity returns only verified subject, optional verified email and known session /
authentication timing. Roles, user_metadata and requested capabilities do not grant
application authority. Provider-user verification calls only the configured user
endpoint, allowing pending identities without the legacy profile-approval lookup.
Legacy CurrentUser behavior stays intact. An opaque provider token does not expose
verified session timing; account-wide last_sign_in_at is deliberately not used as
recent-auth proof. Sensitive transfers require verified timing. JWT mode accepts an
optional signed auth_time; absent timing remains unknown. Actual provider signing /
claim semantics must be verified before activation; real projects remain untouched.

JWT verification uses PyJWT 2.15.1 with cryptography 50.0.2. Signature, fixed issuer /
audience, expiry, issued-at, optional nbf, subject UUID and session UUID are checked.
Only configured asymmetric algorithms/public keys are usable. Embedded key URLs,
critical extensions, malformed headers and unsupported algorithms are rejected.
JWKS is fetched solely from configuration, bounded to 32 keys/128 KiB with finite
cache TTL/unknown-key refresh interval and synchronized fetch. Fresh cached keys can
verify during an outage until TTL; stale cache fails closed. This does not detect
provider logout immediately. Current database state and future gateway epochs remain
separate authority/revocation checks.

The identity HTTP client has no environment proxy trust/redirect following, finite
phase timeouts, bounded read-loop deadline and body caps. It requests identity
encoding and rejects compressed responses before decoding. These are application
bounds, not an OS-level guarantee against a blocked system resolver. No provider
body/token/DSN details are included in public verification errors. Invalid tokens
map to 401; transient/bad provider responses map to 503. Runtime RLS, pooled trusted
context and /v1/me are still the next P02.3 slice, not established by these tests.

Every mandatory foundation module is explicitly registered; missing, undeclared or
empty modules and skipped cases fail without a fixed case-count guard. New modules
must update FOUNDATION_TESTS in scripts/check_foundation.py.

Mandatory identity tests use real generated ES256/RS256 signatures and injected
httpx synthetic transports for provider/JWKS cases. Cache-clock advances test rotation,
outage and refresh rate without sleeping. Injected timeout/redirect/body fixtures
are not a real provider outage benchmark. The dependency preparation probe separately
verified ES256 and AES-GCM offline in the pinned Python 3.14 image. Actual invitation
payload encryption/key-provider implementation still belongs to P02.4.

### P02.3 transaction context slice (scoped RLS/API still pending)

RequestContext pairs a VerifiedIdentity with a server-selected RequestScope enum
(global, platform, tenant or personal) and an optional typed organization UUID.
Tenant scope requires an organization; global and personal scopes prohibit one.
Platform scope can carry an explicit target organization or a directory scope.
This context does not grant permissions: current DB state and scoped RLS/application
policy must independently authorize access. Never construct it from caller actor,
role, capability or GUC names. No worker authority is added by this request scope.

FoundationDatabase.request_transaction binds only four fixed settings through
parameterized set_config calls: wpl.actor_id, wpl.scope_kind, wpl.org_id and
wpl.auth_time. The last value is verified authentication timing, or empty when
unknown. All values are transaction-local; every scope overwrites every field.
The existing session/transaction context managers commit or roll back and release
the checked-out connection, including BaseException cancellation. Keep the yielded
session within this boundary; no SET ROLE or session-persistent context is used.

Mandatory disposable Postgres tests use actual wpl_app with a pool of one and
assert reuse of the same backend PID across actors/scopes. Commit, ordinary Python
failure, SQL error, raised CancelledError and actual PostgreSQL statement timeout
must clear actor/org/auth timing before the next checkout. The cancellation test
raises the request cancellation exception at the transaction boundary; it is not
an HTTP disconnect or transport cancellation test. Tests also exercise missing
org/timing values and global/personal/platform scope transitions without trusting
raw actor dictionaries. Direct DB credentials remain a trusted server boundary;
custom settings are not a defense against compromise of those credentials.

Context lifetime proof alone is not tenant isolation proof. Scoped production RLS,
API identity/context wiring and the two-org authorization matrix remain pending.

### P02.3 scoped read RLS slice (mutation/API policies still pending)

Revision p0204_read_rls grants the non-owner application role SELECT on scoped
organization/cohort data and selected user/capability columns. User email and
platform grantor/reason columns are not included in these read grants. No write,
worker, secret-payload, audit or migration-map authority is added by this slice.
Table RLS remains enabled. Missing, malformed or incompatible actor/scope/org
settings return no rows; SQL UUID context parsing does not cast unchecked text.

Only six boolean policy entry points receive app EXECUTE. They run as the schema
owner with a fixed pg_catalog,wpl search_path and qualified objects, avoiding
recursive RLS table lookups. Internal context/permission helpers and existing
trigger functions remain private; worker receives no helper execution. The trusted
migration owner deliberately bypasses RLS for policy helper queries and synthetic
fixture setup. Runtime ownership/BYPASSRLS is neither granted nor required.

Active tenant admins can read all cohorts in their organization. Instructors need
an active instructor assignment and organization role for cohort/roster access;
a separate student assignment does not inherit their instructor authority. Students
read their own membership/roles/assignments. Global identity scope permits only
own user/membership summaries (including pending state). Personal scope grants no
tenant data. Directory executives require an unexpired explicit orgs capability in
platform scope; this does not supply tenant impersonation or roster access.
Recovery roster metadata requires an explicit recovery capability and target org.
No recovery mutation or authority-grant endpoint is provided by this slice.

Mandatory read RLS tests use production policies with actual wpl_app transactions
and synthetic two-org, multi-role fixtures. They cover current user/member status,
capability expiry, invalid context, private-column/helper denials and absence of
mutation grants. Owner connections seed test records only. The older composite-FK
fixture still temporarily grants narrow constraint-test writes; it restores prior
read grants and is not counted as production mutation authorization proof. Scoped
write policies, service runtime transactions and HTTP comparisons remain pending.

### P02.3 HTTP read slice and pending identity mirror

The shared versioned router is backend.app.foundation.api.router, internally /v1.
The independent factory mounts it only when FoundationSettings.enabled is true,
with explicit IdentitySettings and optional trusted HTTP transport injection for
fixtures. Verification still uses the production verifier; request headers cannot
select a transport or bypass it. Construction does not connect, migrate or load
legacy/private environment. Lifespan verifies the non-owner DB identity and closes
both DB pool and verifier resources. Legacy main/startup routes remain untouched;
conditional mounting for a later approved activation must reuse this router.

GET /v1/me verifies bearer identity, binds GLOBAL context and inserts only the own
UUID if absent. Revision p0205_identity_mirror grants INSERT(id) with an own-subject,
global-scope, pending-default policy helper. It grants no approval, role, email or
identity-remapping authority. Existing records use ON CONFLICT DO NOTHING; no
request-driven version churn or email-based lookup occurs. Email/metadata/session
claims are not returned. Pending/blocked users get their own status and membership
summary with effective can_enter=false and no capabilities. This narrowly scoped
identity insert supersedes the prior read-only slice's absence of all write grants;
privileged tenant mutations remain denied until their own policies are implemented.

GET /v1/orgs/{o} requires an active user/membership/org; contact and primary-member
fields are omitted for non-admin roles. GET /v1/orgs/{o}/members is the P02 minimal
admin-only transfer-selection list, not the P05 instructor/full directory product.
GET /v1/orgs/{o}/cohorts supplies the small read surface needed to compare HTTP and
actual assignment-aware RLS. No cohort management endpoints are introduced here.
Lists use {items,next_cursor}, limit 1..100 and parameterized (created_at,id) cursor
ordering. The /me membership summary uses the same bounded pagination. New indexes
support the tenant membership/cohort page ordering. Invalid cursor syntax returns
400, semantic validation 422, missing identity 401, explicit policy denial 403,
inaccessible resources 404 and identity/data unavailability sanitized 503.

Responses carry no-store, a server-generated request ID and the shared error
{code,message,request_id,field_errors?} shape. Validation errors do not echo input;
DB/provider/token details are omitted. Header actor/role/org spoofing is ignored.
A cached verified token does not override current DB suspension on new requests.
These checks do not claim immediate provider logout or live gateway revocation.

Current nginx source maps public /api/v1/... to internal /v1/... by its existing
location /api/ and trailing-slash loopback proxy_pass. The runner snapshots that
non-secret template explicitly. Tests inspect this source mapping and exercise
internal routing; they do not launch a reverse proxy or claim browser/provider
smoke. Real authenticated browser/provider smoke remains NOT RUN, and remote
Actions execution remains separate evidence. Synthetic HTTP tests pass real signed
tokens through the production verifier and factory into actual wpl_app RLS using
only injected JWKS transport, the disposable DB and owned internal network.

The own-user SELECT predicate permits the verified actor UUID without first
requiring a stored user row. PostgreSQL checks SELECT policy for proposed rows in
INSERT ... ON CONFLICT (id) DO NOTHING, before a first mirror is stored. Checking
existence inside the permission helper makes that first request fail despite a
valid INSERT policy. Existing table scans still return only actual rows. A direct
runtime regression executes the same statement twice, proves one pending mirror,
and rejects other-subject insertion and approval writes. No extra table/column
privileges or authority grants are added by this predicate correction.
