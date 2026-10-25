# P02 completion evidence — partial identity/context/read milestone

Status: IN PROGRESS, approximately 38%. P02.1/P02.2 and this bounded P02.3 read
milestone passed local checks. P02.3 mutation authorization remains pending, as do
P02.4–P02.8. This report does not accept P02 or authorize P03 or deployed activation.
The earlier report is preserved below as historical evidence, not current scope.

## Current source identity

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- P02.1 source: b3d2d5c87b89fde996d03bc0ca8862c2d1437a1b; evidence 9a280f4913c037580841b5c2142a32ba1ad7fdb8.
- P02.2 source: c000e52c0b40ab2ca6c88838228939ffc2f9471d; evidence parent ab579bbd8a2f9ab4cb32c2c5f00c2eac300cd8b8.
- This implementation: ea805e5e7648c356ec8e428e692f9545c3245741, parent ab579bbd8a2f9ab4cb32c2c5f00c2eac300cd8b8.
- Branch: codex/p02-tenant-foundation; subsequent report-only commit contains this report.
- Exactly 22 source paths were selected and their staged/committed bytes verified.
  Unrelated untracked planning/reference attachments and work directories were left
  unstaged. No blanket add, reset, clean, deployment or app service mutation ran.

## Implemented scope and explicit remaining boundary

Explicit identity settings support the provider-user path or configured asymmetric
JWT verification (ES256/RS256), never HS/debug fallback or token-selected key URLs.
Verification yields identity fields, not user-metadata roles/capabilities. Pending
provider identities do not pass through the legacy approval lookup. Optional verified
authentication timing remains unknown when absent; account-wide last_sign_in_at is
not recent-auth proof. Actual project signing/claim semantics remain unverified.

Synthetic tests use real generated signatures and injected JWKS/provider transports.
They cover signature/issuer/audience/expiry/subject/session/algorithm/kid/claim failures,
rotation, synchronized cache, refresh cooldown, bounded body/encoding/redirect handling,
fresh-cache outage tolerance and stale-cache denial. HTTP phase/read-loop bounds are
not an OS guarantee for a blocked resolver. Cached JWTs do not immediately detect
provider logout. Provider/JWKS timeout injection is not a live outage benchmark.

Frozen RequestContext pairs VerifiedIdentity with a server-selected enum scope and
optional organization UUID. It carries no grants. Fixed parameterized set_config
calls bind actor, scope, org and known auth timing locally to the checked-out
transaction. Actual pool-size-one tests reuse the same PostgreSQL backend PID after
commit, Python error, SQL error, raised CancelledError and actual statement timeout.
The next actor/org sees cleared settings; no SET ROLE/session-persistent GUC is used.
Raised cancellation is not an HTTP-disconnect transport proof. DB credentials remain
a trusted server boundary; arbitrary credentials/SQL cannot be made safe by GUCs.

Revision p0204_read_rls grants scoped SELECT on seven identity/tenant relations,
with restricted user/capability columns. Six boolean entry points execute as the
trusted migration owner with fixed pg_catalog,wpl search_path and qualified objects
so private lookups do not recurse through RLS. Internal helpers and trigger functions
remain private; worker receives no added authority. Application role remains a
non-owner without superuser/BYPASSRLS/role-creation/schema-creation privileges.

Active tenant admins see all own cohorts; instructors require active assignment and
matching organization role; students see own membership/roles/assignments. Multi-role
instructors do not gain instructor roster access from a student assignment. Current
global/member suspension denies new protected reads. Directory executives require
explicit unexpired capability in platform scope, not tenant impersonation. Recovery
metadata requires explicit recovery capability plus target org; no recovery mutation
exists yet. Missing/malformed actor/scope/org settings fail closed. Email and grantor/
reason columns remain outside the new read grants. Secret payloads and migration maps
remain inaccessible to the runtime; queue/mutation grants are still later work.

Revision p0205_identity_mirror adds only INSERT(id) for the verified actor's own new
pending user mirror, and tenant page indexes. No approval, role grant, email matching
or identity remapping occurs. The SELECT helper accepts the proposed own UUID during
ON CONFLICT (id) DO NOTHING rather than requiring the row to already exist. Direct
runtime and HTTP regressions prove first/repeat insertion, one pending mirror, and
other-subject/approval denials. No privilege was widened to fix first insertion.

One shared internal /v1 router is mounted by the independent enabled factory with
explicit settings and injected fixture HTTP transport; no request chooses a transport
or bypasses verification. It implements GET /me, /orgs/{o}, /orgs/{o}/members and
/orgs/{o}/cohorts. /me returns own status, bounded memberships and effective capability
summary even when pending/blocked. Members is the P02 admin-only transfer-selection
read, not the full P05 instructor directory. Non-admin detail omits contact and primary
member fields. All protected reads bind trusted context and apply current DB checks
plus production RLS. Tests send real signed tokens through the production verifier,
factory/router and actual wpl_app DB connection; spoofed actor/role/org headers grant
nothing. Lists use limit 1..100 and (created_at,id) cursors; invalid inputs are bounded.

Shared errors are {code,message,request_id,field_errors?}, with server-generated
request IDs, no-store and sanitized identity/database failures. 401/403/404/400/422/503
paths and pool cleanup are tested. Public /api/v1 maps to internal /v1 in the existing
nginx source. The test snapshots/inspects that non-secret template and exercises
internal routes; it does not run nginx or claim a browser/proxy smoke. Legacy main,
SQLite configuration/startup and original routes are unchanged; disabled independent
factory exposes no versioned business routes or identity/DB requirements. Conditional
mounting into legacy activation must reuse this router in a subsequent bounded slice.

The original P02.2 FK test still temporarily grants narrow fixture policies/writes so
constraints can be exercised under wpl_app. It restores prior production read grants
in finally. That constraint evidence is not positive production mutation authorization
proof. The read RLS matrix itself uses production policies with no temporary grants.
Owner-session domain tests remain application-policy/invariant proof, not runtime RLS
mutation proof. Tenant mutations, service runtime UOWs and API write comparisons are
still required before calling P02.3 complete. Jobs/outbox/encryption/key-provider,
provisioning/transfer/recovery HTTP, frontend, import rehearsal and file primitives
remain required P02.4–P02.8 work; existing schemas/dependency probes do not implement them.

## Actual execution and counts

Developer ran (from /tmp):

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-NIG8X6k4/P02.3-read-full-checks.log
Raw log SHA256: 2e4b828ac6eed24f63c1f4f9c5c951e09d204f123484ec5ad2dc28f311367934.
The recorder checked the log hash, observed counts, final mandatory pass, build/lint,
recreated-target smoke, removed resource IDs, source bytes and prior report hash.
These execution-specific counts record evidence, not hardcoded suite pass targets.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner failure/isolation/discovery | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Frontend registered tests, four modules | 46 |
| Foundation, eight modules | 83 |
| Total | 180 |

No mandatory suite skipped. Foundation breakdown: 8 context, 3 configuration/import,
6 DB/migration/role, 9 guards/races, 10 HTTP, 20 identity, 13 read RLS/mirror and 6
schema plus 8 owner-session domain service tests. Recreated-target migration/runtime
smoke passed separately and is not counted as an extra test case. Focused repetitions
are not added to 180. Production build passed; npm ci installed 170 locked packages.
Lint passed with 0 errors and the same 2 loadGitStatus dependency warnings in
App.tsx:1159/1165. Bundle JS: 801.77 kB, gzip 215.19 kB; >500 kB chunk warning remains.
Starlette's httpx TestClient deprecation remains visible; no warning was suppressed.

Two intermediate failures were retained as development evidence, each with owned
cleanup: (1) read-RLS test reused a teacher membership still suspended by its preceding
subcase; setup now restores it before the global-suspension baseline check; (2) first
/me insertion failed because ON CONFLICT's proposed-row SELECT check could not pass
an existence-dependent permission helper. Its predicate and same-statement regression
were corrected without added privileges. Final focused 83 and full 180 passed.

## Runtime, dependencies, roles and isolation evidence

- PostgreSQL 17.11, postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
- Psycopg 3.3.6, binary implementation; actual DB wpl_fixture, actual role wpl_app.
- Test Python 3.14.8, base python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4.
- New check image wpl-p01-checks:0a284cb1047ecf5f, ID sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
- Node 22 pinned ID sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.
- Added pinned PyJWT[crypto] 2.15.1, cryptography 50.0.2, cffi 2.1.1, pycparser 3.0.
  Binary-only install succeeded; offline ES256/AES-GCM capability probe passed.
  That probe is not actual invitation encryption or KMS/key-provider integration.
- wpl_migrator owns wpl. Actual pg_roles assertions show wpl_app/wpl_worker have
  false superuser/BYPASSRLS/create-db/create-role/replication attributes. Runtime
  DDL, owner-role escalation, ledger access and owner runtime use were denied.
- Competing real migration runner waited on advisory lock; fresh/repeat/concurrent,
  disposable downgrade/reupgrade and recreated-schema migration all passed.
- Final DB container 0cd249f237f4b89d08e75e92b22c35c9d849a8e0eb7129f2e82ed1eb7efae2bc;
  final internal network 44100c0e7a93d8eca8467b5ac63c6be2f5d20a5f188b3b8e04bdbbedf0bf4dd9.
  Both were inspected and removed by ownership-checked exact ID; tmpfs data discarded.
- Fixture DB has no published port or host data/socket mount. Tests get only an
  allowlisted read-only source snapshot, synthetic env and their internal network.
  The legacy regression group stays network-none. No private .env/database/work is
  copied into test snapshots. No app/student image or running service was rebuilt.
- Failed/timeout/missing/empty/skipped suite contracts return nonzero and retain
  owned cleanup; Docker response mocks in runner tests are distinguished from actual
  fixture cleanup and actual DB statement cancellation. No prune/global cleanup ran.

Configuration names introduced/documented: WPL_AUTH_MODE, WPL_AUTH_PROVIDER_URL,
WPL_AUTH_PUBLISHABLE_KEY, WPL_AUTH_ISSUER, WPL_AUTH_AUDIENCE, WPL_AUTH_JWKS_URL,
WPL_AUTH_ALGORITHMS. Existing explicit foundation application/migration URL and enable
settings remain separate from legacy SQLite. No credential values are recorded.
No real provider/account, private env, live DB or original labs.wibyte.in was changed.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 180 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented HTTP identity/read surfaces, pending own /me, invalid identity/errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PARTIAL: actual two-org/multi-role read DB+HTTP matrix and denied writes; positive scoped mutation policies pending. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented new reads: current user/member suspension blocks cached-token requests; epoch guard tests retained. |
| T13 | PENDING transactional executive provisioning/invite/outbox workflow. |
| T14 | PENDING org operation idempotency/concurrency; identity mirror repeat is not this criterion. |
| T15 | PARTIAL DB/owner-session service guards pass; future write RLS/API paths pending. |
| T16 | PARTIAL DB races/service version/confirmation/recent-auth pass; runtime mutation/API pending. |
| T17 | PASS DB active-primary and audited security-recovery invariants; recovery API pending. |
| T18 | PARTIAL DB final-instructor races and actual read assignment matrix pass; scoped mutation paths pending. |
| T19 | PENDING explicit reasoned/audited recovery mutation; scoped metadata read alone is insufficient. |
| T20 | PENDING durable business/outbox transaction and worker restart proof. |
| T21 | PENDING competing workers, lease generation/fake-effect dedup. |
| T22 | PENDING retry/dead-letter/worker actor recheck. |
| T23 | PENDING actual encrypted delivery payload/key-provider and full redaction workflow. |
| T24 | PENDING foundation frontend vertical slice. |
| T25 | PARTIAL HTTP spoofing/pending/cross-org denial passes; frontend/deep-link UI pending. |
| T26 | PASS bounded source/internal-route prefix contract; no running proxy/browser smoke. |
| T27 | PENDING explicit fixture SQLite dry-run and historical populated-chain proof. |
| T28 | PENDING disposable import/count/ID/repository-map idempotency and negative matrix. |
| T29 | PENDING imported fixture token encryption and explicit personal/mapping preservation. |
| T30 | PENDING wired safe file primitives and negative cases. |
| T31 | PENDING atomic replacement and ordinary file behavior proof. |
| T32 | PENDING actual general-file-route primitive wiring; prior FormData/auth checks retained. |
| T33 | PASS current snapshot/owned isolated Postgres fixtures; later new modules must register. |
| T34 | PASS current local mandatory groups/discovery/frontend policy; remote Actions UNVERIFIED. |
| T35 | PASS implemented failure/timeout/cleanup contracts and actual cleanup; no app service mutation. |

## Remaining review and activation boundaries

Next: finish P02.3 tenant mutation policies and actual-runtime service UOW proofs;
then P02.4 jobs/outbox/idempotency/encryption, P02.5 executive provisioning/transfer/
recovery API, P02.6 minimal gated UI/activation wiring, P02.7 fixture import rehearsal
and P02.8 safe file primitives. Re-run appropriate focused gates as each change lands,
then the full mandatory gate and update this report with actual final evidence.

Authenticated browser/provider smoke: NOT RUN (previously deferred by developer).
Remote Actions execution: UNVERIFIED; local execution is not a remote CI run.
Real project issuer/keys/claim timing/provider PG major/pool compatibility: UNVERIFIED.
Real email delivery, account grants, service rebuild/feature activation and original
labs.wibyte.in effects: NOT RUN. No live migration, export, backup or external writes.

Keep feature off and original SQLite/Docker lab intact. Local rollback is a reviewed
source revert; schema downgrade tests apply only to owned disposable fixtures.
No real academic-data deletion/down-migration is a normal rollback. Before actual
provider migration/grants/delivery/deployed activation, prepare target/rollback and
obtain applicable approval. Final architect review must inspect code, scoped writes,
worker fencing/effects, UI caller wiring, import/file behavior and final T01–T35 proof.
Stop after completing P02 for review before P03; this milestone is not acceptance.

## Exact implementation paths and source hashes

- backend/alembic_foundation/versions/p0204_read_rls.py — SHA256 ef1516d0a74b2cc8f84da0d5181a1b0d4d348ee0b82961ea11b6c5649b9f712f
- backend/alembic_foundation/versions/p0204_read_rls.sql — SHA256 6a2c5993e56118c97cefcc386ace837b954d37a6e804d91bd26ed30a91bf7128
- backend/alembic_foundation/versions/p0205_identity_mirror.py — SHA256 01d85d9ca81dc5732bb12b7d6fa04003de8cc740625d4474769a99a6e62d93e6
- backend/app/domains/authorization/context.py — SHA256 6fa9948a697f059a022dfcf98cf6b18038441bd5fa5cc2c67f8e4e5dac3cc4a7
- backend/app/domains/identity/settings.py — SHA256 afcc0e736d2243a732ae6d1049464fc9401fb6e05f751fded92575a952af9dbb
- backend/app/domains/identity/verification.py — SHA256 556a0668d6035803789d54292649dfeeb24b8b356977c1b96618ae25e9fbf240
- backend/app/foundation/api.py — SHA256 f0d1c1b53096227d35820336cc1d96cde2e99c2d9a533808afaa12a7b0a73410
- backend/app/foundation/app.py — SHA256 c864545171b26dbc5bdf93a787feb915d65303f236bbf112346414d81d269566
- backend/app/foundation/db.py — SHA256 e06da559c006f80243e4556ad29e0a4fd3744b2b74740afab6ea3ca690e24c22
- backend/requirements.txt — SHA256 fd422a1efeb05f443f753de600bb209cfef41fd0b3e3536844a4f768a0d1acc6
- backend/tests/foundation/test_context.py — SHA256 347403e53e71ce8c73bff806cb90fa32a73723818cb8b00b0e74fe6de15a7ca0
- backend/tests/foundation/test_database.py — SHA256 1afc0b2c189250b95e88a67015ac6a5ebc6b35207f853a035de796d48751b2c9
- backend/tests/foundation/test_guards.py — SHA256 24b2eb9e5071af2d6721957356e827b549922c9e4867b8a45a8404a74db78d2c
- backend/tests/foundation/test_http.py — SHA256 02a0e70b4b6fdb234c9a1abb41590476709c7af62fa84f680ab6553829a7616f
- backend/tests/foundation/test_identity.py — SHA256 cdad672ba6b602ecef62406b5faf3a220ea19a03402cd28fb2b8e33dced1cc3a
- backend/tests/foundation/test_read_rls.py — SHA256 5b35cf2dba2452118aa9d9b80e1c79c140369b174c77e7ae438a5912f537dce4
- backend/tests/foundation/test_schema.py — SHA256 ea36ca29e2fceee837bd91ed0b5b460629bfc66f9de72c9a432553e8acb0c6c7
- docs/development.md — SHA256 03fa77a37489e1e098d71fb55ab391319eb2c1d97352bfc667ba0183068fe61e
- scripts/Dockerfile.checks — SHA256 283c4a452533d772926de723f1db26a3f9d6f2035068cb206c07aa37431dce06
- scripts/check_foundation.py — SHA256 51c85e9686f0648bdcd79b6239029a57d522af0f7278f8bfd5a32526d1b30807
- scripts/check_local.py — SHA256 c691d3404f60d84a16fd0e726ab1cfc4619865e95b71ba55c12bc0cda49a6bdf
- scripts/test_check_foundation.py — SHA256 4fc142b17463c941e2e5d815df5a2bfeac9a42900d37a2df3fbc0d8198f3db10

## Prior P02.1/P02.2 report — historical snapshot

This preserved prior report describes earlier source/evidence. Its pending-state
statements are superseded by the current ledger above; remaining phase work is not
waived. Prior report SHA256 before this update: a4e6444f550f952f130459f9ed8e92e2f5afecd1c4469c69393afcb405715693.

<details>
<summary>Preserved previous checkpoint report</summary>

# P02 completion evidence — in progress through P02.2

Status: IN PROGRESS, approximately 25%. P02.1 and P02.2 local checkpoint gates
passed. P02.3–P02.8 remain required. This is not phase acceptance, runtime RLS/API
certification or approval for P03. Finish P02 and stop for review before P03.

## Current source and checkpoint identity

Accepted P01 baseline: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
P02.1 implementation: b3d2d5c87b89fde996d03bc0ca8862c2d1437a1b.
P02.1 evidence checkpoint: 9a280f4913c037580841b5c2142a32ba1ad7fdb8.
P02.2 implementation: c000e52c0b40ab2ca6c88838228939ffc2f9471d, parent 9a280f4913c037580841b5c2142a32ba1ad7fdb8.
Branch: codex/p02-tenant-foundation. The subsequent report-only commit records this
updated evidence. Existing unrelated untracked planning/attachments/work remain
preserved; only the explicit 17 implementation paths below were staged.

## P02.2 implemented scope

The private schema now has users, platform_roles, organizations,
organization_memberships, organization_roles, invitations, primary_admin_transfers,
cohorts, cohort_memberships, secret_payloads, jobs, outbox, idempotency_records,
audit_events and migration_mappings. UUIDs, bounded fields/statuses, versions/epochs,
UTC timestamps, composite same-org references and list/claim indexes are present.
A non-null deferred primary reference supports preallocated circular pending org /
membership / invitation creation without granting a pending member permissions.

Separate revisions p0202_tenant_schema and p0203_tenant_guards follow the unchanged
private-ledger root. SQL source is explicitly included in the test snapshot. The
migration regression discovers actual head rather than hardcoding the P02.1 revision.
The legacy four-revision SQLite chain remains unchanged and passed again.

All new application tables have RLS enabled and no implicit app/worker grants.
This is private default denial, not the completed scoped RLS policy. One constraint
test temporarily installs narrow disposable fixture policies/grants to let actual
wpl_app inserts reach the real foreign keys, proves a positive same-org insert and
five cross-org rejections, then removes those grants/policies in finally.

Parent updates serialize child changes, including repeatable-read transactions.
Deferred checks validate the final primary/instructor/invitation state; child-level
constraint triggers also check after mutations when a session requests immediate
constraints. Protected primary removal/demotion/suspension is rejected. Active orgs
need an accepted active admin whose global identity is active. Transfers require an
active same-org target and retain the former primary as admin. Active cohorts need
an active assigned instructor with the actual organization instructor role.

Global security blocking still succeeds. Affected active organizations and cohorts
losing their final eligible instructor enter audited recovery_required state. The
cohort recovery state is a justified bounded addition: it avoids preserving access
or refusing a security suspension merely to keep staffing active. Reactivation is
explicit; it does not silently activate organizations or restore provider sessions.

Initial shared domain policy reads active global/member/admin grants from the DB,
not identity metadata. Synchronous SQLAlchemy services lock/recheck permission and
parent versions, protect primary/final-instructor transitions, retain instructor
membership history, and append audit inside the caller transaction. Role, assignment
and status changes advance appropriate epochs. Typed VerifiedIdentity carries subject,
authentication time and optional identity fields without role/capability authority.
No verifier/debug-header/bypass switch or new HTTP endpoint exists at this checkpoint.

Primary completion checks current-primary authority, stored preview actor/scope,
version, expiry, constant-time confirmation-hash match, recent authentication and
eligible target. Fixture tests create the preview records; production preview HTTP,
executive recovery and notification outbox wiring remain P02.5/P02.4 work. An
administrative domain action is not a claim of email delivery or account activation.

## P02.2 actual execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-AXW88xTC/P02.2-full-checks.log
Log SHA256: b68465b27292985fff80c0da576d5f49cf29f12bf0b671896efe2f69d138ad3b.
Log was read/hashed during preparation; the user-executed recorder verifies hashes,
observed counts, stage/commit bytes and prior report again. These count assertions
record this execution; mandatory runtime outcome guards do not hardcode case counts.

| Group | Actual passes |
| --- | ---: |
| Runner failure/isolation | 20 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend | 46 across four modules |
| Foundation Postgres/configuration/schema/guards/services | 32 |
| Total | 126 |

All mandatory groups passed; no skipped mandatory cases. Production build and lint
passed. Foundation group: three configuration/import, six database, six schema,
nine invariant/race and eight domain service cases. Separate recreated-target
migration/runtime-role smoke passed. Earlier focused 15/24/32-case runs are not added
to the 126-case full-run total.

Actual races: one versioned transfer wins and the competing request conflicts;
transfer-versus-target-removal leaves a valid designated primary; concurrent final
instructor removals leave one instructor under READ COMMITTED and REPEATABLE READ.
Depending on isolation/interleaving, the losing mutation is rejected or serialized
out; no universal successful retry/progress guarantee is inferred from the fixture.
Services additionally proved clear protected-primary/last-instructor/stale-version
conflicts, actor/cross-org denials, transfer confirmation/recent-auth/expiry/eligibility,
role/assignment epoch changes, former-admin retention, history and audit rollback.
Service tests explicitly use fixture owner sessions to isolate application policy;
they do not replace the required P02.3 runtime-role RLS and API tests.

One intermediate 24-case guard run failed: a new early missing-primary guard rejected
an invalid cross-org reference as CheckViolation before the FK ran. Its missing-
reference SQLSTATE was corrected to 23503, preserving the existing exact FK test and
rejection. All 24 cases then passed; subsequent epoch/service additions passed all
32 focused and 126 full cases. The failed run returned nonzero and removed its owned
resources. No failed run is labelled a pass.

## Current runtime identities and isolation

Actual Postgres 17.11 / Psycopg 3.3.6 binary runtime remains the P02.1 pinned fixture.
Database image: postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Backend check image identity: sha256:cb9713f03d3d38e223b6ba76b1a5d8a46ad574537e06a7b2761867bc4b033a3e.
Node: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.
No dependency or application image changes were needed in P02.2. Provider major,
issuer/key configuration, region and actual pool capacity remain unverified.

Full-run internal network ID:
c6e5c9d8a4f9be265f41114c25957768fbb2b5936ba580beeefabe1b7d9d7cdb.
Full-run database container ID:
9b38e61b1dd3b32b9b9b1c0d59273484a468b8d38a81f29e3db33a21d88a30fd.
Both were ownership-inspected and removed. Database had no published port and only
tmpfs storage. Test containers had only the owned internal network and read-only
allowlisted source, no host Docker socket/private env/live data/provider credentials.
Actual role attributes/denied DDL/owner assumption/escalation passed again. Guard
SECURITY DEFINER functions have explicit qualified objects/safe search_path, no
arbitrary dynamic SQL and no public/app/worker direct EXECUTE grants.

## Current acceptance ledger and limits

This ledger supersedes the historical P02.1 statuses below. Checkpoint passes must
be repeated as later schema/policies/routes change; no partial phase is 100%.

| IDs | Current evidence / remaining work |
| --- | --- |
| T01 | Current 126-case gate/build/lint pass |
| T02 | Factory and all added domain imports pass with blocked socket/no legacy imports/files |
| T03 | Disabled construction and unchanged legacy source/regressions pass; future router integration pending |
| T04 | Actual-head fresh/repeat/concurrent/advisory/downgrade/recreate pass |
| T05 | Actual non-owner runtime/worker attributes and DDL/escalation denials pass; recheck future grants |
| T06 | Same-org schema constraints pass including actual wpl_app positive/negative writes |
| T07–T11 | Provider/JWT/JWKS, full policy/RLS/API and pooled trusted-context proofs pending P02.3 |
| T12 | Database/service suspension and epochs pass; protected HTTP/RLS request proof pending |
| T13–T14 | Pending schema shape/uniqueness present; provisioning/idempotency concurrency/effect workflow pending |
| T15 | Implemented DB and ordinary service primary paths pass; future API paths still require proof |
| T16 | DB races and domain version/confirmation/recent-auth/eligibility pass; preview/HTTP contract pending |
| T17 | DB accepted-primary activation/recovery invariant passes; executive status/recovery HTTP pending |
| T18 | DB staffing races and admin instructor-replacement service pass; full instructor-assignment policy pending |
| T19 | Executive recovery capability/reason/API proof pending P02.5 |
| T20–T22 | Queue/outbox schema exists; durable workers/idempotent effects/retries/rechecks pending P02.4 |
| T23 | Hash/ciphertext/reference schema and no transfer-confirmation audit leak pass; real encryption/workflow pending |
| T24–T26 | Foundation frontend and /v1 route/proxy contract pending |
| T27–T29 | SQLite fixture import/rehearsal tooling pending |
| T30–T32 | Safe workspace/file route work pending |
| T33–T35 | Current snapshot, mandatory group, strict outcomes and owned cleanup pass; extend with later work; remote CI unverified |

Ciphertext-shaped schema fixture bytes are not cryptographic encryption evidence.
No real invitation redemption, Resend delivery, identity activation, provider logout
revocation or executive HTTP bootstrap/recovery is claimed. Existing Legacy CurrentUser
and live SQLite/Docker lab remain unchanged. No private env/provider/original
labs.wibyte.in action was performed by these commands; no comprehensive private-state
comparison was requested or claimed.

Current full log: two existing App.tsx exhaustive-deps warnings at 1159/1165 and the
Starlette TestClient/httpx deprecation. Bundle remains 801.77 kB / 215.19 kB gzip;
the size warning was observed in prior runs, though this full log did not emit it.
Authenticated browser/provider smoke: NOT RUN. Real provider/email/DB migration:
NOT RUN. Remote Actions execution: UNVERIFIED. Disposable rollback remains dropping
only owned fixture resources; live academic-data downgrade is not authorized.

## Exact P02.2 implementation paths and SHA256

- backend/alembic_foundation/versions/p0202_tenant_schema.py — SHA256 c7199d38275f8c2cc9d7abc319b8358eb561ba6c33d3645a7085e21a90726453
- backend/alembic_foundation/versions/p0202_tenant_schema.sql — SHA256 a08cfc31c4000377881b279e0077d6c44adf4d1d5fdef12d17d4d58d64d5986a
- backend/alembic_foundation/versions/p0203_tenant_guards.py — SHA256 b057987ac50a52cbf4c404ca3f2bd963186c08a082b4e57a09f20d62b6b3679b
- backend/alembic_foundation/versions/p0203_tenant_guards.sql — SHA256 3571af25c69782265f83ae0441052fa9614f1cddbac29d0199e136001206486f
- backend/app/domains/__init__.py — SHA256 2380b3f64b5adfb5ae73e3483d7155364aec187d264fab081e3b662b4686be10
- backend/app/domains/authorization/policy.py — SHA256 2474b6cb9ec50c7597f3f037be2c3616411476cbc4d5a63dff8708e86a71eb6d
- backend/app/domains/cohorts/service.py — SHA256 9cac084c365ca6c96efc45ea3d4ae74f8ad2f3c501d308fef73d4de5cc86307c
- backend/app/domains/errors.py — SHA256 e59b0e0c1795b3076c1ced91fe6423b562a6a3813ccf25ac65cf1f40d3a11cc4
- backend/app/domains/identity/types.py — SHA256 b89523802bb235a0c3f9825f9d61bac7bed1fbb9745f9b94fe0020f996551c2c
- backend/app/domains/organizations/service.py — SHA256 fa8d01cdd4126e5c4ec9d6ea8a458bb8f8d6dc0bac0395bfa38f4ba3be75f179
- backend/tests/foundation/test_database.py — SHA256 4b2337e087a0b76683fb4c401d58d73490b6e347c68ec90e863390f63a679cd2
- backend/tests/foundation/test_guards.py — SHA256 bcdfed680ae6376a60d080fe0ec5c78c8c365b8b71e475ecdf2a846d4fc13cf6
- backend/tests/foundation/test_schema.py — SHA256 ca51cc570ca2d3cba84b3ea4fd438aa70cfcdd4830e56973984a86c50c8ba0b8
- backend/tests/foundation/test_services.py — SHA256 39cc14d31350674d7bcbc4664918731e051b436ed1f69875b64c65b3257a2177
- docs/development.md — SHA256 8e605446b1259d4b815816b6c2ad91d38e93d9e3041b2d25f0290d082f076460
- scripts/check_foundation.py — SHA256 1983330ad40c5a064dd813ab05b702b14e0eb6025851e88fc9b72652d1e77c17
- scripts/check_local.py — SHA256 31bf32ba675da9a3523ffe1db9e477852663aabb1b6a6aa629fbcd79435dc24e

## Preserved P02.1 checkpoint record

The following is historical evidence from before P02.2. Its earlier scope/status
statements are superseded by the current ledger above. Original report SHA256 before
this update: f7be324dcaec71ccf766c3d2f1fc5db3e06583da76df0569270df155fb9fe0cd. Git history at 9a280f4913c037580841b5c2142a32ba1ad7fdb8 retains the original bytes.

### Source identity and scope

Accepted predecessor: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
P02.1 implementation commit: b3d2d5c87b89fde996d03bc0ca8862c2d1437a1b on codex/p02-tenant-foundation.
The report is recorded in the subsequent report-only checkpoint commit.
Only explicit intended paths were staged. Existing untracked planning documents,
source attachments and work material were retained. No reset/clean or blanket add.

Implemented: separate explicit foundation settings, bounded sync SQLAlchemy pool,
independent factory, owner-only explicit Alembic runner with transaction advisory
lock/private version ledger, disposable Postgres harness and mandatory local/CI
entry-point wiring. The original SQLite config/engine/migration chain/startup were
not edited. The independent app has no business endpoints at this checkpoint;
legacy feature/router activation remains later P02 work. No tenant/RLS claim follows
from establishing a private schema and non-owner roles alone.

### Actual execution evidence

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Output retained locally at /home/wibyte/wibyte-python-lab/work/p02-evidence-9eMNdKf1/P02.1-full-checks.log.
Log SHA256: 2862786d3b3789c7fdac3dea5029b08c041d2012f99672143b589de8d19c309d.
The log was read/hashed when preparing this record; counts and source hashes were
checked again by this user-executed recorder. Counts are evidence assertions here,
not hardcoded expected test counts in the mandatory runner.

| Group | Actual passing cases |
| --- | ---: |
| Runner failure/isolation | 20 |
| Legacy setup | 16 |
| Legacy backend/idle | 12 |
| Registered frontend contracts | 46 across four modules |
| Real Postgres/configuration | 9 |
| Total | 103 |

All mandatory groups passed without skipped cases. Production tsc/Vite build and
ESLint passed. Recreated-target migration/runtime-role smoke passed separately from
the nine unittest cases. Earlier focused runs: 20 runner contracts, then nine real
Postgres/configuration cases and recreated-target smoke. Do not add focused/repeated
runs to the 103-case full-run total. Synthetic negative fixtures deliberately reject
failures/skips/timeouts; these do not constitute failed/skipped mandatory outer cases.

The first two startup attempts failed before migration/role tests. Server sockets
were configured at /tmp while entrypoint psql selected its default socket location;
a PGHOST workaround was ineffective because the pinned entrypoint explicitly clears
PGHOST/PGHOSTADDR (verified with a developer-run read-only image script inspection).
The final fixture mounts tmpfs at /var/run/postgresql and aligns server/readiness/
bootstrap clients. Both failed attempts removed their owned database/network and
returned nonzero. Missing /tmp preparation artifacts were regenerated in a persistent
workspace artifact folder; no application implementation was applied by that repair.

### Database/runtime identities and isolation

Actual server: PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2), Linux amd64.
Pinned database image: postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Major/version is provisional pending actual provider compatibility before activation.
Driver pins: psycopg[binary]==3.3.6 and psycopg-binary==3.3.6.
Developer-run binary probe reported Python 3.14.8, SQLAlchemy 2.0.54,
Psycopg 3.3.6, binary implementation, libpq 180006. Host Python version is separate.
Backend check image: wpl-p01-checks:5283d8a9918e5efe,
sha256:cb9713f03d3d38e223b6ba76b1a5d8a46ad574537e06a7b2761867bc4b033a3e.
Pinned Node identity: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.
No application image tag was used as a build/test output target.

Bootstrap superuser stays inside the fixture DB container. wpl_migrator owns wpl;
wpl_app and wpl_worker have no schema/database ownership, superuser, BYPASSRLS,
create-db, create-role or replication privileges. Actual SQL verified attributes,
owner and denials of schema/table DDL, owner-role assumption, privilege escalation
and version-ledger reads. The app guard rejects the owner identity. Transaction
commit, application exception rollback, SQL-error rollback and timeout settings
passed against the real pool. Actor/org RLS context is not implemented yet.

Fresh/repeated/concurrent migrations passed. A held advisory lock made a competing
runner visibly wait in actual pg_stat_activity; then the runner completed. Disposable
downgrade/re-upgrade and explicit owned schema recreation passed. No app import or
factory construction applied DDL or connected; subprocess tests blocked socket
connections and verified no legacy config/main/engine/Docker imports or DB files.

Full-run owned network ID:
c00a78839763282c6afc4ff9b19f00a0189fdc463c4090b7d19b83263d6bb754.
Full-run owned database container ID:
73ad6e8cf8ddec57573a7bdf77db96b43143f57bfc6ee5c239554a5a2652ce17.
Both were inspected for ownership and removed. Tests ran on an internal Docker
network, no published DB port, tmpfs-only DB storage, clean synthetic env and
allowlisted read-only source, without host socket/private env/data mounts. Test
containers used --rm; owned-ID cleanup was checked afterward. Failure/timeout/foreign
owner contracts use mocked Docker responses; actual startup failures and passing
fixtures supply separate actual cleanup evidence. No live failure was injected.

### Configuration and remaining gates

New setting names: WPL_FOUNDATION_ENABLED (default false),
WPL_APPLICATION_DATABASE_URL (runtime only), WPL_MIGRATION_DATABASE_URL (tool only).
WPL_WORKER_DATABASE_URL currently exists as synthetic role-test input only.
No dotenv fallback; missing new settings do not affect disabled legacy operation.
Real settings, provider mode/JWKS, keys, worker wiring and activation remain pending.
No private env edits, live migrations, provider calls, service restart, student image
rebuild or operation targeting the original labs.wibyte.in was performed by these
commands. No comprehensive private-state comparison was performed or claimed.

| Criteria | Current evidence/status |
| --- | --- |
| T01 | Checkpoint full regressions/build/lint pass; repeat after later changes |
| T02 | Independent factory imports pass; future domain imports still pending |
| T03 | Disabled settings/factory proven; legacy untouched source/regressions; later router integration pending |
| T04 | Private-ledger fresh/repeat/concurrent/lock/rollback/recreate pass at current revision; repeat after schema additions |
| T05 | Actual current role ownership/attributes/denials pass; reassess after grants/helpers are added |
| T06–T32 | NOT IMPLEMENTED/NOT RUN; remain required phase work |
| T33 | Current new modules/migrations/tests are included; actual internal fixture isolation passes; extend with future files |
| T34 | Mandatory local group wired to existing CI command; local run passed; remote Actions UNVERIFIED |
| T35 | Current mocked failure/timeout/foreign-owner plus actual startup-failure/normal cleanup evidence; extend for remaining operations |

Remaining warnings: App.tsx lines 1159/1165 loadGitStatus exhaustive-deps warnings;
Vite chunk warning (801.77 kB minified, 215.19 kB gzip); Starlette TestClient/httpx
deprecation. The earlier dependency build also emitted Docker legacy-builder and
pip-as-root notices. No warning suppression or unrelated dependency sweep.
Authenticated browser/provider smoke: NOT RUN. Real email/provider execution:
NOT RUN. Real Supabase compatibility/schema/identity configuration: UNVERIFIED.
Remote Actions execution: UNVERIFIED; local source wiring is separate evidence.

Disposable rollback is ownership-checked removal of the fixture containers/network;
tmpfs data disappears. Legacy mode remains the working system. This is not a live
academic-data downgrade/rollback plan. No phase beyond P02 is authorized here.

### Exact implementation paths and hashes

- backend/alembic_foundation.ini — SHA256 8ed5e6615a40ffa22b7a7867c7567d8b24f776439cc462442a4d4d147834dc99
- backend/alembic_foundation/env.py — SHA256 1e3336e994d953e312637ec2fd1d6ba23e6d9cd862833d0551b423f70b02aa51
- backend/alembic_foundation/versions/p0201_private_schema.py — SHA256 29aa7955f4d239deccbb9dd8fd4d92159f4c5a60b794e3e1bf03565f98428f1b
- backend/app/foundation/__init__.py — SHA256 7edfa0ddbaf83ff1e688b5776ee160f340a49988884ee95ae559be9dd0efabeb
- backend/app/foundation/app.py — SHA256 bd8e3ae3b927f4fa8153d8b25c70721c0b1c0941419a5730a181b19d99b5e03b
- backend/app/foundation/db.py — SHA256 554057f6eca70af20094d135b0afa8217e8f065643303bb06fb512565b21d038
- backend/app/foundation/migrate.py — SHA256 0338c1a14044e69c6a7105aaca56c49ef4eac3db891a008c369b7b82784c9ad8
- backend/app/foundation/settings.py — SHA256 78efdb8011e4aa3de1e449fcf6561635c76b48b57ff02a828c5dfe44d017985c
- backend/requirements.txt — SHA256 5f7c97653d806bc1dae0c6e178f386d62686c5d5b0ec69019c6660bfe900dd79
- backend/tests/foundation/test_database.py — SHA256 3c4e301af1137cf2c3eca465f05d0a848b013b252fc315a1e8e72d87d7e9908d
- docs/development.md — SHA256 f8b6799b75d9d9dad376d7185210e1d8968f34b97a995393d550ac414953fa44
- scripts/check_foundation.py — SHA256 c07a73708e23eb01762500c89e6f7d1e6ae3d73eb49b3b61bff02d88e0f4f584
- scripts/check_local.py — SHA256 45fb9ad481fe4653701699a8e598b3ef0ecabe49d9295456c603c916fc49282a
- scripts/migrate_foundation.py — SHA256 99c224e817e7cd5d577051dcc12e867f3bdf336c6797ade6330938b9be087f27
- scripts/test_check_foundation.py — SHA256 9db6bd94312fe62e7a6be2ad86f03e90015bce6f55f5221a31dfa7d27119a253

</details>
