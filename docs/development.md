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

### P02.3 ordinary tenant mutation slice

Revision p0206_tenant_mutations adds application tenant-admin UPDATE policies for
metadata/member status and SELECT FOR UPDATE locks, role INSERT/DELETE and instructor
assignment INSERT/UPDATE(status). Column grants exclude identity/org remapping,
access epochs, global approval and the protected primary designation. Parent/version/
epoch and deferred primary/final-instructor triggers still run. No organization or
membership creation, transfer ledger, executive, worker or queue grant is added.

Only write_tenant and write_tenant_audit are new public-to-app boolean entry points;
PUBLIC and worker execution remains revoked and internal helpers stay private. Audit
INSERT is limited to the bound actor, same-org admin, supported membership/cohort
actions, existing same-org targets and a bounded reason. UPDATE/DELETE of audit stays
ungranted. Tenant admins may read own-org audit; unbound/non-admin/cross-org access
remains filtered. Domain operations append audit in the same request transaction.
Failure, including audit failure, must roll back business changes together.

Shared service policy checks that the current application DB context matches the
passed VerifiedIdentity and organization before checking actual active grants. The
trusted migration owner remains available only for fixture/maintenance callers and
is rejected as an application runtime identity by the factory. No request bypass
flag or actor header can select that role. Worker domain calls remain denied until
an explicit worker authorization design is implemented in P02.4.

New actual-wpl_app tests run production member/role/instructor services in bound
request transactions. They test versions, epochs, history, audit and rollback,
non-admin/cross-org/context-substitution denials, direct SQL invariants and competing
administrators. Ordinary self-demotion/suspension fails closed when it removes the
current mutation/audit authority; explicit exit/rejoin workflows remain P05 work.
Primary designation writes remain denied pending the protected P02.5 transfer/recovery
workflow. Current APIs remain read-only except the own pending identity mirror.
The RLS suite's earlier generic denial test now checks DELETE users rather than
DELETE organization_roles, because scoped admin role deletion is deliberately added.
The constraint fixture uses production role/assignment grants and retains temporary
constraint-only transfer/invitation policies until those workflows are implemented.

### P02.4 encrypted payload primitive (enqueue/worker wiring follows)

backend.app.domains.jobs.payloads uses the installed cryptography AESGCM API with
an explicitly resolved 32-byte key and a fresh random 12-byte nonce. Envelopes carry
WPL1, nonce and authenticated ciphertext/tag; ciphertext is excluded from dataclass
repr. There is no legacy signing-key, environment, file, synthetic-default or remote
provider fallback. Concrete KeyProvider.current_reference/resolve implementations
must be injected by the trusted composition root. Synthetic providers live in tests
only. Key references are bounded identifiers, not key material; rotation resolves the
recorded reference and retains old references only while needed. Key lifecycle and
operational nonce/message budgets remain requirements before real activation.

Associated data binds version, key reference, tenant/personal/platform scope and
scope UUID, verified actor UUID, operation UUID, payload UUID and job purpose. This
prevents an encrypted delivery capability being swapped between those contexts.
These bindings are not permission grants: enqueue/worker callers must validate
current actor/scope authority separately. Personal scope matches its actor; platform
scope uses the reserved zero UUID. No arbitrary worker impersonation API is added.

Payloads are JSON objects with string keys, finite numbers, bounded nodes/depth and
at most 32 KiB canonical UTF-8 bytes. Binary envelopes are at most 32800 bytes,
inside the existing secret_payloads schema limit. Malformed/tampered envelopes,
wrong binding/key, duplicate-key/non-object JSON and invalid sizes fail closed.
Missing/invalid key material produces a sanitized key-unavailable error; corrupt
payloads produce a separate sanitized invalid-payload error. Neither includes raw
payload/key/provider details. No API returns decrypted payloads from this module.

Mandatory tests use real AES-256-GCM and synthetic keys, including scope/actor/
operation/payload/purpose/reference swaps, nonce differences, rotation/retirement,
tampering, invalid JSON and size boundaries. An owner-seeded disposable DB test
persists actual ciphertext, decrypts the stored value with the explicit fixture key,
and verifies actual wpl_app SELECT ciphertext is still denied. This is ciphertext
compatibility/isolation proof, not production enqueue/worker authorization proof.
Durable job/outbox insertion, idempotency, lease fencing, retry/dead-letter, current
actor rechecks and fake delivery remain the next P02.4 slices. Real mail delivery,
provider/KMS configuration and authenticated browser smoke remain NOT RUN.

### P02.4 transactional idempotency foundation (tenant operations first)

jobs.idempotency.execute_idempotent runs a trusted server callback in the existing
bound request transaction. Its first allowlisted operations are member status,
organization role replacement and instructor assignment. The caller supplies a
RequestContext, operation enum, bounded idempotency key and canonical JSON object.
No HTTP caller supplies a callback or arbitrary SQL/operation/capability name.
Keys are scoped by verified actor, operation and tenant organization. Only a SHA256
request digest is stored, alongside a small fixed-shape public result, not the raw
request. Status/member/cohort IDs, roles and version are the only receipt fields;
private capability/token/payload fields are rejected before persistence.

Current context/permission is checked before locking and again after acquiring a
transaction-scoped advisory lock derived from the complete actor/operation/scope/key.
The existing composite database primary key remains the final uniqueness guard.
Same-key/same-body replay returns the saved result; changed input raises the stable
idempotency_conflict (409) without repeating the callback. A callback runs inside a
savepoint so failure/invalid result rolls its writes back even if the caller catches
the error. Outer rollback also discards business/audit/receipt together. The returned
outcome is provisional until the caller's outer transaction commits. Callback code
must not commit or perform external I/O; external effects belong to durable outbox.

Revision p0207_idempotency grants only own-actor/current-tenant-admin SELECT/INSERT
for these operation receipts, with an explicit policy helper, safe search_path and
bounded public JSON shapes. No UPDATE/DELETE, worker, personal/platform receipt or
business authority is added. Cached responses also require current permission;
revocation cannot be bypassed by reusing an old request key. Transaction pool lock
and statement timeout bounds apply. Hash collisions can serialize unrelated work;
the database primary key, not a lock hash alone, defines receipt identity.

Real wpl_app tests invoke actual mutation services and prove concurrent replay,
changed-body conflict, actor/org/operation separation, pool-independent persistence,
outer/savepoint rollback, current-permission recheck, PK uniqueness, immutability and
secret-field rejection. This is the foundation for operation idempotency, not proof
of idempotent organization creation or external exactly-once delivery. Organization
creation/status/primary and enqueue operations must explicitly add their operation,
scope, receipt schema and production API wiring in subsequent P02.4/P02.5 slices.
Durable jobs/outbox and worker lease/fencing/retry/current-actor checks remain pending.

### P02.4 tenant invitation enqueue foundation

jobs.enqueue prepares a typed invitation delivery before the database unit of work.
prepare_invitation resolves the explicitly injected key provider and encrypts the
bounded invitation payload; no key-provider I/O or encryption occurs inside
enqueue_invitation. Production key-provider configuration and delivery integration
remain explicit future wiring. Synthetic tests supply their own key provider.

Inside the bound tenant transaction, enqueue_invitation checks the current actor's
administrator authority and the current invitation UUID, organization, pending
membership, normalized recipient, token digest and expiry. A delivery UUID lock
serializes retries. Matching intent replays its job receipt; changed intent or an
unverified legacy ID collision fails without adopting another job. A nested
savepoint persists ciphertext, queued job, pending outbox and redacted audit
atomically; an enclosing idempotent business transaction owns final commit/rollback.
No activation token, email or ciphertext enters the public receipt or audit.

Revision p0208_enqueue grants tenant administrators narrowly scoped INSERT and
readable job metadata. Private ciphertext remains unreadable by wpl_app. Application
code cannot mark a job complete, dispatch an outbox entry, update/delete queue rows,
or acquire worker privileges. Helper EXECUTE grants are explicit and checked with
safe search_path and owner identity. Jobs without the new verified intent hash are
not exposed or adopted. Existing private fixture rows remain unchanged.

The only operation here is deliver_invitation for an existing pending tenant
invitation; platform provisioning requires separate authority and policy wiring.
The receipt means queued/pending_integration, never delivered or activated. No
provider, mail, browser session, worker loop or application route is invoked.
Worker claims, lease fencing, retries, current-actor checks before effects and fake
adapter crash/reconciliation proof remain pending. The eventual external call must
run outside a database transaction.

Actual-role tests cover ciphertext persistence, scoped metadata, concurrent
same-intent deduplication, conflicting input, key resolution before checkout,
invalid/revoked/expired target denial, actor substitution, immutable queue metadata,
legacy collisions and a real unique-constraint outbox failure. Business state,
audit, receipt and queue rows roll back together on failure or outer rollback.

### P02.4 restricted worker claim and renewal

Revision p0209_worker_leases gives wpl_worker EXECUTE on claim_deliveries and
renew_delivery only. Worker table SELECT/INSERT/UPDATE/DELETE and payload reads
remain denied; wpl_app cannot call either worker entry point. Owner-definer
functions use an explicit safe search_path, qualified objects and no dynamic SQL.
The shared private delivery_actor_allowed predicate also backs tenant_admin, so
request services and worker decisions require the same current global user,
organization, active membership and administrator role. Worker decisions use
stored job actor/org/scope, independent of caller-supplied session context.

claims use FOR UPDATE SKIP LOCKED with a batch of 1..20 and a lease of 5..300
seconds. Only due tenant invitation jobs with verified intent, private payload
reference and matching durable delivery outbox are considered. A successful claim
increments attempts and lease generation, records owner/expiry, dispatches the
outbox intent and appends a redacted audit in the same transaction. Dispatched
means the intent reached the database worker lease, never that mail was sent.
Expired running jobs can be reclaimed; generation advances and stale/foreign
owners cannot renew. Exhausted jobs become dead and revoked actors' jobs cancel.
Both terminal decisions clear leases and append audit. Renewal requires the exact
unexpired owner/generation and current stored actor permission; it never shortens
the lease. Invalid bounds are rejected in Python and independently in PostgreSQL.

The Python wrappers own short transactions and return only after commit. They do
not resolve keys, load ciphertext, contact providers or initialize workers on
import. Synthetic tests use actual wpl_worker connections, competing claims,
explicit expiry timestamps, a held row lock, rollback, stored-actor revocation,
maximum attempts, delayed availability and privilege denials. No long sleeps.

Payload loading, fenced completion/retry/backoff, fake external delivery dedup and
crash reconciliation remain separate pending gates. A valid lease alone does not
prove delivery or universal exactly-once effects. There is no production worker
loop or runtime activation in this slice.

### P02.4 fenced worker payload and transition foundation

Revision p0210_worker_transitions adds three worker-only owner-definer functions:
delivery_payload, authorize_delivery_target and finish_delivery. No direct worker
or application table access is added. Each checks stored tenant job scope/kind,
verified intent and the exact running lease owner/generation and current expiry.
Payload loading additionally requires the current stored actor's administrator
authority and returns only that leased job's scoped encrypted material. Python
returns an envelope/binding after commit; decrypt/key resolution happens outside
the database transaction. Material repr omits the encrypted envelope.

After decrypting, authorize_delivery checks the fixed invitation shape, recomputes
the complete actor/org/kind/payload intent hash, and asks PostgreSQL to recheck the
current actor and exact pending invitation recipient, token digest and expiry.
A different otherwise valid invitation cannot substitute for this job's payload.
Run this immediately before an external call. This check cannot make provider I/O
atomic with database revocation; external adapters still need stable operation
identity and reconciliation. No adapter/provider is invoked by these wrappers.

finish_delivery accepts only success, bounded retry codes (transport_unavailable,
key_unavailable), or bounded cancellation codes (payload_invalid,target_unavailable).
Late/foreign/expired generations return no transition. Current actor revocation
cancels even an attempted success. A valid retry clears the lease and persists a
5-second exponential delay, capped at 300 seconds, or dead-letters at max_attempts.
All outcomes append fixed-shape audit with stored actor, worker and generation;
provider exception details, recipient and token are never accepted as error codes.
A database rollback restores state and discards the audit together. Returned state
is committed before the wrapper returns. A succeeded database fixture transition
is not evidence of mail delivery or provider integration.

Actual-role tests prove scoped payload access, target/intent checks, pool release
before decrypt, expiry/reclaim completion fencing, one terminal audit, backoff and
cap without sleeps, dead-letter, global/member/role/org revocation, transition
rollback and denied application/worker table privilege bypass. Fake delivery and
crash-after-external-success reconciliation remain pending, as do actual provider,
production worker loop and public job-status route integration.

### P02.4 explicitly injected delivery execution and synthetic reconciliation

jobs.execution.process_delivery runs one committed lease using an explicit cipher
and adapter. It loads only fenced encrypted material in a short worker transaction,
then resolves/decrypts keys after commit, renews the lease and rechecks the exact
current invitation/actor/intent before calling the adapter outside the database.
The adapter must honor a 10-second timeout and deduplicate/reconcile by the stable
job UUID across retries, process restart and lease generation changes. No daemon,
provider credentials, network client, concrete mail adapter or key defaults are
initialized here. Provider exceptions become a fixed transport_unavailable code;
key errors retry, invalid payloads cancel, and stale leases cannot complete.

Adapters return the enum SIMULATED or PROVIDER_ACCEPTED, not an arbitrary message.
Revision p0211_delivery_execution atomically acknowledges a current lease and
records delivery_status as simulated or provider_accepted plus redacted audit.
Application reads/replayed enqueue receipts preserve that status. A fake adapter
never becomes Delivered; provider_accepted would only mean an explicitly integrated
provider accepted the request, not that a recipient received/read mail. Existing
control fixtures retain pending_integration unless explicitly acknowledged. No
real provider implementation or browser delivery smoke is part of this slice.
The actual worker/application still have no direct queue update or payload SELECT.

A test-only adapter uses a separate temporary SQLite provider store with a unique
operation UUID and request digest. It does not store raw token/email or send mail.
Tests crash after that store commits, then reclaim with a new worker pool, key
provider and adapter object and reconcile one simulated effect. Overlapping old
and reclaimed workers use the same provider operation identity; one current lease
acknowledges and the old generation loses its completion. A real PostgreSQL CHECK
failure after fake acceptance rolls back completion/audit; subsequent reclaim
reconciles the same durable fake effect. This demonstrates the specified adapter's
dedup contract, not universal exactly-once delivery from a database lease.

Other actual-role checks exercise transport retry with fixed diagnostics, key
unavailability, tampered ciphertext, role revocation during key resolution, revoked
targets, required adapter injection, unrecognized acknowledgement and explicit
simulated status/audit. Fixture timestamps avoid long waits. No database checkout
is held during key resolution or fake adapter I/O. Global/member/role/org and
expiry checks remain shared with the earlier transition tests. Revocation can
still race an external call after the final database check; adapters require
operation-specific reconciliation and deployment policies before activation.

This completes the isolated tenant invitation job plumbing, not pending-organization
platform provisioning, organization-create idempotency, public job-status routes,
executive APIs, real provider setup or final P02 acceptance. Those gates remain
explicitly pending. Run the complete local gate before recording this checkpoint.

### P02.5 executive directory and tenant job-status reads

Internal GET /v1/platform/organizations is a bounded cursor-paginated executive
organization directory with status/type filters and literal case-insensitive name
search (max 120 characters). It requires the current active user's explicit orgs
platform capability, including expiry, in a bound platform transaction. Tenant
admin status or JWT/user metadata does not grant this capability. The shared domain
policy checks the actual application DB role and actor/platform/target context;
there is no owner/request-header bypass. Explicit platform directory RLS already
exists; this slice introduces no database grants or migrations.

GET /v1/platform/organizations/{org_id} uses targeted platform scope and an explicit
metadata projection. Directory list/detail do not grant tenant roster or job access.
GET /v1/orgs/{org_id}/jobs/{job_id} uses current tenant membership plus existing
job actor/admin RLS and returns only job ID/kind/state/delivery_status, bounded
attempt counts, fixed error code and timestamps. It never selects ciphertext,
private payload/key references, intent/dedup hash, lease owner or raw invite values.
Cross-org, unknown and unauthorized job IDs share not_found. Persisted simulated,
pending_integration and provider_accepted remain distinct; none imply inbox delivery.

These routes use the existing real signature-verification dependency, error envelope,
no-store/request ID middleware and internal /v1/public /api/v1 proxy contract.
Foundation feature-off keeps them unmounted. HTTP tests use synthetic real ES256
signatures, MockTransport JWKS only and actual wpl_app policy/role connections.
Owner writes seed explicit executive capability fixtures and display-state cases;
no user is automatically granted a platform role. No actual provider is contacted.

Provision/create/PATCH/status/primary-transfer/recovery write routes, initial pending
primary workflow, platform enqueue authority and organization-create idempotency
remain pending. This read slice returns no placeholder provisioning/write success.

### P02.5 versioned executive metadata and organization status

PATCH /v1/platform/organizations/{org_id} accepts expected_version, reason and an
explicit nonempty subset of name/contact_email/home_region. Extra fields (actor,
role, primary designation, scope, charge/delete) are forbidden. Email/name inputs
are normalized and bounded; versions reject boolean coercion. POST at the same
organization path plus /status accepts expected_version, reason and active or
suspended only. Both run actual verified identity in explicit target platform scope
and require the current active executive's orgs capability; expiry/revocation and
ordinary tenant admin/JWT metadata cannot bypass that requirement.

Revision p0212_executive_metadata exposes only change_organization to wpl_app, with
safe owner-definer search_path and independent fixed operation/context/input/grant
validation. It grants no direct status/designation/epoch/table write or worker
EXECUTE capability. The function locks the organization, rechecks authority and
expected version, and performs update plus redacted audit in the same statement.
The domain service wraps this in a savepoint so a caught audit failure cannot leave
partial metadata. Existing triggers own version/epoch updates. Metadata audit lists
changed field names, not contact values; status audit records from/to and versions.
No-op edits retain version and do not create a spurious audit.

An active or suspended state requires a verified active designated admin. Pending
initial invitations cannot activate or be moved into an invalid non-pending state.
recovery_required cannot be cleared by this ordinary orgs-capability status path;
the reasoned protected recovery operation remains separate. This slice adds no
implicit approval, invitation acceptance, primary transfer, real mail or side-effect
job. Initial provisioning/idempotent create and protected recovery remain pending.

Actual HTTP/domain tests use real synthetic ES256 verification and wpl_app, explicit
fixture-only executive grants, metadata/status epochs/audit, validation/extra-field
rejection, cached authority denial, pending-primary/recovery safeguards, two actual
app connection race winners/conflicts, direct status/context bypass denial and a
real CHECK failure proving audit/business rollback even when the caller catches it.
No private configuration or running application is activated.

### P02.5 atomic pending organization provisioning foundation

organizations.provisioning.prepare_organization validates a fixed OrganizationCreate
request and generates fresh org/member/invitation/job/payload UUIDs and a random
activation capability. An explicit PayloadCipher resolves its key and encrypts the
bounded delivery payload outside the DB transaction. Raw capability/email inputs
are omitted from prepared-object representations and public receipts. No legacy
signing key, automatic key fallback or real secret provider is supplied.

create_organization requires the actual bound application actor in platform scope
with current orgs capability and no tenant target. Revision p0213_provisioning
exposes one narrow owner-definer function with safe search_path and independent
scope/capability/input validation; no direct table/worker/bootstrap grants. It
computes a canonical request digest in PostgreSQL, serializes the complete
actor/platform/create-operation/key namespace, rechecks current permission, and
uses the existing composite idempotency primary key as the final guard. Same
actor/key/body replays one saved public receipt; different body conflicts, while
another executive has a separate key namespace. Cached receipts still require
current permission. Generated crypto IDs/ciphertexts are excluded from the request
digest so preparation on a retry does not repeat creation.

The transaction inserts a pending organization, one designated invite_pending
membership with NULL user_id, admin role, pending invitation/digest, encrypted
payload, queued deliver_primary_invitation job, pending outbox, redacted creation
and enqueue audits and fixed-shape idempotency receipt. It never matches a user by
email, approves an identity, grants platform authority or activates the primary.
All records share a savepoint and outer caller-owned commit; actual audit CHECK
failure and outer rollback remove every partial record. No-op replay does not
persist its freshly prepared payload or alternate IDs. The receipt describes the
original persisted pending/queued result; current detail must be fetched separately.

This is the database/service foundation, not the POST create HTTP endpoint yet.
The initial-primary job uses a separate kind and remains queued/pending_integration;
current tenant invitation workers intentionally do not claim this pending-org,
executive-actor kind. Its explicit worker authorization, HTTP composition/key-provider
injection and platform job-status path follow separately. No delivery/activation
success or real provider integration is claimed by this slice.

Actual wpl_app tests prove pending designation/circular constraints, no email-only
identity remap, encrypted persisted payload/redacted receipt/audit, same-key concurrent
one-org/invite/job/outbox receipt, changed-body conflict, new-pool replay, separate
executive namespaces, current capability revocation, outer/savepoint failure rollback,
invalid input/key/provider/context rejection and direct-table/receipt privilege denial.
No generated raw token is returned in test diagnostics or stored as plaintext.

### P02.5 initial organization create HTTP and platform job status

POST /v1/platform/organizations validates the fixed OrganizationCreate body and
requires an ASCII bounded Idempotency-Key header. It uses the actual verifier and
explicit platform context, checks current capability and an actor-scoped saved
receipt before preparing new crypto. New creation returns 201 only after the full
organization/invite/payload/job/outbox/audit/receipt transaction commits. A repeated
body/key returns the identical public body/status with Idempotency-Replayed: true;
changed input returns 409. Current permission still applies. Saved receipt replay
works without key resolution, even during key-provider outage or after restarting
without crypto configuration. The original receipt reports its persisted creation
result; use detail/job reads for subsequent current state.

create_app accepts only an explicit optional PayloadCipher at the trusted server
composition boundary. There is no key environment/file/signing-key fallback or
automatic provider setup. Read/metadata routes still work when crypto is absent;
new create returns a sanitized delivery_unavailable (503), never placeholder success.
Pre-auth/read transaction closes before key resolution/encryption. A second current
authority check inside creation prevents a key-time revocation from committing.
No private configuration is changed and no real provider is contacted.

Revision p0214_provisioning_reads gives wpl_app two narrow owner-definer read entry
points for actor/platform/create receipt lookup and targeted initial-primary job
metadata. It adds no direct private table or worker permissions. GET at
/platform/organizations/{org_id}/jobs/{job_id} requires current orgs capability and
explicit target scope, reads only that org's verified deliver_primary_invitation
job, and excludes raw invitation/key/ciphertext/hash/lease data. Executives do not
implicitly gain tenant membership or arbitrary tenant-job/roster access.

HTTP tests use real synthetic ES256 tokens and actual runtime roles, explicit
fixture-only keys/capabilities and a thread-local checkout guard during key I/O.
They exercise 201/pending receipts, concurrent/replayed/changed-body requests,
provider outage replay, key-time revocation, unauthorized/invalid/missing config,
redacted targeted job scope, feature-off and unchanged tenant boundaries. The
initial-primary worker kind remains queued/pending_integration until its explicit
stored executive/pending-org authorization is wired separately; no activation,
acceptance of an invitation or delivery success is implied by HTTP 201.

### P02.5 initial-primary worker authorization

Revision p0215_primary_worker extends the existing fenced claim/load/renew/target/
finish entry points to the explicit deliver_primary_invitation kind. A private
shared predicate validates stored creator UUID/current active global state, current
unexpired orgs capability and the stored organization's pending state. Ordinary
tenant invitations retain the same current active tenant-admin predicate. Caller
worker GUCs cannot substitute a different executive or tenant actor. No new public
function/table privilege is granted; the private helper remains non-executable by
app/worker roles. Existing lease owner/generation/expiry/attempt bounds remain.

Payload load returns the stored known kind for authenticated payload binding.
Execution uses that purpose in the full intent check. Initial-primary target
checks additionally require the current designated membership, NULL user binding,
pending matching invitation and admin-only intended roles. Revoked/expired invites,
non-designated targets, lost capability, global suspension or no-longer-pending
organization cannot produce a new effect. The ordinary route still cannot approve,
activate, accept invitations or assign platform authority. Initial delivery uses
the explicit adapter timeout and the same stable operation dedup/reconciliation.
Fake acceptance persists simulated while org/member/invitation stay pending.

Actual-runtime tests connect the signed HTTP create flow to wpl_worker and the
durable test-only fake adapter, inspect redacted platform status and pending identity
invariants, exercise stored actor/expiry/target denials, mixed-kind competing claims,
stale generation/crash reconciliation and raw helper privilege denial. The full
ordinary tenant worker test matrix remains mandatory. No real mail adapter/key
provider/daemon activation is supplied; protected transfer/recovery remains pending.

### P02.5 protected transfer preview boundary

Revision p0216_transfer_preview introduces an app-only preview entry point and
private authority helper. Tenant scope requires the current globally active,
active-member designated Primary Admin of an active organization. Platform scope
requires the separate current recovery capability, explicit target org and
recovery_required state; directory orgs capability alone cannot preview recovery.
The helper has no public/app/worker EXECUTE grant. No direct transfer table read,
insert or designation update permission is added.

The org parent lock serializes previews with membership/role/status writes. The
entry point rechecks authority after locking, requires expected organization
version and another active same-org admin, and stores actor/from/to/scope/reason,
a SHA256 confirmation digest and a five-minute deadline. It leaves designation,
roles, organization state and epochs unchanged. Only one live preview is allowed:
the same actor can replace its preview; a different actor conflicts until expiry.
Preview and redacted audit share a transaction/savepoint. The Python service
requires actual wpl_app context, generates a random confirmation returned once
and excludes it from repr; it never returns the stored digest or member email.

This slice supplies no HTTP route, completion mutation, notification job or
recovery activation. Those follow separately with recent-auth confirmation,
version/target/authority recheck and atomic notification intent. Existing ordinary
primary and instructor guards remain unchanged. Mandatory actual Postgres tests
cover primary/recovery authority, target/version/context denials, preview expiry
and competing actors, rollback/audit failure and raw runtime privilege boundaries.

### P02.5 confirmed primary change and recovery transaction

Revision p0217_transfer_completion exposes one narrow app-only confirmation root.
The service requires an exact actual wpl_app actor/scope/org/auth-time context.
The root independently checks a server-bound authentication time within five
minutes (at most 30 seconds future skew), including after locks. The preview's
actor, org, authorization scope, expected version and SHA256 confirmation digest
must match. A live unexpired preview must still refer to the current designation,
organization version and another active same-org admin. Tenant execution requires
the current Primary Admin; recovery requires the separate current unexpired
recovery grant and recovery_required state. Reasons are retained from the preview.

Identity rows are share-locked in UUID order before the org parent lock, matching
the user-before-org order of global security suspension. Recovery also locks the
current capability row. The transaction then rechecks authority/target/version,
changes the single designation and, for explicit recovery, restores active org
state without changing the old identity's global security state. Existing triggers
advance version/epoch once and retain the old active admin membership/role.
No approval, account remap or platform grant is performed.

Designation, completed preview/public receipt, redacted audit, a queued
notify_primary_transfer job and pending primary_transfer_notification_requested
outbox are atomic. Intent uses private stored from/to IDs and a canonical digest;
no email address, credential or confirmation value is put in the job/outbox/audit.
The notification job has no secret payload and remains pending_integration.
Existing invitation workers deliberately ignore this distinct kind. A notification
worker/provider integration and public HTTP/status routes follow separately; this
slice claims durable notification intent, not delivery. No real provider is called.

The preview UUID is the one-use operation identity. Repeated matching confirmation,
including simultaneous requests or a new pool after commit, returns the persisted
public receipt without a second change/job/outbox. Replay still requires recent
authentication, matching actor/scope/digest/version and current tenant-admin or
explicit recovery authority. Thus the former primary can replay while still an
active admin, but removal/global block/grant revocation denies cached receipts.
The receipt describes the committed operation; current job state is separate.

Actual Postgres tests cover normal/recovery change, old admin retention and global
block preservation, wrong/expired confirmation and stale versions/targets, current
recovery grant expiry/revocation, concurrent confirmations, actual transfer/removal
and target-global-suspension lock races, outer rollback/new-pool retry and real
audit/outbox constraint failures caught inside savepoints. They also retain direct
column/table/helper/worker denial. No broad table privilege or root bypass is added.

### P02.5 signed transfer and explicit recovery HTTP

The shared internal /v1 router adds these public-proxy /api/v1 operations:

- POST /orgs/{org_id}/primary-admin-transfers/preview: current Primary Admin.
- POST /orgs/{org_id}/primary-admin-transfers: confirm that actor's preview.
- POST /platform/organizations/{org_id}/primary-admin-recovery/preview: explicitly
  granted recovery executive targeting an org in recovery_required state.
- POST /platform/organizations/{org_id}/primary-admin-recovery: confirm recovery.
- GET /platform/organizations/{org_id}/primary-admin-recovery/jobs/{job_id}: current
  recovery authority, redacted status of the exact completed transfer's notification.

The route selects tenant/platform context; no body/header scope/actor/capability
selector exists. An orgs directory grant does not permit recovery or tenant entry.
Both preview and confirmation require production-verified authentication within
five minutes, with at most 30 seconds future skew. Missing/old timing gets fixed
recent_auth_required conflict; invalid signed timing is rejected by the verifier.
No provider account login timestamp or caller header substitutes for this proof.

Preview requires target_membership_id, strict positive bounded expected_version
and a bounded nonempty reason. It returns from/to IDs, five-minute expiry, a one-use
confirmation and the explicit former-primary-retains-admin consequence. Confirmation
accepts only transfer_id, the original expected_version and confirmation. It uses
the preview UUID as stable operation identity: committed retries return the same
public receipt with Idempotency-Replayed true, after current authority and recent
authentication are rechecked. Confirmation values/hashes are excluded from errors,
audit, job status and completion receipts. Body extra fields cannot substitute IDs.

The required expected_version body field follows the implemented foundation write
contract. A supplied strong If-Match header must equal the quoted body version;
weak/mismatching values fail version_conflict. This supports the planned If-Match
contract without silently ignoring it, while retaining the existing explicit body
version convention. Responses are emitted after transaction commit. Unknown or
expired preview/confirmation and stale org version produce fixed conflicts.

Revision p0218_transfer_job_read adds one app-only safe read root, no table grants.
GET /orgs/{org_id}/jobs/{job_id} retains ordinary invitation reads and can now use
that root for current active admins' transfer notification status. It verifies the
completed private transfer receipt, actor/org/kind/dedup/intent digest and matching
outbox before returning only the existing nine job status fields. Platform recovery
status uses the same root with explicit current recovery scope. Cross-org, absent,
unauthorized or tampered intent yields not_found. The ordinary executive initial-
invitation status route stays specific to that job kind and orgs capability.

Queued notify_primary_transfer jobs remain pending_integration; this slice adds
no mail adapter or worker claim path for them. Invitation workers remain unchanged.
Signed HTTP tests use production ES256 verification with synthetic JWKS transport
and actual runtime DB roles. They prove tenant transfer/recovery, current grants,
spoofed header/claim/body denials, recent authentication, bounded inputs/If-Match,
concurrent receipt replay, stale/blocked actors/targets, redacted/tampered status,
actual audit failure rollback/error sanitization/pool reuse and feature-off routes.
Domain tests separately exercise two-connection locks and suspension/removal races.
