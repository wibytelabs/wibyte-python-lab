# P02 completion evidence — protected snapshot and disposable import rehearsal

Status: IN PROGRESS, approximately 86%. P02.7 now has explicit protected-snapshot
dry run, historical archival compatibility and confirmed owned-fixture personal
import with encrypted credentials and reconciliation. P02.8 safe general-file
primitives and final architect review remain required. Do not advance to P03.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous shared-router/UI implementation: 416d2e482d1ce6c5cc0effaf4f8efc4fe610e742.
- Parent/report: b3b71f44d8034448170450cf6dbdcd4477dbdf4e.
- Migration rehearsal implementation: 2f3e9e58151bc27dcd46e9067fbf35fd0be961a7; branch codex/p02-tenant-foundation.
- Exactly 15 intended implementation paths are listed with hashes below. A separate
  report-only commit preserves prior evidence; unrelated documents/work remain unstaged.

## Implemented behavior and actual proof

The offline snapshot inspector has no default source, target connection, dotenv,
legacy ORM/config/main import, provider request or workspace-file export. It requires
an explicit absolute *.snapshot.sqlite3 private regular copy, matching SHA256,
current ownership, no group/other access, one link, no final symlink/sidecar and a
64 MiB bound. It reads with no-follow descriptors, checks file stability and exact
bytes, then deserializes into an in-memory query-only SQLite connection with trusted
schema disabled and bounded SQL work, rows and text. Nothing opens the source for
writing. Public output contains counts/checksums/policy, never profile/token/repo/
container values. Private row state has redacted repr and immutable scalar mappings.

The inspector validates integrity, known tables/columns, current or explicitly
supported historical revision, nonzero canonical UUIDs, timestamps, required fields,
FKs/owner relationships, numeric GitHub identifiers and repository owner/name/fullname
consistency. Orphans, cross-owner lab/repository bindings, unknown executable schema,
duplicated repository/provider identity or unsupported partial revisions fail with
fixed redacted codes. Stable source-kind/UUID target maps retain original IDs and
personal owner/repository references. Profile emails are retained only as data; even
duplicate emails never merge identities or infer an institution.

Generated fixtures run the unchanged legacy revision bodies through Alembic
Operations, bypassing legacy dotenv/config. The empty chain reaches existing head
7d8e63fb45c3 before synthetic population. A separate actual populated 553a7ddf4183
fixture proves that unchanged 3e58a6eb699a NOT NULL refresh-token/expiry additions
fail without defaults. The historical source is neither upgraded nor stamped.
Default inspection rejects it. Only explicit archive_for_reauthorization permits
that exact older schema to be read directly, retaining its original revision and
absent profile/refresh/expiry fields. Unsupported/partial schemas still fail. No
missing token or usable expiry is invented, and old credentials cannot become active.
This avoids modifying historical migrations or pretending a populated upgrade passed.

Revision p0219 introduces private RLS-enabled legacy_import_runs and
legacy_import_artifacts, without app/worker grants. The immutable journal/archive
holds source/revision/checksum/intent, stable target IDs, original owners and repo
references, optional explicit existing auth UUID references, private metadata and
credential envelopes. Same-namespace owner/repository FKs retain referential identity.
Only personal scope exists; no organization assignment or runtime activation is
available. Existing migration_mappings records imported references/checksums.

This is a bounded P02 archival bridge because P03's replacement personal runtime
and repository/storage model is not implemented here. It proves fixture import,
counts and mappings without switching the working lab or fabricating new institution
rows. Archived container references are metadata, never resumed or executed. No
workspace code/file contents are read or exported. The architect should review this
explicit scope choice before a later real migration or P03 consumption; this is not
an import into an already activated replacement lab domain.

Import requires explicit confirmation flag and matching source checksum, target URL,
fixture ownership nonce, source namespace, reason, private 32-byte key file and key
reference. Optional private JSON maps canonical source student UUIDs to distinct
existing auth UUIDs. Unknown source/target IDs or many-to-one mappings fail; missing
bindings remain unresolved personal archive owners. Binding neither creates nor
approves users nor grants membership/roles. Actual pending-state and no-membership
assertions pass after an explicit binding. No email-only auth remap is present.

The tool accepts only fixture-db / wpl_fixture / wpl_migrator. It verifies actual
connected role/database, non-super/non-BYPASSRLS schema ownership and the database
comment matching the explicit run nonce. The fixture runner sets that comment and
passes only its synthetic ownership nonce. Production/remote targets and env-default
URLs are unsupported. This marker is an accidental-target safeguard in addition to
the constrained fixture endpoint, not a general authorization boundary against a
schema/database owner deliberately constructing another target.

Credential material is encrypted by the existing AES-256-GCM component before a
target connection or transaction. AAD binds the personal archive owner, namespace
operation, target artifact, purpose and recorded key reference. Tokens and expiry
values are excluded from metadata/public output. All imported credential records,
including current-head ones, remain reauthorization_required. Historical missing
refresh/expiry fields remain absent inside the envelope. Explicit key and mapping
files require private regular owner-only/no-follow/one-link/bounded stable reads;
no missing/wrong-key fallback or provider call exists. Replaying preparation can
resolve/encrypt again, so the explicit archive key remains a prerequisite; no claim
of key-outage import replay is made.

Namespace advisory locking serializes competing imports. An identical committed
source/binding/reason request replays after a new connection/pool and reconciles
against the original archive/ciphertext, despite a fresh preparation nonce. Changed
source, binding or reason conflicts. Source UUIDs, target IDs, owner/repo references,
metadata/source checksums, mapping states/counts and stored archive digest must match
before success. Corruption is rejected, not silently repaired. Run, artifacts and
mappings share one transaction/savepoint, including caught real mapping CHECK failure
and outer rollback. CLI prints success only after its outer connection context commits.
App and worker cannot read the archive; actual immutable-row and secret-metadata
CHECK denials pass. No normal runtime authorization uses the archive.

Thirty-one new mandatory cases cover 12 snapshot, 6 historical and 13 actual
Postgres import cases. Proof includes source bytes/mtime and disposable target-count
preservation, real historical failure/explicit compatibility, unsafe input rejection,
ambiguity/orphans, stable maps, encrypted round trip, explicit identity binding,
new-pool/concurrent idempotency, real SQL/outer rollback, corruption rejection,
role/marker/confirmation denial and actual CLI dry-run/import/replay from /tmp.
Earlier mandatory factory/import, legacy app, RLS, worker and real frontend contracts
remain unchanged and pass. No new dependency or runtime image was needed.

## Full execution evidence

User-run command from /tmp after exact candidate-source verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  /home/wibyte/wibyte-python-lab/scripts/check_local.py
```

Raw full-gate log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-iGAM92xY/P02.7-migration-full-checks.log

Raw log SHA256: 3721e2a8541e79483ca565060b62de03da6dfed53048ab3211de94f5bf56eaea

| Mandatory group | Actual result |
| --- | --- |
| Runner failure/isolation contracts | 23 passed in 0.538s |
| Setup regressions | 16 passed in 0.248s |
| Legacy backend/idle regressions | 12 passed in 22.624s |
| Frontend strict contracts | 96 passed across 8 declared modules; no fail/cancel/skip/TODO |
| Disposable Postgres foundation | 251 passed across 27 declared modules in 91.195s; no skips |
| Total registered cases | 398 passed; focused runs below are not added again |
| Recreated-target migration/runtime role smoke | Passed |
| Locked frontend install/build/lint | Passed; 0 lint errors, 2 existing warnings |

Build remains 101 modules: CSS 27.50 kB / 6.24 kB gzip; JS 842.81 kB / 225.81 kB
gzip, with Vite's >500 kB warning. Existing App.tsx:1161/1167 loadGitStatus dependency
warnings and Starlette/httpx TestClient deprecation remain. No suppression, dependency
upgrade or frontend source change was made in this checkpoint.

## Runtime, isolation and cleanup

PostgreSQL 17.11 image remains
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture wpl_app / wpl_fixture, Psycopg 3.3.6 binary; worker role wpl_worker;
private schema owner wpl_migrator, separate from non-owner runtime identities.
The import tool's explicitly permitted migrator role is a rehearsal-tool boundary,
not owner-runtime RLS proof. App/worker denial is tested under their actual roles.
Check image: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node image: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned database container:
2523e579a79e7fef98056a0c4a550656157804a13d2e8d74c0d0ee41a51ac945.
Final owned internal network:
4a61c1b34be2528d2a57ab32c50c7cb15b61614787ef0a32daa6cd7091ee9f37.
Both were inspected and removed by exact owned ID; tmpfs data, including imported
archives, was discarded. Generated SQLite/key/mapping fixtures lived only in owned
temporary directories. Isolation verification retained internal network/no published
ports/tmpfs/no host socket/data mount, read-only allowlisted source and synthetic
settings. Legacy tests retain network-none. CLI target credentials are synthetic,
confined to the disposable fixture and never included in report output.

No live SQLite backup/export/read/import, private env, student files, configured
provider account, real token, original labs.wibyte.in, deployment flag, service restart,
application/student image rebuild or global prune was targeted. Source/domain imports
retain socket-blocked no-legacy-config proof. Disposable fixture teardown/downgrade
is not a rollback plan for real academic data.

## Focused execution provenance (not additional full-gate cases)

- Protected snapshot dry run: 232 unit/foundation cases; /home/wibyte/wibyte-python-lab/work/p02-snapshot-evidence-RnRsMeqS/snapshot-checks.log; raw SHA256 1d563700e43adea1c522621e701e22db7bafbad663ddd4766cd88ed7bbf7b27d.
- Explicit historical archival compatibility: 238 unit/foundation cases; /home/wibyte/wibyte-python-lab/work/p02-historical-evidence-Z5wHXFEp/historical-checks.log; raw SHA256 31587fa85f5fae45bf2a0316f0e40040da2de59c2689c83a382e1fa29e095eb5.
- Confirmed disposable personal import: 251 unit/foundation cases; /home/wibyte/wibyte-python-lab/work/p02-import-evidence-yUjrqT4k/import-checks.log; raw SHA256 bb227ccf773a7a9a0486d2c7938e3611c98e9210940b8de09593264f76317b89.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 398 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS socket-blocked foundation factory/domain/mount imports and no legacy DB side effects; actual legacy-main composition tested separately with synthetic adapters. |
| T03 | PASS actual main default/explicit off and dotenv-only nonactivation, legacy SQLite/health/auth/CORS retained; explicit process-on shares the same router with bounded lifecycle cleanup. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented identity/read, provisioning, protected transfer and separate executive recovery HTTP, pending own /me and sanitized stable errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS implemented tenant/executive/provisioning plus primary/recovery runtime and signed HTTP scope matrix; no client actor/scope authority. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented reads/current capability revocation plus executive org status/epoch/audit and tenant access suspension/resume; no immediate provider-logout claim. |
| T13 | PASS atomic executive creation of one pending organization/designated invitation membership, encrypted intent, outbox, audit and receipt; no email binding or activation. |
| T14 | PASS actual concurrent same-actor/key/body DB and signed HTTP creation, changed-body conflict, actor namespaces, new-pool replay and current authority recheck. |
| T15 | PASS ordinary runtime services/direct SQL deny primary removal/demotion/suspension; protected transfer/recovery HTTP use separate confirmed paths and no direct designation grants. |
| T16 | PASS actual app-role concurrent confirmations, version/target/confirmation/recent-auth checks, transfer/removal and target-global-suspension locks; signed HTTP replay matches one committed change. |
| T17 | PASS active-primary/security-recovery invariants and explicit recovery HTTP restoring active org while preserving old global block and retained admin membership. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PASS explicit targeted recovery capability, current expiry/revocation checks, stored reason, recent confirmation and atomic recovery audit/notification intent; no self-bootstrap. |
| T20 | PASS implemented invitation pipelines plus confirmed primary changes with atomic business/receipt/audit/job/outbox, caught failure rollback and new-pool replay; notification jobs remain pending integration. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented invitation/confirmation redaction plus bound AES-GCM fixture-token archive, explicit keys before target transactions and app/worker archive denial; imported credentials remain disabled for reauthorization. |
| T24 | PASS local real-client/controller and actual TSX/SSR identity, directory/provision/detail/job and protected transfer/recovery contracts; truthful queued/activation state. Browser/provider smoke NOT RUN. |
| T25 | PASS local pending/non-executive/account-change/deep-link UI contracts plus existing actual signed HTTP tampering/RLS denials; no client grant. Browser interaction smoke NOT RUN. |
| T26 | PASS production P01 client public /api/v1 joining and actual conditional /v1 child mount/internal routes; running nginx/browser smoke NOT RUN. |
| T27 | PASS explicit protected-snapshot dry run preserves source bytes/mtime and actual target counts; unchanged populated historical migration failure proved and handled by explicit old-revision archival read with unknown expiry retained. |
| T28 | PASS confirmed owned-disposable private personal archive import with reconciled counts/UUID/owner/repo maps, concurrent/new-connection idempotency and ambiguity/orphan/conflict/corruption/rollback denials; no activated P03 runtime import. |
| T29 | PASS imported fixture tokens encrypted and disabled, personal scope retained, existing UUID bindings explicit/distinct with no user approval or invented memberships/institution/email remap. |
| T30 | PENDING wired safe file primitives and negative cases. |
| T31 | PENDING atomic replacement and ordinary file behavior proof. |
| T32 | PENDING actual general-file-route primitive wiring; prior FormData/auth checks retained. |
| T33 | PASS current CLI/domain/migration/test/helper snapshot and owned internal Postgres fixture, including explicit synthetic rehearsal ownership marker; extend for file primitives. |
| T34 | PASS current local mandatory 96 frontend cases/8 modules and 251 foundation cases/27 modules with strict discovery/outcome policy; remote Actions UNVERIFIED. |
| T35 | PASS implemented failure/timeout/cleanup contracts and actual cleanup; no app service mutation. |

## Remaining work and review limits

P02.8 still needs the common descriptor-relative safe file primitive wired into the
existing general WorkspaceService/routes, atomic editor replacement, bounded traversal
and delete, path/symlink/type/size/race/error tests and preserved upload/download/
FormData/authentication behavior. Repeat the full gate after that work and complete
T01–T35 evidence, then stop for architect review before P03.

The reviewer should verify the private personal archival bridge scope, original vs
historical schema handling, immutable reconciliation, ownership marker/tool-role
separation and encrypted-but-disabled credentials. A future real data migration needs
its own protected source/provider identity inventory, mappings, target/connection
limits, key retention, expand/backfill/validate/contract and rollback review. No real
backup, export, provider role/bootstrap, academic-data downgrade or deployment is
authorized by this fixture proof. Legacy mode and default-off foundation remain.

Authenticated browser/provider smoke and browser visual/interaction QA: NOT RUN.
Remote Actions: UNVERIFIED; local command wiring is separate evidence.
Real issuer/key/timing and provider PostgreSQL compatibility: UNVERIFIED.
Real mail/activation/runtime data switch/live migration/deployment: NOT RUN.
Notification integration remains pending; full invitation acceptance/binding and
broader member/cohort UX remain P05. P02 remains IN PROGRESS, not phase acceptance.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0219_import_rehearsal.py — SHA256 cdd9fb375200dde473bc7c532b35cd1750740d63cf649d730e8b3326acc56b78
- backend/alembic_foundation/versions/p0219_import_rehearsal.sql — SHA256 4af643c5586c84ffda238ef340f2af2a1be79df8c5265d61cf56e6f1c32473cf
- backend/app/domains/migration/__init__.py — SHA256 03d8ce63e0e4a964b18764cf6538664608dc2afac0b712bf35b9411deb34bc70
- backend/app/domains/migration/cli_inputs.py — SHA256 26fca4225f5248cfccab7b028eae3a911b7fa5e70ce4e60c0009f51bd3e8a376
- backend/app/domains/migration/importer.py — SHA256 433001a87c621ac92ec1b38744cb735de8bc3fba1681733c3219be1948b3f5e4
- backend/app/domains/migration/snapshot.py — SHA256 6df5304fbb0ce55ff157da21e63279e4de437172e8ec72abf0fc5244659c934e
- backend/tests/foundation/legacy_fixture.py — SHA256 936a7f4cfdcbe8b5922653b3344be8c281097dd902e057d6ddbb2647f776633c
- backend/tests/foundation/test_database.py — SHA256 26e5ca7c3db0b889010ba37435dd59db4c939e25f01edc81bca7317e3a2148be
- backend/tests/foundation/test_legacy_historical.py — SHA256 244e67625d765d52752a6968699c8fe4cf9e4f6092b4be6313accf0b28cc1d2d
- backend/tests/foundation/test_legacy_import.py — SHA256 330dec632071c55823abae577dd6d2831da72d3f33055a6c8963b6b6f57d8eb1
- backend/tests/foundation/test_legacy_snapshot.py — SHA256 057c28ffa20fb7a4efddcf176a2eca718f60b82babaf9775c8c78b12e1a5de99
- docs/development.md — SHA256 92c23fcf222077af1f0f62547317d7379d0860e4d051f101023ef40044c266ee
- scripts/check_foundation.py — SHA256 5aeaf0787acbb088a05dad7d9099fee6931c37d1cb360150ecf08fe9427211d1
- scripts/check_local.py — SHA256 d6c2a8e019b862e0e3a6b08656576c5c1b7d33199ba9dade62cdee3709c16347
- scripts/rehearse_legacy.py — SHA256 2ab7cb92caeba764a1f8ccb7ed374c9ec068367e033e0bfa7d0b4f8421fb5504

## Previous checkpoint report (historical evidence)

Current sections supersede earlier pending-state/count statements.
Prior report SHA256: ce468457ee4d11c178323686eccd44e802b8845aae01452fc01dc9770963b7db.

<details>
<summary>Preserved frontend, shared-router, protected-transfer and earlier reports</summary>

# P02 completion evidence — minimal foundation UI and conditional shared router

Status: IN PROGRESS, approximately 78%. P02.6 now has a default-off shared router
mount and the minimal real-client identity, executive provision/detail/job and
protected primary transfer/recovery UI, with mandatory local contracts. This is a
partial P02 checkpoint. P02.7–P02.8 and final architect review remain required.
Do not advance to P03.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous protected transfer/recovery implementation: 25a1176ef0176b1119be346e1ba3adcb1e727e90.
- Parent/report: d6ef1087dabd1dd158d7a3a059c367a3b504690c.
- P02.6 implementation: 416d2e482d1ce6c5cc0effaf4f8efc4fe610e742; branch codex/p02-tenant-foundation.
- Exactly 30 intended implementation paths are listed with hashes below. A separate
  report-only commit records evidence. Unrelated documents/work remain unstaged.

## Implemented behavior and actual proof

The independent factory and legacy application compose the same versioned router.
Its routes are prefix-neutral internally; the independent factory applies /v1,
while the legacy composition mounts the child at /v1 with no duplicate prefix.
The trusted factory accepts only its supported prefix choices. The mount helper
reads an explicit settings mapping, creates no resources when disabled, rejects
an existing /v1 mount, and composes child and legacy lifespans with owned cleanup.
Foundation startup verifies its role before legacy workers start. Child failures
retain sanitized child errors and leave parent handlers/legacy behavior scoped.

Legacy main captures only explicit process foundation/application/auth settings
before importing legacy dotenv-based configuration. A dotenv-only feature flag
cannot enable this new surface. Normal legacy SQLite/Docker configuration, health,
authentication, CORS and cleanup-worker lifecycle remain in their existing path.
Eight new foundation cases include actual legacy-main imports in isolated child
interpreters with synthetic Docker/provider substitutes and temporary SQLite paths,
explicit on/default off/explicit off/dotenv-only behavior, lifecycle failures and
resource closure. The full run printed the actual legacy-main contract marker.
No running service, private env or deployed feature was enabled.

The frontend production client composes the P01 URL/auth adapter. Default /api
joins /v1 endpoints into public /api/v1; existing proxy stripping maps them to
backend /v1. Fixed typed response projections preserve pending state and discard
unknown/private response fields. UUIDs, bounded pages, enum states, versions and
receipt status/replay headers are checked. POSTs send only allowed fields, with
stable creation request keys and quoted If-Match for protected versioned changes.
Network/provider/database messages and raw validation inputs never become user
errors; safe known messages, field names and request references are projected.
This is source/client/mounted-route proof, not a running nginx/browser smoke test.

Only VITE_WPL_FOUNDATION_ENABLED=true selects /foundation and its subpaths.
Legacy paths and /reset-password retain their existing behavior. The production
entry uses Supabase auth and the foundation API without the legacy public.profiles
approval gate, allowing a verified pending identity to see its own status. A small
external session store drives unconditional React hooks. It handles initial-session
races, auth changes, retries, StrictMode-style cleanup/remount and sign-out, aborting
reads and fencing stale completions before another account can see old data. The
view receives a minimal current subject and server-projected account/membership
state, never a session/token. Pending, suspended, declined and denied states do not
gain organization capability merely by opening a route.

An active orgs capability opens the bounded directory, search/paging, executive
detail links and six-field pending-organization form. One in-memory key and frozen
body survive uncertain retries and temporary same-account access refresh. Duplicate
submits are blocked. A definite validation rejection unlocks correction with a new
request identity; starting a new uncertain request is explicit and warns to inspect
the directory first. Creation shows its committed/replayed pending receipt and a
manually refreshed initial invitation job. Pending integration, simulated test
execution and provider acceptance remain distinct; no inbox delivery, invitation
acceptance, user approval or tenant activation is inferred.

Ordinary primary transfer requires an effective active admin membership and a
fresh tenant organization response identifying it as the current Primary Admin
before fetching a paged roster and offering eligible replacement admins. The server
still checks target global state and current eligibility. Executive recovery uses
its separate current capability and explicit reviewed org/version/membership/reason
inputs; it does not impersonate a tenant or open a tenant roster. Directory access
is a separate capability, not a recovery grant. A recovery-only operator supplies
references from an authorized review; arbitrary typed references grant nothing.

The server-confirmed preview displays organization, current/new membership IDs,
version, expiry, reason and consequences before an explicit acknowledgement and
confirmation. Opaque confirmation material remains private in the in-memory
controller, absent from view state/DOM/storage/URLs/diagnostics. Review freezes
inputs. An uncertain result retries exactly the saved operation, including receipt
reconciliation after expiry; a new unsubmitted expired preview is blocked locally.
Definite version, permission and recent-auth errors discard the confirmation and
require current review/recent sign-in. No client clock or checkbox grants server
authority. Logout/account change or loss of the selected membership/recovery scope
clears/fences the workflow. Successful changes show the committed/replayed version,
retained ordinary admin role, unchanged global blocks and a separately read redacted
notification job. Notification integration is still pending; no delivery is claimed.

The actual dark/purple TSX views and root composition are wired through the new
feature entry; CSS is scoped under foundation-shell. Four new mandatory frontend
test modules contain 50 cases: 12 client, 12 identity/session, 12 organization and
14 protected-change cases. They exercise production controllers/client paths and
render the actual TSX with locked TypeScript/React/ReactDOMServer in memory. They
cover capability/pending/deep-link states, escaping, account/request races, paging,
retry identity, confirmation/expiry/version handling and truthful job state. These
are controller and SSR contracts, not browser event/layout or real provider proof.

check_local.py installs the same locked dependencies before offline frontend
contracts so the actual existing compiler/React are available. Contract execution
keeps network-none/read-only isolation and the strict no-skip/nonempty policy. The
isolated build receives the public feature flag true to compile the feature branch;
this does not enable any running/deployed surface. No dependency or lockfile changes
were made. Snapshot declarations include all new source/test/helper files. Backend
foundation module discovery and the original runner failure contracts remain mandatory.

## Full execution evidence

User-run command from /tmp, after exact candidate source verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  /home/wibyte/wibyte-python-lab/scripts/check_local.py
```

Raw full-gate log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-udHsxEA5/P02.6-primary-ui-full-checks.log

Raw log SHA256: 33130021d77df8535000ffa33962242f757b727aea455b689eddb183a895c0a1

| Mandatory group | Actual result |
| --- | --- |
| Runner failure/isolation contracts | 23 passed in 0.545s |
| Setup regressions | 16 passed in 0.242s |
| Legacy backend/idle regressions | 12 passed in 23.124s |
| Frontend strict contracts | 96 passed across 8 declared modules; no fail/cancel/skip/TODO |
| Disposable Postgres foundation | 220 passed across 24 declared modules in 82.181s; no skips |
| Total registered cases | 367 passed; focused runs below are not added again |
| Recreated-target migration/runtime role smoke | Passed |
| Locked frontend install/build/lint | Passed; 0 lint errors, 2 existing warnings |

Build transformed 101 modules. CSS is 27.50 kB / 6.24 kB gzip; JS is 842.81 kB /
225.81 kB gzip. Vite reports its >500 kB chunk warning. App.tsx:1161/1167 retain the
same two loadGitStatus exhaustive-deps warnings (shifted by the added imports).
Starlette's httpx TestClient deprecation remains. No warning suppression or unrelated
dependency sweep was introduced.

## Runtime, isolation and cleanup

PostgreSQL 17.11 image remains
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture identity remains wpl_app / wpl_fixture with Psycopg 3.3.6 binary;
worker proof uses wpl_worker. Runtime is non-owner/non-superuser/no-BYPASSRLS;
wpl_migrator owns the private schema. Existing RLS, composite-FK, pool/context,
primary/instructor/concurrency, idempotency, crypto and fenced-worker cases all pass.
Check image: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node image: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned database container:
5e81a582d0411ced16d8b4fced6291afca3a8403e6d57b1aaadf2e13f0a9ce3e.
Final owned internal network:
67f07f67c8a79ba8a4759c3626be259286de6490893619d824abdf9d3a1526ef.
Both were inspected and removed by exact owned ID; tmpfs data was discarded.
Isolation verification passed: internal network, no published ports, tmpfs data,
no host socket/data mount, read-only allowlisted source and synthetic environment.
Legacy tests retain network-none. Mocked failure/timeout/foreign-owner contracts
remain separate from this actual clean fixture run. No private env/live DB/student
files, external provider account, original labs.wibyte.in, Compose service restart,
application/student image rebuild, live backup/export or global prune was targeted.

## Earlier slice execution provenance (not additional full-gate cases)

- Conditional shared-router mount: 220 unit/foundation cases; /home/wibyte/wibyte-python-lab/work/p02-router-mount-evidence-THnRDcLL/router-mount-checks.log; raw SHA256 767cfd57dd94adb8ecb859f90781d8a14da27ba27b2e9dbbb067912c3519d73a.
- Production foundation client: 23 + 16 + 12 + 220 unit/foundation cases + 58 frontend cases; /home/wibyte/wibyte-python-lab/work/p02-full-evidence-YOiwzmqB/P02.6-client-full-checks.log; raw SHA256 b7d11b267f395e917e7f8f4d9a54cc8a41db8c6f32af49ad0fbef1c1590c5c4e.
- Pending identity and account UI: 23 + 16 + 12 + 220 unit/foundation cases + 70 frontend cases; /home/wibyte/wibyte-python-lab/work/p02-full-evidence-ruMDusGg/P02.6-identity-ui-full-checks.log; raw SHA256 b0aec7270b5f03c3d41fe8454e7e85892252e81e6066b7c8045605bc6ecf41c5.
- Executive organization UI: 23 + 16 + 12 + 220 unit/foundation cases + 82 frontend cases; /home/wibyte/wibyte-python-lab/work/p02-full-evidence-pcJDZx8h/P02.6-organization-ui-full-checks.log; raw SHA256 145a299d52960bcc30a55a1b1b1c924c6c4dbd875220c4fc02f19a22171a588f.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 367 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS socket-blocked foundation factory/domain/mount imports and no legacy DB side effects; actual legacy-main composition tested separately with synthetic adapters. |
| T03 | PASS actual main default/explicit off and dotenv-only nonactivation, legacy SQLite/health/auth/CORS retained; explicit process-on shares the same router with bounded lifecycle cleanup. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented identity/read, provisioning, protected transfer and separate executive recovery HTTP, pending own /me and sanitized stable errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS implemented tenant/executive/provisioning plus primary/recovery runtime and signed HTTP scope matrix; no client actor/scope authority. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented reads/current capability revocation plus executive org status/epoch/audit and tenant access suspension/resume; no immediate provider-logout claim. |
| T13 | PASS atomic executive creation of one pending organization/designated invitation membership, encrypted intent, outbox, audit and receipt; no email binding or activation. |
| T14 | PASS actual concurrent same-actor/key/body DB and signed HTTP creation, changed-body conflict, actor namespaces, new-pool replay and current authority recheck. |
| T15 | PASS ordinary runtime services/direct SQL deny primary removal/demotion/suspension; protected transfer/recovery HTTP use separate confirmed paths and no direct designation grants. |
| T16 | PASS actual app-role concurrent confirmations, version/target/confirmation/recent-auth checks, transfer/removal and target-global-suspension locks; signed HTTP replay matches one committed change. |
| T17 | PASS active-primary/security-recovery invariants and explicit recovery HTTP restoring active org while preserving old global block and retained admin membership. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PASS explicit targeted recovery capability, current expiry/revocation checks, stored reason, recent confirmation and atomic recovery audit/notification intent; no self-bootstrap. |
| T20 | PASS implemented invitation pipelines plus confirmed primary changes with atomic business/receipt/audit/job/outbox, caught failure rollback and new-pool replay; notification jobs remain pending integration. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented invitation encryption and transfer confirmation/receipt/audit/status/error redaction, explicit keys and current intent checks. Notification intent holds no secret payload; imported tokens remain pending. |
| T24 | PASS local real-client/controller and actual TSX/SSR identity, directory/provision/detail/job and protected transfer/recovery contracts; truthful queued/activation state. Browser/provider smoke NOT RUN. |
| T25 | PASS local pending/non-executive/account-change/deep-link UI contracts plus existing actual signed HTTP tampering/RLS denials; no client grant. Browser interaction smoke NOT RUN. |
| T26 | PASS production P01 client public /api/v1 joining and actual conditional /v1 child mount/internal routes; running nginx/browser smoke NOT RUN. |
| T27 | PENDING explicit fixture SQLite dry-run and historical populated-chain proof. |
| T28 | PENDING disposable import/count/ID/repository-map idempotency and negative matrix. |
| T29 | PENDING imported fixture token encryption and explicit personal/mapping preservation. |
| T30 | PENDING wired safe file primitives and negative cases. |
| T31 | PENDING atomic replacement and ordinary file behavior proof. |
| T32 | PENDING actual general-file-route primitive wiring; prior FormData/auth checks retained. |
| T33 | PASS current TS/TSX/helper/migration/test snapshot declarations, locked dependency preparation and owned isolated Postgres fixtures; extend for later modules. |
| T34 | PASS current mandatory local groups: 96 frontend cases/8 modules and 220 foundation cases/24 modules with strict discovery/outcome policy; remote Actions UNVERIFIED. |
| T35 | PASS implemented failure/timeout/cleanup contracts and actual cleanup; no app service mutation. |

## Remaining work and review limits

P02.7 still needs explicit generated/supplied protected SQLite fixture dry-run and
confirmed disposable idempotent import, populated historical-chain compatibility,
counts/UUID/repository/ownership mappings, encrypted fixture tokens and preservation
of personal work without email-only remapping or invented tenant assignment.
P02.8 still needs wired descriptor-relative safe general-file primitives, atomic
replacement and traversal/symlink/type/size/race/cleanup/route negative cases.
Repeat mandatory checks after those changes, complete T01–T35 evidence, then stop
for architect review before P03.

Backend activation requires explicit verified identity/database settings. Production
invitation encryption and delivery need a trusted configured key/provider adapter;
the shared mount alone does not configure them. Notification jobs remain pending
integration. Full invitation acceptance, verified binding and broader account/member
or cohort administration UX remain P05. No production bootstrap/feature activation,
remote schema change or real mail was performed. No immediate provider-logout claim.

Authenticated browser/provider smoke and browser visual/interaction QA: NOT RUN.
Remote Actions execution: UNVERIFIED; local command wiring is separate evidence.
Real issuer/key/timing, provider PostgreSQL compatibility and connection limits:
UNVERIFIED. Live backup/export/import and deployment: NOT RUN. Disposable downgrade
proof does not authorize academic-data down-migration. P02 remains IN PROGRESS;
this local milestone is not phase acceptance or a production-ready claim.

## Exact changed implementation paths/hashes

- backend/app/foundation/api.py — SHA256 7f70e645e740a2f6d1bbf6849ee215f93174f200e7d5435ea8d7a1e9d3bf43c2
- backend/app/foundation/app.py — SHA256 315f27025c7b05c87d90beae92d6013636d1e4d8b710bbbe49d4beff970903f1
- backend/app/foundation/mount.py — SHA256 3f03c26b24e47bfaea2df967c24ea03b294da3c6cbda3e262edd2e20ad76d200
- backend/app/main.py — SHA256 65c1ec6f1c380e9ea2121f1be038a72de9caead89e4fa6bca83fc6d1ccc71aea
- backend/tests/foundation/test_database.py — SHA256 17c3d1a71f29cb386e7093e958c9f99f9d8952e505e3efff12fe26781c7c93f8
- backend/tests/foundation/test_router_mount.py — SHA256 ffd2227a40773fc4f3a891773343eb941e5a88469309285c23911447ce8daf56
- docs/development.md — SHA256 cd4b977fc19ac548acfe4865cb05f21965ea871aa94fd7c63ff902d8ca390193
- frontend/src/App.tsx — SHA256 f5f286280b1481de1a2931fec1d53a6f343d9a698452564162e0cb7a9821fdeb
- frontend/src/features/foundation/FoundationEntry.tsx — SHA256 a3c6b2317454e2dd34f7ed5d433005b5719e7f9b31d6009388617a195cbd536b
- frontend/src/features/foundation/FoundationPage.tsx — SHA256 d9ee5ab4d597c5dfba8b83bf07bedf1d1d4b54d7a562699226b2b56a45808a0e
- frontend/src/features/foundation/IdentityPanel.tsx — SHA256 c7351044ee808445f1f395dca3ba224bd74b0c7ee43b830ec85cc830e38c1c18
- frontend/src/features/foundation/OrganizationPanel.tsx — SHA256 1b937d5bb23914f3f090caa7323b233a5e87fd69b0882e0e187fbdd4d5fce6aa
- frontend/src/features/foundation/OrganizationView.tsx — SHA256 1ee1a8fbfdd77898a57040608c15e2655f5f2b584191a9c629a673bf591ba934
- frontend/src/features/foundation/PrimaryChangePanel.tsx — SHA256 5507e2935f546841be8ebbdc0cb80ed6e5be2dd8afd79c26898d2019ab2a2fcd
- frontend/src/features/foundation/PrimaryChangeView.tsx — SHA256 ecae0405be8bab41e7a24a724d0498b639363ea68ce1341e762f0382ba8e3246
- frontend/src/features/foundation/client.ts — SHA256 b705e9b13ad1243c719a2bd83bf6cabd96ca1604f81a2fbce78224b73311e4f0
- frontend/src/features/foundation/foundation.css — SHA256 a8dce45a0a3dc185aaee31f36f0480effe8538a48d1776829275d8270aaaae4d
- frontend/src/features/foundation/organizations.ts — SHA256 db8a78e6029b4d94303447cbad2306e62c4e4a6bca00885f67c75d4728e25e52
- frontend/src/features/foundation/primaryChanges.ts — SHA256 8c5a92f85da6d63b8efc62d9e8e8f7b631b3de08a818cc0939db888bae3220d0
- frontend/src/features/foundation/route.ts — SHA256 fb725942abe5ea24e67d963dee88e109c796ea095442c0b314b177c327668d75
- frontend/src/features/foundation/runtime.ts — SHA256 1006c9fae3511b33b627ab2795f0b1ae4de58c232fc445288ff73a55f14bbcfb
- frontend/src/features/foundation/session.ts — SHA256 059cd9c43edda20fd0192dcaf97539af02b6bd31b1eb2471cd4f80b307d856f6
- frontend/tests/foundationClient.test.mjs — SHA256 ceba42fee618e81322b182857695fe5bdcd4169f301c2d6ada913a04440eb3f0
- frontend/tests/foundationIdentity.test.mjs — SHA256 c98e4a40ff2f96a5c957b84ff6f59bc9fa2eb55ebde61d56f7a705db045855c1
- frontend/tests/foundationOrganizations.test.mjs — SHA256 808694e94b5eea19925f883ba49db47e1b1fbd0893097c84b06ae4461d887640
- frontend/tests/foundationPrimary.test.mjs — SHA256 7df6300bb0b67e02b53182a38873d11a5c47343ca776cf53bb2ed06d8c7b6e86
- frontend/tests/renderFoundation.mjs — SHA256 af69e478fc81da5b065248beadcc790d853b9990c08d6c8a47f9ca2476a66a01
- scripts/check_foundation.py — SHA256 2491a1fa7b91656e22a608e4b70150e5f1fab4114950ca55149a0ac778e90310
- scripts/check_local.py — SHA256 cee1a7090e9b8e6c5fa7343bb313641ddd0d7164111e2ff11dba381720839209
- scripts/test_check_local.py — SHA256 9c239efea38eeb30d6980ab30d56338545d2b5ef6d268d7650fc2bc6fd99b949

## Previous checkpoint report (historical evidence)

Current sections supersede earlier pending-state/count statements.
Prior report SHA256: c645bb09b235e69ba8529c9268f0ab442fcc16de753b2ad0df760a69c4af9906.

<details>
<summary>Preserved protected-transfer, provisioning, jobs and earlier reports</summary>

# P02 completion evidence — protected primary transfer and executive recovery

Status: IN PROGRESS, approximately 69%. Runtime-role protected primary previews,
confirmed transfer, explicit reasoned executive recovery and signed HTTP now pass.
This is a partial P02 checkpoint. P02.6–P02.8 remain required; do not advance to P03.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous provisioning implementation: d6fd7b8758d177db897ddc7450b7cdde6ae7e9f6.
- Parent/report: 3c3dd81a0e2deaee35ed18c2b94721febbbeafb6.
- Protected transfer/recovery implementation: 25a1176ef0176b1119be346e1ba3adcb1e727e90; branch codex/p02-tenant-foundation.
- Exactly 15 intended implementation paths are recorded. A separate report-only
  commit preserves this evidence; unrelated documents/work are untouched.

## Implemented behavior and actual proof

Revision p0216 adds a narrow app-only preview root and private authority helper.
Tenant preview requires the current active designated Primary Admin of an active
organization. Platform preview requires an explicit current recovery capability,
matching targeted org and recovery_required state. Directory orgs capability alone
cannot grant recovery, and a normal tenant admin cannot transfer the designation.
The org parent lock serializes preview decisions with membership/role/status
changes. The root rechecks authority and expected version, requires another active
same-org admin and persists actor/from/to/scope/reason, a confirmation digest and
five-minute expiry with redacted audit. It leaves designation/roles/epochs unchanged.
Only one live preview exists per org: the same actor may replace its own preview;
a different actor conflicts until expiry. Preview rollback/audit failure restores
the earlier preview. Raw confirmation is returned once and excluded from repr.

Revision p0217 adds an app-only confirmation root. Actor/org/scope, expected version,
SHA256 confirmation digest, current live preview/expiry, current primary and target
eligibility are checked again. Server-bound authentication must be within five
minutes, allowing at most 30 seconds future skew, including after lock waits.
Identity rows are share-locked in UUID order before the org lock, matching the
user-before-org order of global security suspension; recovery also locks its grant
row. Thus a concurrently blocked target cannot become an active primary through
an unchecked user/organization race. No direct designation/transfer-table grants
or owner runtime exemption are introduced by these services.

A successful change atomically updates the one primary reference, advances org
version/access epoch once, completes the preview with a fixed public receipt,
appends actor/reason/version audit and queues notify_primary_transfer plus a pending
primary_transfer_notification_requested outbox event. The old primary keeps its
active admin membership and roles. Explicit recovery restores active org state
without unblocking the old globally suspended identity, approving a user, remapping
an account or granting platform authority. Ordinary orgs status cannot substitute
for this recovery operation. Existing primary and final-instructor guards remain.

The preview UUID is the stable one-use operation identity. Concurrent matching
confirmations and committed retries after a new pool return the same persisted
receipt without another designation/job/outbox. Replay still requires matching
actor/scope/digest/version, current tenant admin or recovery permission and recent
authentication. A former primary can replay while still an active admin; removal,
global block or recovery-grant revocation denies cached results. Real audit and
outbox CHECK failures caught within the service savepoint roll back all earlier
writes and preserve the preview. Outer rollback/retry is also proved.

The shared internal /v1 router, public /api/v1 through the existing proxy, adds:

- POST /orgs/{org_id}/primary-admin-transfers/preview and POST at its parent for
  tenant Primary Admin preview/confirmation.
- POST /platform/organizations/{org_id}/primary-admin-recovery/preview and POST
  at its parent for explicit executive recovery preview/confirmation.
- GET /platform/organizations/{org_id}/primary-admin-recovery/jobs/{job_id} for
  current targeted recovery notification status.

Routes select scope on the server; no input actor/role/scope selector is accepted.
Both preview and confirmation require recent authentication from production signed
identity verification. Preview exposes from/to IDs, expiry, confirmation and the
former-admin retention consequence. Completion accepts only preview ID, expected
version and confirmation. The required expected_version body field follows the
existing foundation write convention; a supplied strong If-Match must match the
quoted version. Weak/mismatching values conflict rather than being ignored.
This is a documented narrow adaptation of the planned If-Match contract. Responses
are emitted after commit; Idempotency-Replayed distinguishes first completion and
receipt replay. Extra fields, boolean/oversized versions, control-character reasons,
invalid UUIDs and malformed confirmation are rejected without echoing input values.

Revision p0218 adds one app-only safe redacted status root. Tenant job HTTP reads
can project a transfer notification only for a current active admin; the explicit
platform recovery status route requires current recovery authority. The root checks
completed private transfer receipt, stored actor/org/kind/dedup/intent digest and
matching outbox, returning only the existing nine status fields. Cross-org, absent,
unauthorized or tampered intent is not_found. The ordinary executive initial-primary
job route remains specific to its original kind/orgs capability. No direct transfer
result, confirmation hash, contact/email, private payload, intent hash or lease is
exposed. Pool reuse after actual HTTP audit failure passes, as do feature-off routes.

Notification intent contains no secret payload or recipient address. Its immutable
from/to IDs remain in the private transfer record. The job is queued with
pending_integration; existing invitation workers deliberately ignore this distinct
kind. Notification worker/provider integration is not supplied or claimed here.
No inbox delivery, real mail call or notification fake-execution proof is claimed.
Existing tenant/initial invitation fake-worker and crash reconciliation tests still
pass separately; their simulated result is never represented as real delivery.

Twenty-six added tests comprise eight preview, ten completion and eight HTTP cases.
Actual app-role competing confirmations produce one committed change and matching
receipt replay. The observed actual transfer/removal result was transferred plus
protected_primary, leaving the new primary valid and the old admin retained.
An actual PostgreSQL target user lock was observed blocking confirmation; after
suspension committed, confirmation rechecked and rejected the target with no job.
Competing recovery preview actors produce one live preview and one conflict.
HTTP tests use production ES256 signatures with synthetic JWKS transport and actual
runtime connections. They cover authority/header/claim/body spoofing, current grant
expiry/revocation, global block with cached tokens, scope isolation, stale input,
redacted/tampered job status, sanitization and actual audit rollback. HTTP concurrency
uses the production bounded fixture pool; a separate two-connection DB race proves
locking. Fixture-owner seeding is not counted as production authority or activation.

## Actual full-gate execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-tktDKRNB/P02.5-transfer-full-checks.log
Raw log SHA256: c3851064cf691ad2deb38dd8a600b71dcc36b037b5871babb1c7ece5485e5644.
The user-run recorder verifies candidate/log/prior-report hashes, actual observed
counts, cleanup/race markers and exact staged/committed bytes. Preparation reads
sources/logs and writes artifact scripts/preview only; developer executes checks
and original-checkout mutations through the agreed terminal workflow.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner contracts/discovery/isolation | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend, four modules | 46 |
| Foundation, twenty-three modules | 212 |
| Total | 309 |

All mandatory cases passed without skips. The 212 foundation cases include the
previous 186 plus 26 new cases. Recreated-target migration/runtime-role smoke is
separate and not an extra case. Focused runs below are not added to the full total.
Dynamic discovery still rejects missing/empty/skipped modules without fixed runtime
count assumptions. All four prior legacy SQLite migrations remain unchanged.

Build passed with 87 modules and npm ci installed 170 locked packages. Lint has
0 errors and the existing two App.tsx:1159/1165 loadGitStatus dependency warnings.
JS remains 801.77 kB / 215.19 kB gzip, with the >500 kB warning; Starlette's httpx
TestClient deprecation remains. No warning suppression or dependency upgrade.

## Runtime, isolation and cleanup



Unchanged PostgreSQL 17.11 image:
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture wpl_app / wpl_fixture, Psycopg 3.3.6 binary; worker tests use
wpl_worker. Non-owner/non-super/BYPASSRLS/create/replication and DDL/escalation
checks pass; wpl_migrator is the private schema owner, not runtime.
Check image: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node image: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned DB container
04f8ff33c5db19be497110d6e62aa9cf81af72bbd2a29771973b08d0b1edbfa9
and internal network
15dce749c893c1943eae1bfa64928d46eb99fdda64e3ace06c10a5a1d511ddec
were inspected and removed by exact owned ID; tmpfs data was discarded. Internal
network, no published ports or host data/socket mounts, read-only allowlisted source
snapshot and synthetic environment/identities only. Legacy checks remain
network-none. Mocked runner failure/cleanup contracts are separate evidence from
actual DB/fixture cleanup. No private env/live DB/student files/provider requests,
Compose up/service restart/global prune or original labs.wibyte.in action occurred.
Foundation stays disabled by default; legacy SQLite/Docker lab remains unchanged.

## Focused execution provenance (not additional full-gate cases)

- Protected transfer preview: 194 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-transfer-preview-evidence-3zsFAQyg/transfer-preview-checks.log; raw SHA256 103a05cb321900a13cf95d15ac7229db63a9d77d5eb07e774ec7b3f5d738f280.
- Confirmed primary transfer/recovery: 204 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-transfer-completion-evidence-5CvazjFw/transfer-completion-checks.log; raw SHA256 b81aba7133717738598b69cc8b92e91ccf4bed3f28d7ff02a65a11fdc39e2796.
- Signed transfer/recovery HTTP: 212 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-transfer-http-evidence-GMVQ6FBO/transfer-http-checks.log; raw SHA256 d05b325173bf167b632b7153bcd3fe343f917a81fa9051f3037ed8b23fcb43ce.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 309 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented identity/read, provisioning, protected transfer and separate executive recovery HTTP, pending own /me and sanitized stable errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS implemented tenant/executive/provisioning plus primary/recovery runtime and signed HTTP scope matrix; no client actor/scope authority. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented reads/current capability revocation plus executive org status/epoch/audit and tenant access suspension/resume; no immediate provider-logout claim. |
| T13 | PASS atomic executive creation of one pending organization/designated invitation membership, encrypted intent, outbox, audit and receipt; no email binding or activation. |
| T14 | PASS actual concurrent same-actor/key/body DB and signed HTTP creation, changed-body conflict, actor namespaces, new-pool replay and current authority recheck. |
| T15 | PASS ordinary runtime services/direct SQL deny primary removal/demotion/suspension; protected transfer/recovery HTTP use separate confirmed paths and no direct designation grants. |
| T16 | PASS actual app-role concurrent confirmations, version/target/confirmation/recent-auth checks, transfer/removal and target-global-suspension locks; signed HTTP replay matches one committed change. |
| T17 | PASS active-primary/security-recovery invariants and explicit recovery HTTP restoring active org while preserving old global block and retained admin membership. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PASS explicit targeted recovery capability, current expiry/revocation checks, stored reason, recent confirmation and atomic recovery audit/notification intent; no self-bootstrap. |
| T20 | PASS implemented invitation pipelines plus confirmed primary changes with atomic business/receipt/audit/job/outbox, caught failure rollback and new-pool replay; notification jobs remain pending integration. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented invitation encryption and transfer confirmation/receipt/audit/status/error redaction, explicit keys and current intent checks. Notification intent holds no secret payload; imported tokens remain pending. |
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

## Remaining work and review limits

P02.6 needs the minimal feature-gated real frontend/client for identity, directory,
provision/detail and protected primary confirmation, plus conditional mounting of
the same router in the legacy app with feature-off behavior retained. P02.7 needs
explicit generated/supplied SQLite fixture dry-run/import, populated historical
migration proof, idempotent mappings and encrypted token/personal preservation.
P02.8 needs wired descriptor-relative safe file primitives and route negative cases.
Complete remaining T01–T35 evidence, then stop for architect review before P03.

Notification jobs remain pending_integration without a notification worker/provider.
Complete invitation acceptance, verified binding and full account/email UX remain
P05. No production key/provider/identity bootstrap or feature activation was done.
Authenticated browser/provider smoke: NOT RUN, as previously deferred.
Remote Actions: UNVERIFIED; local evidence remains separate.
Real issuer/key/timing/provider PostgreSQL compatibility/connection limits: UNVERIFIED.
Real mail, deployment and live backup/export/import: NOT RUN.
Fixture downgrade proof does not authorize real academic-data down-migration.
P02 remains IN PROGRESS; this is not phase acceptance.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0216_transfer_preview.py — SHA256 8416588d595b4377d62e1562a0c21825f0fc612234c3c1034cf4035e41deeab8
- backend/alembic_foundation/versions/p0216_transfer_preview.sql — SHA256 f861301dfa55585d4ceedcb578e6c86743b3fce2e3a1e32e5c1cb39ffdaf2388
- backend/alembic_foundation/versions/p0217_transfer_completion.py — SHA256 43916855197e55cbab8eea1dfcf756575d77137699918c9307b4a584f9ec9685
- backend/alembic_foundation/versions/p0217_transfer_completion.sql — SHA256 3e9734480fd810b74e8a50882bff88934c5bfac7dcf1661336414a3b193f6a03
- backend/alembic_foundation/versions/p0218_transfer_job_read.py — SHA256 1eb2b9f0028ac28178e808dd87da65db41cd739e0ff2d2fd5000335dc783d690
- backend/app/domains/organizations/requests.py — SHA256 330820e843e26bb1efb4395ba3b10ddfd9b12f78bf9416fe8f72b68d740cd82c
- backend/app/domains/organizations/transfers.py — SHA256 fc3799a6e7f5ce9b72cf4e369fb69d487d3f8d73944281b6b3a24833c7a3ac0c
- backend/app/foundation/api.py — SHA256 16d5b266b1f2303d7217b35d9eaa69687fbebb1e81172a5f3816709aef8a6c14
- backend/tests/foundation/test_database.py — SHA256 95b7d79daac0cb161dd0d297a7be15afc7cf7fa7b358af525b41460f0990c249
- backend/tests/foundation/test_http_transfers.py — SHA256 97a83bc20512855644eb7e1bd538fdd02404e5c2d10edd6a929db9c2c0f9409b
- backend/tests/foundation/test_read_rls.py — SHA256 59f9b92f423772306655746b7996ef7ea4eb14cf68d3e33dc40997121736e8cf
- backend/tests/foundation/test_transfer_completion.py — SHA256 d702642b9a6d9661680e096d5c844e1e74ca92ee1a24bef279b14f157eb50c14
- backend/tests/foundation/test_transfer_preview.py — SHA256 a74e0f23ed3c9095af2091b658242cff54ba51526fd6bdf90159d89fd2e3e705
- docs/development.md — SHA256 230c239f3638ad06643152b455094aeaee05cd37a538d8226f4410d01038e6df
- scripts/check_foundation.py — SHA256 c975d79e08422fe84bad8234dedf6a12100406953cbc8655e3197f46e07c277d

## Previous checkpoint report (historical evidence)

Current sections supersede earlier pending-state/count statements.
Prior report SHA256: 5a05fb01be114dca98f1a63f6cfcbdccf8a5ebec182b1ebcc01c1b1bd050b012.

<details>
<summary>Preserved provisioning, executive metadata, jobs and earlier reports</summary>

# P02 completion evidence — pending organization provisioning checkpoint

Status: IN PROGRESS, approximately 63%. Executive creation, scoped creation
idempotency, signed HTTP and initial-primary invitation worker execution now pass.
Protected transfer/recovery and P02.6–P02.8 remain required. Do not advance to P03.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous executive metadata implementation: 20ebea31691c83a208e41f6c36ec1f2afadb8bcf.
- Parent/report: f06fdba5b5ac9b5cb91248ada63f5a6f5a5b3e32.
- Provisioning implementation: d6fd7b8758d177db897ddc7450b7cdde6ae7e9f6; branch codex/p02-tenant-foundation.
- Exactly 19 implementation paths are recorded; a separate report-only commit
  preserves execution evidence. Unrelated untracked documents/work are preserved.

## Implemented behavior and actual proof

Revision p0213 provides a narrow app-only provisioning function. It independently
checks fixed input, actual actor/platform context with no tenant target and current
unexpired orgs capability. A transaction advisory lock plus the receipt constraint
serialize actor/operation/key requests. PostgreSQL canonical JSON request hashing
excludes generated IDs, capability tokens and randomized encryption. Same-body
replays return the original public receipt; changed bodies conflict. Different
executives have separate namespaces. Current authority is checked on replay too.

Creation atomically persists one pending organization, one designated invite_pending
membership with no bound user, admin role, pending invitation, tenant-bound encrypted
payload, queued deliver_primary_invitation job, pending outbox, redacted audit and
201 receipt. It never binds an existing user by email, approves an identity, grants
platform authority, accepts an invitation or activates an organization. Existing
circular/composite constraints and primary guards remain enforced. A real audit
constraint failure and outer rollback leave no partial business/queue/receipt state.

OrganizationCreate validates six fixed fields with normalization, bounds and extra
field rejection. Explicit PayloadCipher preparation generates capability material
and binds AES-GCM to org, actor, job, payload and purpose outside the database
transaction. Missing or failed key configuration is sanitized and creates no state.
No production key provider or mail adapter is implicitly configured.

Revision p0214 adds narrow app-only creation-receipt lookup and targeted redacted
initial-job lookup. POST /v1/platform/organizations requires a bounded ASCII
Idempotency-Key. The short current-authority/receipt transaction closes before key
resolution, and the creation transaction rechecks authority after preparation.
Both first execution and replay return the same committed seven-field public body
with status 201; Idempotency-Replayed distinguishes them in the response header.
Replay survives a new factory/pool and absent or unavailable encryption keys.
Unknown/invalid body/header and capability denial produce no creation side effects.

GET /v1/platform/organizations/{org_id}/jobs/{job_id} requires current targeted
platform authority and exposes only initial-primary job status fields. No private
payload/key/hash/lease/recipient/token data or implicit tenant roster access is
returned. Feature-off behavior and existing reads remain covered. A repeated
HTTP artifact application stopped on its before-source guard because all candidate
files were already installed exactly; a read-only hash check confirmed this and
no source correction or grant expansion was needed.

Revision p0215 extends existing fenced worker roots to the initial-primary kind.
A private helper checks the stored actor, current global status and unexpired orgs
capability for a pending organization. Ordinary invitation jobs retain tenant-admin
checks. Worker context cannot substitute another actor. Payload loading returns
stored purpose for AEAD binding; authorization rechecks the exact designated,
unbound admin invitation, email/token hash, expiry and immutable intent. Private
helper execution and direct tables remain denied to app/worker roles. Downgrade
restores prior worker definitions; the migration chain recreation passed.

Twenty-four added tests cover actual wpl_app provisioning, signed HTTP using real
synthetic ES256 verification with mock JWKS, and actual restricted wpl_worker.
Concurrent DB and signed HTTP requests produce one org/invitation/job/outbox and
one receipt. They cover changed-body and actor separation, key I/O outside DB,
current grant revocation before creation/replay, rollback, redaction and scope.
Initial-primary worker cases cover capability removal/expiry/global suspension,
nonpending org, revoked/expired/nondesignated target, revocation after claim,
mixed-kind competing claims, stored-actor substitution and private-helper denial.
Signed creation through durable fake execution persists simulated status while
org/member/invitation remain pending. A crash after fake acceptance is recovered
by a new pool/adapter with one durable simulated effect and stale lease rejection.
No real provider was contacted; simulated is not inbox delivery or activation.

## Actual full-gate execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-UlVOTq9k/P02.5-provisioning-full-checks.log
Raw log SHA256: 555df7af7ebc44ea35fb0581854bd49dbe0f434832e254f89a7bb317e137abb3.
The user-run recorder verifies candidate/log/prior-report hashes, observed counts,
cleanup markers and exact staged/committed bytes. Preparation reads source/logs and
writes artifact scripts/preview only; developer executes checks and original edits.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner contracts/discovery/isolation | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend, four modules | 46 |
| Foundation, twenty modules | 186 |
| Total | 283 |

All mandatory cases passed without skips. Foundation includes the previous 162
plus eight provisioning, eight HTTP creation and eight primary-worker cases.
Separate recreated-target migration/runtime-role smoke passed and is not an extra
test case. Focused runs below are not added to the full total. Dynamic discovery
still rejects absent/empty/skipped modules without fixed runtime count assumptions.

Build passed with 87 modules; npm ci installed 170 locked packages. Lint has
0 errors and the existing two App.tsx:1159/1165 loadGitStatus dependency warnings.
JS remains 801.77 kB / 215.19 kB gzip, with the >500 kB warning. Starlette's httpx
TestClient deprecation remains. No warning suppression or dependency upgrade.

## Runtime, isolation and cleanup


Unchanged PostgreSQL 17.11 image:
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture wpl_app / wpl_fixture, Psycopg 3.3.6 binary; worker tests use
wpl_worker. Non-owner/non-super/BYPASSRLS/create/replication and DDL/escalation
checks pass; wpl_migrator is the private schema owner, not runtime.
Check image: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node image: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned DB container
6c81ea556874dfa17faeba59f6953630b45a0d1e2193821e0ac576b57b78c206
and internal network
98138bd0c6a7286fa44472ccdee5205dadaac85b0e900069919a054fabb39b60
were inspected and removed by exact owned ID; tmpfs data was discarded. Internal
network, no published ports or host data/socket mounts, read-only allowlisted source
snapshot and synthetic environment/identities only. Legacy checks remain
network-none. Mocked runner failure/cleanup contracts are separate evidence from
actual DB/fixture cleanup. No private env/live DB/student files/provider requests,
Compose up/service restart/global prune or original labs.wibyte.in action occurred.
Foundation stays disabled by default; legacy SQLite/Docker lab remains unchanged.

## Focused execution provenance (not additional full-gate cases)

- Provisioning service: 170 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-provisioning-evidence-L1BnG8PX/provisioning-checks.log; raw SHA256 da1dcaf1b26ba2d25b959244c8eccb51c1408973b1a6501e654b71100573b5bf.
- Signed create HTTP: 178 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-create-http-evidence-8naZSTu9/create-http-checks.log; raw SHA256 20dab81ba94624ff86a8d5b56a74d6e75074b0ceac300d4cf94ec095a9030caf.
- Initial primary worker: 186 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-primary-worker-evidence-AFLAhoKs/primary-worker-checks.log; raw SHA256 4b11933831302a6e17ca17a6489db9055d2b5364de13f0edf831100c38e19a3a.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 283 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented identity/read, executive metadata/status and signed idempotent organization-create HTTP surfaces with pending own /me and stable sanitized errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS implemented tenant and executive directory/metadata/status/provisioning runtime/HTTP scopes. Protected primary transfer/recovery scopes remain pending. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented reads/current capability revocation plus executive org status/epoch/audit and tenant access suspension/resume; no immediate provider-logout claim. |
| T13 | PASS atomic executive creation of one pending organization/designated invitation membership, encrypted intent, outbox, audit and receipt; no email binding or activation. |
| T14 | PASS actual concurrent same-actor/key/body DB and signed HTTP creation, changed-body conflict, actor namespaces, new-pool replay and current authority recheck. |
| T15 | PASS ordinary implemented runtime service/direct SQL paths reject protected primary changes; transfer/recovery HTTP remains P02.5. |
| T16 | PARTIAL: runtime member-version race now passes; protected transfer races/service confirmation remain owner-fixture proof until P02.5 runtime/API transfer. |
| T17 | PASS DB active-primary and audited security-recovery invariants; recovery API pending. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PENDING explicit reasoned/audited recovery mutation; scoped metadata read alone is insufficient. |
| T20 | PASS implemented tenant and initial-primary pipelines: business/audit/receipt/payload/job/outbox rollback, committed retry, worker fencing and durable fake reconciliation. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented tenant and initial-primary payload/API/receipt/audit/error redaction, bound AES-GCM, explicit keys outside DB transactions, replay during key outage, and simulated status. Imported tokens remain pending. |
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

## Remaining work and review limits

P02.5 requires protected primary transfer preview/confirmation/recent authentication,
version fencing, atomic designation change and notification intent, plus explicit
reasoned executive recovery with its separate capability. Existing owner-session
transfer tests do not establish runtime/API transfer or recovery acceptance.
Initial invitation redemption/verified binding/activation is not implemented here.

P02.6 needs the minimal real client and shared-router activation; P02.7 needs explicit
fixture SQLite dry-run/import and populated historical migration proof; P02.8 needs
wired safe file primitives and route negative cases. Finish T01–T35 evidence and
stop for architect review before P03. P02 remains incomplete.

Authenticated browser/provider smoke: NOT RUN, as previously deferred.
Remote Actions: UNVERIFIED; local evidence remains separate.
Real issuer/key/timing/provider PostgreSQL compatibility/connection limits: UNVERIFIED.
Real mail, activation grants, deployment and live backup/export/import: NOT RUN.
Fixture downgrade proof does not authorize real academic-data down-migration.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0213_provisioning.py — SHA256 bf56d1b56ccea56f57c9843d758512836737d802df2cd881b1f6fdb01e308eec
- backend/alembic_foundation/versions/p0213_provisioning.sql — SHA256 ff5006e1592859562856b0bfaaed3d0d1cc33daf56b95d57b97eb530a7fb1e6e
- backend/alembic_foundation/versions/p0214_provisioning_reads.py — SHA256 57f8a9156a6b01ba800611dd4782b887e481077b6d62217f07139fbe97e08c56
- backend/alembic_foundation/versions/p0215_primary_worker.py — SHA256 ef994628cfd4d0c712ca23cdeca5f8f678aa39d7f338ee39da98902ccf246cf4
- backend/alembic_foundation/versions/p0215_primary_worker.sql — SHA256 b26866958920168ee7218b40bb66bebba428773c16b1ea2e57fb42c1fb127bd0
- backend/app/domains/jobs/execution.py — SHA256 e7236081d917a5ec7bdc8ec968983d96b55ff88ce86f3e34b842bbc6bb81b595
- backend/app/domains/jobs/transitions.py — SHA256 755065a7ce3496f7406860699239764977ede01a3e670497b70d8492e8afbd93
- backend/app/domains/organizations/provisioning.py — SHA256 7292e6ab1fa22dafc40a08ccea361ee4d59e9d9bc494d3d7ac54d052b949e358
- backend/app/domains/organizations/requests.py — SHA256 d4b9402098883fc92ceeb1ce5cb9c58dff426ef5a1cd2aa332891d563057d3c3
- backend/app/foundation/api.py — SHA256 a5afc63dcab28572a77c078b580ca56c0fb953fb4526f91b321be257112a612b
- backend/app/foundation/app.py — SHA256 458ac42545b8e3a2ae2c83a08ff66f6f04eb48cd7cda1bb653c9e42fc99c9709
- backend/tests/foundation/test_database.py — SHA256 f668113ce693531933417844dc83c25ab3a0b7d3f2ad67b71e35ecc013867433
- backend/tests/foundation/test_http_platform.py — SHA256 801262e17ad443ecc6747e55878a8fd12aba4d66c835251102f2a8594c62658e
- backend/tests/foundation/test_http_provisioning.py — SHA256 2eca50d7966a583c501d16b2d3711c1f73a60954fa49fe45b17e94b6b0fa51db
- backend/tests/foundation/test_primary_worker.py — SHA256 eb940e89cd576c4b2b7302bd508abcd371da696288e0db1199777006aaaec2bb
- backend/tests/foundation/test_provisioning.py — SHA256 e01f6eb37d6b651805bea87c5663b5e675d69507eb8ceff51f815b9005f1ea11
- backend/tests/foundation/test_read_rls.py — SHA256 14bf1ae4e5bbda501a6561fb788299b650fcf4a43de0867eea288550df4e1e3e
- docs/development.md — SHA256 4e96303b506ac8afd8f975c69934191cb0dac8c948ad88661dfe09d15ab2610e
- scripts/check_foundation.py — SHA256 f6d98efd31cf5a3c4e4e5c54f24a4f92b35dd34824012423084b74de7f6084ab

## Previous checkpoint report (historical evidence)

Current sections supersede earlier pending-state/count statements.
Prior report SHA256: 5a2089a9668f22f1a2b7735512067b0211fb7b609b2e94874b0ba1847dff8a68.

<details>
<summary>Preserved executive metadata, jobs and earlier checkpoint reports</summary>

# P02 completion evidence — executive directory and metadata milestone

Status: IN PROGRESS, approximately 57%. This milestone adds executive directory,
explicit organization detail, redacted tenant job status, versioned metadata and
reasoned active/suspended status changes to the earlier foundation/jobs work.
Initial provisioning, org-create idempotency, protected transfer/recovery and
P02.6–P02.8 remain required. Do not advance to P03; this is not phase acceptance.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous jobs implementation: 30179670f437cfbe162ba903df9c735d83001bce.
- This milestone parent/report: be0e4eeebd969fb9a0ffe94bc07df251a3100500.
- Executive read/metadata implementation: 20ebea31691c83a208e41f6c36ec1f2afadb8bcf; branch codex/p02-tenant-foundation.
- Exactly 11 intended implementation paths were staged. A subsequent report-only
  commit records this evidence; unrelated untracked documents/work remain preserved.

## Implemented behavior and actual proof

GET /v1/platform/organizations uses explicit platform scope and current active
user orgs capability, including expiry. The directory is cursor-paginated with a
1..100 bound, validated status/type filters and literal case-insensitive name
search up to 120 characters. It projects only directory metadata. GET at
/platform/organizations/{org_id} uses targeted platform context and explicit
organization metadata including contact and designated membership reference, not
provisioning identity, tenant roster or private payloads. The shared directory
policy verifies actual wpl_app actor/platform/target context. Tenant admin status,
JWT role/user_metadata, pending users and spoofed headers cannot grant capability.
The read slice adds no migrations/grants or automatic executive bootstrap.

GET /v1/orgs/{org_id}/jobs/{job_id} uses current tenant membership and existing
stored-actor/admin job RLS. It selects only job ID/kind/state/delivery_status,
attempt bounds, fixed last error code and timestamps. Payload/key references,
ciphertext, intent/dedup hashes, lease owner and raw invitation values are omitted.
Cross-org, unauthorized and unknown jobs share not_found. Executives with directory
capability do not implicitly enter tenant roster/jobs. Cached-token suspension
checks and pool reuse/cleanup pass. Pending_integration, simulated and
provider_accepted remain distinct; no result claims inbox delivery. The new HTTP
display-state tests use explicit owner-seeded status fixtures, not real provider
proof. Actual fake execution/reconciliation remains established by P02.4 tests.

PATCH /v1/platform/organizations/{org_id} accepts expected_version, reason and a
nonempty fixed subset of name/contact_email/home_region. Values are normalized,
bounded and validated; boolean versions, whitespace-only reasons/names, invalid
email/region and extra actor/role/designation fields are rejected. POST at
/platform/organizations/{org_id}/status accepts expected_version, reason and
active or suspended. No provisioning/create route is introduced in this milestone.

Revision p0212_executive_metadata grants wpl_app EXECUTE on one narrow
change_organization function with safe search_path/qualified objects. It checks
explicit target platform context/current orgs capability and raw operation/input,
locks the organization, rechecks authority/version and performs change plus audit.
It grants no direct status/designation/epoch update, worker entry or broad table
permission. Existing triggers own version and status epoch increments. Metadata
audit lists changed field names rather than new contact values; status audit
records from/to and versions. No-op metadata changes retain version and avoid
spurious audit. The domain service savepoint also protects callers that catch
an actual audit failure and continue their outer transaction.

Status changes require an active verified designated admin; an initial pending
invitation cannot activate or move into an invalid non-pending organization state.
recovery_required cannot be cleared by the ordinary orgs-capability status route.
Reasoned protected recovery remains separate. Status changes suspend/resume tenant
access and advance epochs. No implicit approval, invitation acceptance, primary
transfer, charge/delete, mail provider or queue side effect is added.

Sixteen new tests use production signature verification with real synthetic ES256
signatures, MockTransport JWKS only and actual runtime-role DB connections.
Fixture owners explicitly seed executive grants; no signed-in user is auto-granted.
Eight HTTP read cases prove bounded/filter pagination, exact projections, capability
expiry/removal/global suspension, actor/context/header/metadata denials, job scope,
truthful display state and nonmutating reads. Eight metadata/status cases prove
commit/versions/epoch/audit, pending-primary/recovery safeguards, field errors,
current capability denials, no-op/direct-column/context protections, two actual
app-connection executive races (one applied, one version_conflict), and a real
PostgreSQL audit CHECK failure that rolls metadata back even when caught.

## Actual full-gate execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-0h6E0az0/P02.5-metadata-full-checks.log
Raw log SHA256: 83c1eb7922777560d775f6db0dda659a6a84c4c04c6a46f29d090c3e89b2c1ff.
The user-run recorder verifies source/log/prior-report hashes, actual counts,
cleanup markers and exact stage/commit bytes. Preparation only read source/logs
and wrote artifact scripts/preview. The developer ran application checks and
original-checkout mutations through the terminal workflow.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner contracts/discovery/isolation | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend, four modules | 46 |
| Foundation, seventeen modules | 162 |
| Total | 259 |

All mandatory cases passed without skips. The 162 foundation cases include the
prior 146 plus 16 new executive read/metadata/status cases. Separate recreated-target
migration/role smoke passed; it is not an additional case. Focused passes below
are not summed into the full total. Mandatory dynamic discovery still rejects
missing/empty/skipped modules without fixing expected runtime counts.

Build passed with 87 transformed modules; npm ci installed 170 locked packages.
Lint passed with 0 errors and the same 2 App.tsx:1159/1165 loadGitStatus dependency
warnings. JS bundle remains 801.77 kB / 215.19 kB gzip and emits the >500 kB warning.
Starlette's httpx TestClient deprecation remains visible. No warning suppression,
broad dependency upgrade or new frontend activation occurred.

## Runtime, isolation and cleanup

Unchanged PostgreSQL 17.11 image:
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture wpl_app / wpl_fixture, Psycopg 3.3.6 binary; worker tests use
wpl_worker. Non-owner/non-super/BYPASSRLS/create/replication and DDL/escalation
checks pass; wpl_migrator is the private schema owner, not runtime.
Check image: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node image: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned DB container
f51723ed2aa316d29c443d30048fd1665ec83b72f90c506d2eee437dfce281d3
and internal network
ce6d16657a7b984bd58ccc816118c9bb0a34d8e4f2f7352df4bf36929b42d524
were inspected and removed by exact owned ID; tmpfs data was discarded. Internal
network, no published ports or host data/socket mounts, read-only allowlisted source
snapshot and synthetic environment/identities only. Legacy checks remain
network-none. Mocked runner failure/cleanup contracts are separate evidence from
actual DB/fixture cleanup. No private env/live DB/student files/provider requests,
Compose up/service restart/global prune or original labs.wibyte.in action occurred.
Foundation stays disabled by default; legacy SQLite/Docker lab remains unchanged.

## Focused execution provenance (not additional full-gate cases)

- platform_reads: 154 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-platform-reads-evidence-39D3YQ1J/platform-reads-checks.log; raw SHA256 59b10919e7975fdfc713edc6ca5853b6caa84b1ba377c09ab93e150c2f6a0ab5.
- metadata_status: 162 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-metadata-evidence-ZOxAueRN/metadata-checks.log; raw SHA256 cc02e577884b62f3c7e214de78378ef845c383f65ab59023066d30ec782d6c09.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 259 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented identity/read plus executive directory/detail, redacted tenant jobs and metadata/status write HTTP surfaces; pending own /me and stable errors retained. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS implemented tenant read/member/role/instructor and executive directory/metadata/status scopes with actual runtime/HTTP denial matrix. Provision/create and protected primary scopes remain pending. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented reads/current capability revocation plus executive org status/epoch/audit and tenant access suspension/resume; no immediate provider-logout claim. |
| T13 | PENDING transactional executive provisioning/invite/outbox workflow. |
| T14 | PENDING org operation idempotency/concurrency; identity mirror repeat is not this criterion. |
| T15 | PASS ordinary implemented runtime service/direct SQL paths reject protected primary changes; transfer/recovery HTTP remains P02.5. |
| T16 | PARTIAL: runtime member-version race now passes; protected transfer races/service confirmation remain owner-fixture proof until P02.5 runtime/API transfer. |
| T17 | PASS DB active-primary and audited security-recovery invariants; recovery API pending. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PENDING explicit reasoned/audited recovery mutation; scoped metadata read alone is insufficient. |
| T20 | PASS implemented tenant invitation pipeline: actual business/audit/receipt/payload/job/outbox rollback, committed retry and restart reconciliation; platform org-create workflow pending. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented tenant payload/service/receipt/audit/error paths: bound AES-GCM, explicit synthetic key provider, current target/intent checks and simulated status. Redacted job HTTP reads now pass; provisioning APIs and imported tokens remain later gates. |
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

## Remaining work and review limits

P02.5 still requires actual idempotent organization creation with exactly one
pending designated primary, invitation/audit/outbox and platform-aware encrypted
delivery, including concurrent same/different-body and actor/operation separation.
It also requires protected transfer preview/confirmation/recent-auth/version,
atomic designation change/notification intent and explicit reasoned executive
recovery. Ordinary orgs status writes do not substitute for recovery. Existing
owner-session transfer fixtures are not runtime/API transfer proof.

P02.6 needs the minimal real client/frontend and shared-router activation wiring;
P02.7 explicit fixture SQLite dry-run/import and populated-chain proof; P02.8 wired
safe file primitives and route negative cases. Complete remaining T01–T35 evidence,
update this report, then stop for architect review before P03.

Authenticated browser/provider smoke: NOT RUN, as previously deferred by developer.
Remote Actions execution: UNVERIFIED; local evidence remains separate.
Real issuer/key/timing/provider PostgreSQL compatibility/connection limits: UNVERIFIED.
Real mail/activation grants/deployment/live backup/export/import: NOT RUN.
Fixture downgrade proof does not authorize real academic-data down-migration.
This is a partial checkpoint report, not final P02 acceptance.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0212_executive_metadata.py — SHA256 f834332a1fe0f017a359a051e03a6d3937f8b1512ce90b83607ed322416905e0
- backend/app/domains/organizations/directory.py — SHA256 8b21b943186b4498fb28bcf441ba23f7d56c0302097153c749528ceafc5f955d
- backend/app/domains/organizations/metadata.py — SHA256 a81843c57692ef06f6d48af8ff9e399687f34447c34f9ee99ce543b38cadc574
- backend/app/domains/organizations/requests.py — SHA256 28257f6027060a3aaa785d6ce22ba318445403f7e2cb92b2c913b1763b0dcdbf
- backend/app/foundation/api.py — SHA256 e88fa2aeb24dd85158dd29c9bafca7ff3760c118e47bcff898d547470c7c453d
- backend/tests/foundation/test_database.py — SHA256 64924231adc3cf3469e8181b269dbd649582d260d6091a6c169322bac85beaf0
- backend/tests/foundation/test_executive_metadata.py — SHA256 8bec46e7cdb3db20cdd5d4c0fc4efdd8e81c40766ac03f78ffb36fa40817a08d
- backend/tests/foundation/test_http_platform.py — SHA256 9d69bd9f16c04a4538f5b921a96cb6cd496e31282d23e91184ba7cf96c810747
- backend/tests/foundation/test_read_rls.py — SHA256 7db2fa713bbdbfc200b2d7a86bbf2c8a8c76bf177213b1e46e841a12a505a0c5
- docs/development.md — SHA256 2b0d9c5cfbb26f730f462b0957d26c52e51acd617325f8df6849257f286f072d
- scripts/check_foundation.py — SHA256 5ee636521c0684619432a97eea5abf4fc1a6e134d38a3942043e9c2e818df88a

## Previous checkpoint report (historical evidence)

Current sections supersede earlier pending-state/count statements.
Prior report SHA256: 555bbcb21233dea8a6ececece14c8bedd3e1a9f5eb0e014240dffc1fa1e8c05f.

<details>
<summary>Preserved jobs, mutation, identity/read and earlier checkpoint reports</summary>

# P02 completion evidence — durable tenant jobs milestone

Status: IN PROGRESS, approximately 53%. The isolated tenant invitation job pipeline
now has encrypted payloads, scoped idempotency, atomic outbox enqueue, restricted
worker leases, fenced transitions, bounded retry and synthetic crash reconciliation.
Organization-create idempotency/platform provisioning, remaining P02.5–P02.8 gates,
final acceptance and architect review are still required. Do not advance to P03.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Previous mutation implementation: cc4e5d3834e70251965f8e75655188a2e8c26870.
- This milestone parent/report: f2da0b0c4a651a44cf84316f79dc9b95a606ede1.
- Jobs implementation: 30179670f437cfbe162ba903df9c735d83001bce; branch codex/p02-tenant-foundation.
- The subsequent report-only commit records this evidence. Exactly 24 intended
  implementation paths were staged; unrelated untracked documents/work are preserved.

Revisions p0207–p0211 extend the private foundation chain only. Existing legacy
SQLite migrations, private configuration, application image and running lab remain
unchanged. Imports construct neither workers nor provider/key clients nor database
connections. Foundation feature activation is still off by default.

## Implemented behavior and actual proof

PayloadCipher uses explicit injected key references and AES-256-GCM with a fresh
nonce and authenticated version/key/scope/actor/operation/payload/purpose binding.
There is no default key, legacy signing-key fallback or concrete production secret
provider. Bounded JSON/envelope validation, tampering, cross-scope replay, recorded
key rotation and missing/wrong-key failures were tested. Payload and provider error
representations are sanitized. Actual private-schema ciphertext round-trips; app
ciphertext reads remain denied. Synthetic keys never leave fixture memory.

Tenant idempotency is limited to member status, role replacement and instructor
assignment. Current bound actor/admin scope is checked before and after a complete
actor/org/operation/key advisory lock. The composite primary key is the final
uniqueness guard. Same-key/same-body requests replay one saved public result;
changed input conflicts. Raw request bodies, tokens and arbitrary receipt fields
are not stored. Callback, business mutation, audit and receipt share a savepoint
and outer transaction. Current permission is required even for cached results.
Actual two-request concurrency, namespace separation, invalid receipt rollback,
outer rollback, new-pool replay and immutable/secret-field denials passed. This is
not organization-create idempotency proof; T14 remains pending.

Tenant invitation preparation resolves/encrypts outside the DB transaction. Enqueue
rechecks exact pending invitation/org/recipient/token digest/expiry and current
actor. A stable delivery UUID serializes retries. Ciphertext, queued job, pending
outbox and redacted audit commit with business/idempotency state. Changed intent
and legacy/unverified job collisions are not adopted. Actual outbox unique failure
and outer rollback leave no orphan payload/job or partial business change. Metadata
reads are scope/actor/admin restricted; application code cannot dispatch or complete.
Only existing pending tenant invitations are supported here. Initial pending-org
platform provisioning remains P02.5 work.

Workers have explicit EXECUTE entry points, not owner/table privileges. Shared
current actor/global/org/member/admin checks use stored job scope/actor; spoofed
worker session context cannot substitute another user. Claim uses row locking and
SKIP LOCKED, due-time checks, batch 1..20, lease 5..300 seconds, attempts, owner and
monotonic generation. Claim dispatches durable outbox intent and audits the lease;
this is not mail delivery. Expired claims can be reclaimed; stale/foreign/expired
leases cannot renew, load ciphertext or complete. Exhaustion dead-letters; current
actor revocation cancels. Direct app/worker queue mutations, app worker-function
calls and internal helper execution remain denied. Safe search_path, owner and
exact EXECUTE grants were inspected. Actual competing claims, held-row skipping,
rollback, expiry/reclaim and generation denial passed without long sleeps.

Fenced payload access returns a bound envelope only after a short worker transaction.
After decrypting outside the DB, execution renews and rechecks current actor and
exact invitation plus complete intent hash immediately before adapter I/O. Retry
codes are fixed, not provider diagnostics; exponential delay starts at 5 seconds,
caps at 300 and dead-letters at max attempts. Transition/audit rollback is atomic.
Global/member/role/org revocation, wrong invitation/token, expired/revoked target,
late completion, backoff/cap and real statement errors were exercised.

process_delivery requires an explicit cipher and adapter. No daemon or real mail
adapter is installed/wired. Adapter calls receive a 10-second timeout contract and
a stable job UUID across lease generations. Adapter/provider I/O and key resolution
occur outside DB checkout. A test-only durable SQLite provider store records only
operation ID/request digest and deduplicates by a unique operation key. Tests crash
after fake acceptance, then reconstruct worker pool/key-provider/adapter objects;
retry reconciles one simulated effect. Overlapping stale/reclaimed workers and a
real PostgreSQL CHECK failure after fake acceptance also reconcile one effect while
only the current lease acknowledges. This proves this explicit fake adapter's dedup
contract, not universal exactly-once external delivery from database leases.

Acknowledgement persists simulated or provider_accepted separately from job state.
Fake receipts and enqueue replay remain simulated; no Delivered claim is inferred.
provider_accepted has no concrete provider implementation in this milestone and
would mean acceptance only, not inbox delivery/read. Revocation can race external
I/O after the final DB check; operation-specific provider reconciliation and actual
provider policies remain required before activation. Historical control transitions
without an adapter acknowledgement retain pending_integration.

## Actual full-gate execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-0qRUbBkQ/P02.4-jobs-full-checks.log
Raw log SHA256: 7303693ebb2a4a8d244348a8d8acdade0d57d3638e358e4e4070d073e3a04f19.
The guarded recorder checks source/log/prior report hashes, actual group counts,
cleanup markers and staged/committed bytes. Preparation read these sources/logs
and wrote artifact scripts/preview; the developer executed application checks and
original-checkout mutations in the terminal workflow.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner contracts/discovery/isolation | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend, four modules | 46 |
| Foundation, fifteen modules | 146 |
| Total | 243 |

All mandatory cases passed with no skips. The 146 foundation cases include the prior
93 plus 53 new cases (9 crypto/storage, 10 idempotency, 10 enqueue, 8 leases,
8 transitions, 8 execution). Separate recreated-target migration/role smoke passed;
it is not an extra test case. Focused passes below are not added to the full total.
Mandatory discovery still rejects missing/empty modules and skipped cases without
requiring fixed runtime test counts.

Build passed (87 modules); locked npm ci installed 170 packages. Lint passed with
0 errors and the same 2 App.tsx:1159/1165 loadGitStatus dependency warnings. JS bundle
remains 801.77 kB / 215.19 kB gzip with a >500 kB warning. Starlette's httpx TestClient
deprecation remains visible. Warnings were not suppressed. No dependency upgrade
was introduced by this milestone. Earlier development failures remain in history.

## Runtime, isolation and cleanup

Unchanged PostgreSQL 17.11 image:
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual fixture: wpl_app / wpl_fixture, Psycopg 3.3.6 binary; worker tests connect as
wpl_worker. App/worker non-owner/non-super/BYPASSRLS/create/replication attributes and
DDL/escalation denials passed. wpl_migrator owns the private schema, not web/worker
runtime. Check image ID:
sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Node runtime ID:
sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.

Final owned DB container
130a504a7ec9795ff5c38ae40f4158749edfdb96a2d61d063f9476db34f29c97
and internal network
6921b571787166c045933e67bc4a4535bfc114f5aec25b67616ff65f46c7e2f8
were inspected and removed by exact owned ID; tmpfs data was discarded. No published
ports or host data/socket mounts. Read-only allowlisted source snapshot, synthetic
identities/environment and owned internal network only; legacy checks network-none.
Test-only provider SQLite files live in owned temporary directories and are removed.
No live DB/student files/provider requests/private env changes/Compose up/service
restart/global prune/original labs.wibyte.in actions were performed. Mocked runner
failure/cleanup contracts remain distinct from actual Postgres/fixture cleanup proof.

## Focused execution provenance (not additional full-gate cases)

- encryption: 102 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-crypto-evidence-HiVh6Ge7/crypto-checks.log; raw SHA256 532effc211a32c178a6ca0046795281c7d73e0b0efd9ca27730ca0f287e83267.
- idempotency: 112 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-idempotency-evidence-lEr6DLkt/idempotency-checks.log; raw SHA256 a034391b5efbd8cee204f700f82a7e6ab3d61ce70430a4c5f85cc6a8711546b5.
- enqueue: 122 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-enqueue-evidence-c3EIUlqy/enqueue-checks.log; raw SHA256 8ee24f13399250c33d39cd8efa43a675f5b7b1c66551bed7090a2c77121a48c0.
- leases: 130 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-leases-evidence-WZYVNGmY/leases-checks.log; raw SHA256 bb0cf70af85422a788232cee503ad9085d0f60e00294930dc2707ce7d1cda886.
- transitions: 138 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-transitions-evidence-Jj2S9ojg/transitions-checks.log; raw SHA256 2dcba399bde12990caaffabc776510f1e49cce18a98e79594d24e86c15aef88a.
- execution: 146 foundation passes; /home/wibyte/wibyte-python-lab/work/p02-execution-evidence-6L0lsdgu/execution-checks.log; raw SHA256 02bc3197620cb4ca1b6d55f3b4dff63673878e8145646db1aa374978b1f80dfc.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 243 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented HTTP identity/read surfaces, pending own /me, invalid identity/errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS ordinary tenant scope: actual read DB/HTTP matrix plus positive runtime member/role/instructor writes and cross-org/non-admin denials. Executive/primary write scopes remain P02.5. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented new reads: current user/member suspension blocks cached-token requests; epoch guard tests retained. |
| T13 | PENDING transactional executive provisioning/invite/outbox workflow. |
| T14 | PENDING org operation idempotency/concurrency; identity mirror repeat is not this criterion. |
| T15 | PASS ordinary implemented runtime service/direct SQL paths reject protected primary changes; transfer/recovery HTTP remains P02.5. |
| T16 | PARTIAL: runtime member-version race now passes; protected transfer races/service confirmation remain owner-fixture proof until P02.5 runtime/API transfer. |
| T17 | PASS DB active-primary and audited security-recovery invariants; recovery API pending. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
| T19 | PENDING explicit reasoned/audited recovery mutation; scoped metadata read alone is insufficient. |
| T20 | PASS implemented tenant invitation pipeline: actual business/audit/receipt/payload/job/outbox rollback, committed retry and restart reconciliation; platform org-create workflow pending. |
| T21 | PASS actual restricted-worker competing claims, SKIP LOCKED, expiry/reclaim/late completion fencing and durable fake-adapter dedup/crash reconciliation; no universal external exactly-once claim. |
| T22 | PASS bounded batch/lease/attempts, persisted exponential retry/cap/dead-letter, stored scope/actor/global/member/role/org checks and explicit fixture timestamps without long sleeps. |
| T23 | PASS implemented tenant payload/service/receipt/audit/error paths: bound AES-GCM, explicit synthetic key provider, current target/intent checks and simulated status. Public provisioning/job APIs and imported tokens remain later gates. |
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

## Remaining work and review limits

Next is P02.5 executive provisioning and protected transfer/recovery: actual runtime
policies/services/APIs, organization-create idempotency/concurrency, initial pending
primary invitation/outbox and explicit scope/confirmation/recent-auth/version/audit.
Public redacted job-status routes must preserve simulated/queued/acceptance semantics.
The current tenant-only queue does not authorize platform initial provisioning.

P02.6 still requires minimal feature-gated frontend and shared-router activation
wiring; P02.7 explicit synthetic SQLite dry-run/import rehearsal and populated-chain
proof; P02.8 wired safe file-route primitives. Existing owner transfer fixtures are
not a substitute for protected runtime/API transfer. All remaining T01–T35 gates
must be completed and this report updated before architect review. Stop before P03.

Authenticated browser/provider smoke: NOT RUN, as previously deferred by developer.
Remote Actions execution: UNVERIFIED; local evidence remains separate.
Real issuer/key/timing/PG-provider compatibility/connection limits: UNVERIFIED.
Real mail/activation grants/deployment/live backup/export/import: NOT RUN.
Keep the foundation feature off and legacy SQLite/Docker lab usable. Fixture-only
schema downgrade proof does not authorize real academic-data deletion/down-migration.
This is a partial checkpoint report, not phase acceptance.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0207_idempotency.py — SHA256 a98529741104f534766f2fced22177fb164f215538df1eb9508a2f95bfbf2e5e
- backend/alembic_foundation/versions/p0208_enqueue.py — SHA256 1020dfa4d1caaa7ac902654ec6ee34586d237ea7cb8fd38280cb0f15e9db0c21
- backend/alembic_foundation/versions/p0208_enqueue.sql — SHA256 0c61a93580be791f70cc15573ae386ce23c551d0b5dc645e0fe264fff4f13f81
- backend/alembic_foundation/versions/p0209_worker_leases.py — SHA256 01a2cad4fe5be1de879805b7d53ccd5e326126daadfc9e230d6a61bc4da534de
- backend/alembic_foundation/versions/p0209_worker_leases.sql — SHA256 fef9ed28582555e4e92be8a2e2c4a98fe81af0069a704cd5dde72b1d5326664d
- backend/alembic_foundation/versions/p0210_worker_transitions.py — SHA256 4166d786312262b9e074638bddb03c3de68fdfdf39e6f1540b03db6a79fb205b
- backend/alembic_foundation/versions/p0210_worker_transitions.sql — SHA256 4e28abd56290851fd0ea1c606dcf4adfed1beb1f39e8ae4cfeaeb08cb4036068
- backend/alembic_foundation/versions/p0211_delivery_execution.py — SHA256 ccfcd643e45d8b3fad76c552d98c97e2001462dea0f6000aa1fb4ae2c8302462
- backend/app/domains/jobs/enqueue.py — SHA256 703204039b2e6f52eb02b68e32d01ab47530680327f4bf95d433b18433f28c51
- backend/app/domains/jobs/execution.py — SHA256 5fdd53c179c3e16e8828ced9c0ed46c873e9c672472f270c07b09a28d90e866d
- backend/app/domains/jobs/idempotency.py — SHA256 b7e42e775430be9df7211e6ea98be1c10eb4f8dddcfdf87d65d68b47f9c0291c
- backend/app/domains/jobs/leases.py — SHA256 addaadde672c000d01084df785e15d716c306e87da67cf72ddc3c3b82a32671b
- backend/app/domains/jobs/payloads.py — SHA256 3946a5de6de4e299d817a7975954bed860470646a69d90b5408bf8fbcbc1ab4e
- backend/app/domains/jobs/transitions.py — SHA256 5d75ccba4092051aa21323fd6defa562044eb5e40fdec22693659dc57ad508d1
- backend/tests/foundation/test_database.py — SHA256 606db3f112aff875c89c1bccdd67ca64b3c9809bbd0974a6af20650265a056e4
- backend/tests/foundation/test_enqueue.py — SHA256 e20888e96e34c052617c542259b1be26c0de02a99cf7c2a307566752dada7f0e
- backend/tests/foundation/test_idempotency.py — SHA256 9a97f0d37b29395f12961e4a86e97c0d0a2d6326426871bc8223d0c1dde6bd1c
- backend/tests/foundation/test_payloads.py — SHA256 d72e84953d05870d85356ff114becad350bb66f30a822c3f49d20a1fe50326d9
- backend/tests/foundation/test_read_rls.py — SHA256 dee3a4da709aadffd877d36da769cb99d4957595b04d30c34df6fe6001cf6036
- backend/tests/foundation/test_worker_execution.py — SHA256 26e97c5251cb4a6517c7d6acaceeec89093a39ddebf696cf0462e203a4b49bfb
- backend/tests/foundation/test_worker_leases.py — SHA256 795a5e3108a56ac908e59aea0c99fb507d5c52412c2afe3190752ab875a455b0
- backend/tests/foundation/test_worker_transitions.py — SHA256 959928abf33390d910ff1c1f2bd99e29ae431d3b8a54dc00fb9e34dd609fa4de
- docs/development.md — SHA256 25d62db5ac009644b63abf79606313bba354101dcdf5b65d334d913b0cd272ee
- scripts/check_foundation.py — SHA256 93275a12d670ea0e26beb9f9d71198ff5be43bf54bf6283d9c1e9b126ffaf50e

## Previous checkpoint report (historical evidence)

The current sections supersede earlier pending-state/count statements.
Prior report SHA256: ba5001a0392b72ad55dfc2953f35166535b37db184c1fc853e82f913521c6752.

<details>
<summary>Preserved mutation, identity/read and earlier checkpoint reports</summary>

# P02 completion evidence — ordinary tenant mutation milestone

Status: IN PROGRESS, approximately 41%. This milestone adds actual application-role
member/role/instructor mutations to the earlier identity/context/read foundation.
P02.4–P02.8, primary/executive write scopes, final acceptance and architect review
remain required. Do not advance to P03. Earlier reports are preserved as history.

## Source identity and bounded change

- Accepted P01: 0fc1ca53932b94fdcb91ddc20313cbb85ac7edbd.
- Prior identity/read source: ea805e5e7648c356ec8e428e692f9545c3245741.
- This milestone parent/evidence: 760048d83839dd3a33386c715bef3d76d8130681.
- Mutation implementation: cc4e5d3834e70251965f8e75655188a2e8c26870; branch codex/p02-tenant-foundation.
- The subsequent report-only commit records this evidence. Only the 7 intended
  implementation paths below were staged; unrelated untracked files remain preserved.

Revision p0206_tenant_mutations grants active same-org tenant admins ordinary member
status/version writes, organization role INSERT/DELETE and cohort instructor
assignment INSERT/UPDATE(status). Metadata column grants allow required FOR UPDATE
locks; no organization/member creation, user-ID/org remapping, access-epoch override,
global approval, primary designation, executive/worker/queue authority is added.
Existing parent/version/epoch and deferred primary/final-instructor guards remain.
Only two additional boolean entry points receive app execution, with fixed safe
search_path/qualified objects. Internal helper and worker execution stay revoked.

Audit INSERT requires the bound actor, current same-org admin authority, existing
same-org membership/cohort target, supported action/type and a bounded reason.
Audit UPDATE/DELETE remains ungranted; admins can read only own-org audit. Existing
services append business/audit in one caller-owned request transaction. An audit
failure rolls back prior business changes. No external I/O occurs in these services.

Shared service policy now compares passed identity/org against actual transaction
context for wpl_app before reading current grants. This prevents substituting another
visible admin's identity in a service call. The migration owner is trusted solely
for maintenance/owner fixtures and remains rejected as web runtime by factory role
checks. There is no request-selectable role, actor header or debug bypass. Worker
service calls remain denied until their explicit stored-actor/scope design in P02.4.

Ten new tests execute existing production services under actual wpl_app/request
context without fixture grants or owner writes for the operation under test. They
prove status commit/rollback/epochs/audit, role changes without platform grants,
instructor replacement/upsert with removed-history retention, non-admin/cross-org/
context-mismatch denials, direct protected-primary/final-instructor SQL guards,
private-column/authority denials, forged audit actor rejection and audit-failure
rollback. Two actual application-role administrators race on one expected membership
version: one commits, one returns version_conflict, and exactly one audit remains.
No fixed number of test cases is required by the mandatory runtime harness.

An ordinary admin dropping/suspending their own current authority fails closed and
rolls back without partial role/status/audit changes, now explicitly tested. Explicit
exit/rejoin is P05 work. Primary designation writes remain denied until P02.5's
protected transfer/recovery path. No new write HTTP endpoint is introduced; existing
read APIs and own pending identity mirror remain the implemented HTTP surface.

The old composite-FK fixture now exercises role/assignment writes using production
policies with typed actor/org binding. Only pending transfer/invitation tables retain
temporary constraint-only grants until their workflow policies exist. Teardown no
longer revokes production role/assignment mutation permissions. Those two temporary
fixture tables remain constraint proof, not transfer/invitation authorization proof.

## Actual full-gate execution

Developer ran from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

Full log: /home/wibyte/wibyte-python-lab/work/p02-full-evidence-420ILkLz/P02.3-mutations-full-checks.log
Raw log SHA256: 83e6e9986bf74841bb48de30080bcd85f4eb674427a96250b29aa04edcc462e5.
Source, log, prior report, observed counts, cleanup markers and stage/commit bytes
were checked by the user-run recorder. Preparation only read these files and wrote
artifact scripts/preview; application tests and original-checkout mutations were
performed by the developer's terminal workflow.

| Mandatory group | Actual passes |
| --- | ---: |
| Runner contracts/discovery/isolation | 23 |
| Setup regressions | 16 |
| Legacy backend/idle | 12 |
| Registered frontend, four modules | 46 |
| Foundation, nine modules | 93 |
| Total | 190 |

All mandatory cases passed with no skips. The 93 foundation tests include the prior
83 plus 10 actual-runtime mutation tests. Separate recreated-target migration/role
smoke passed and is not an extra case. Focused runs are not added to the full total.
Build passed (87 transformed modules); npm ci installed 170 locked packages. Lint
passed with 0 errors and the same 2 App.tsx:1159/1165 loadGitStatus dependency warnings.
JS bundle remains 801.77 kB / 215.19 kB gzip with a >500 kB warning. Starlette's httpx
TestClient deprecation remains visible. No warnings were suppressed or broad upgrades
introduced. This focused mutation slice passed on its first 93-case execution; earlier
read/HTTP development failures remain documented in historical evidence below.

## Runtime and isolation

Unchanged pinned PostgreSQL 17.11 image:
postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652.
Actual runtime role/database: wpl_app / wpl_fixture; Psycopg 3.3.6 binary.
Check image ID: sha256:bfc852f33cf0fbc9ff7a61897d599682ac71bc4a2a8e15ba1bc8d2268b896d2e.
Pinned Node image ID: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c.
Existing actual pg_roles/owner/DDL/escalation tests passed again: migrator owns wpl,
app/worker are not owners/superusers/BYPASSRLS/create-db/create-role/replication roles.
No dependency, private environment, provider or running application image changed.

Final owned DB container e290af1d38ba76817b89318201a1857409e4a305b1537894ff79470c054838e6
and internal network ff0efd8b872c04aa70589a774180b41e6de5b60d9cd1eda88d24f236d3fe23d6
were inspected and removed by ownership-checked exact ID; tmpfs data was discarded.
The fixture has no published port or host data/socket mount. Tests use the allowlisted
read-only source snapshot, synthetic identities/env and owned internal network;
legacy regressions remain network-none. No live DB, student files, provider request,
private env change, Compose up, service restart, global prune or original
labs.wibyte.in action was performed. Runner failure/timeout/empty/skip/cleanup contracts
also passed; their mocked Docker responses are separate from actual fixture cleanup.

## Current T01–T35 ledger (implemented surfaces only)

| ID | Current result and limit |
| --- | --- |
| T01 | PASS this milestone: 190 tests, build/lint, existing warnings; phase incomplete. |
| T02 | PASS import/factory tests with socket connect blocked, no legacy modules/DB files. |
| T03 | PARTIAL: disabled factory and retained legacy checks pass; shared-router activation mounting pending. |
| T04 | PASS fresh/repeat/concurrent/advisory migration, no import DDL, recreation. |
| T05 | PASS actual non-owner app/worker attributes and DDL/escalation denials. |
| T06 | PASS actual composite constraints under explicit disposable write fixture; not mutation RLS proof. |
| T07 | PASS implemented HTTP identity/read surfaces, pending own /me, invalid identity/errors. |
| T08 | PASS actual asymmetric crypto and synthetic claim/key/metadata negative matrix. |
| T09 | PASS synthetic bounded rotation/outage/cache paths; real project compatibility unverified. |
| T10 | PASS ordinary tenant scope: actual read DB/HTTP matrix plus positive runtime member/role/instructor writes and cross-org/non-admin denials. Executive/primary write scopes remain P02.5. |
| T11 | PASS scoped pool commit/rollback/error/raised cancellation/PG timeout and HTTP reuse; no transport-disconnect claim. |
| T12 | PASS implemented new reads: current user/member suspension blocks cached-token requests; epoch guard tests retained. |
| T13 | PENDING transactional executive provisioning/invite/outbox workflow. |
| T14 | PENDING org operation idempotency/concurrency; identity mirror repeat is not this criterion. |
| T15 | PASS ordinary implemented runtime service/direct SQL paths reject protected primary changes; transfer/recovery HTTP remains P02.5. |
| T16 | PARTIAL: runtime member-version race now passes; protected transfer races/service confirmation remain owner-fixture proof until P02.5 runtime/API transfer. |
| T17 | PASS DB active-primary and audited security-recovery invariants; recovery API pending. |
| T18 | PASS implemented ordinary paths: DB final-instructor races, runtime instructor replacement/history, direct SQL guard and actual assignment-aware read matrix. |
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

## Remaining work and review limits

Next checkpoint is P02.4 durable jobs/outbox/idempotency, encrypted sensitive payloads,
lease fencing/retry/dead-letter and stored-actor permission rechecks. P02.5 must finish
executive provisioning, primary transfer/recovery runtime policies/services/APIs and
queued notification effects. P02.6 adds the minimal gated UI/shared-router activation
wiring; P02.7 explicit fixture import rehearsal; P02.8 actual safe file-route primitives.
Current HTTP denials are read-route proof; write API comparisons land with their
implemented P02.5 routes. Existing owner-session transfer tests are not substituted
for that later actual-runtime/API gate.

Authenticated browser/provider smoke: NOT RUN, as previously deferred by developer.
Remote Actions execution: UNVERIFIED; local tests are separate evidence.
Actual provider issuer/keys/claim timing/PG compatibility/connection limits: UNVERIFIED.
Real email delivery/account grants/deployed activation/live backup/export/import:
NOT RUN. No change to the original labs.wibyte.in system. Keep the feature off and
legacy SQLite/Docker lab usable. Local source reverts are reviewable; fixture schema
downgrade proof does not authorize real academic data deletion/down-migration.
Complete all remaining T01–T35 gates and update this report before architect review;
stop for review before P03. This is a partial phase report, not acceptance.

## Exact changed implementation paths/hashes

- backend/alembic_foundation/versions/p0206_tenant_mutations.py — SHA256 d6be20751e19de343d0adcaa250b9b99652ba31134aa41bace09b542f4d6a1b8
- backend/app/domains/authorization/policy.py — SHA256 ff3aac2eccfb7d249d2bba1e7721191e79ff461ea7a2ff2799e144ff966c3072
- backend/tests/foundation/test_mutation_rls.py — SHA256 c86e3c851414b9520ed1be5e84d6ff07473e313c2eae83e715c8466b35981206
- backend/tests/foundation/test_read_rls.py — SHA256 4918297012ae7a2a107f683f6ad005f4d17c76a23cddffe075385bd1b11a3896
- backend/tests/foundation/test_schema.py — SHA256 e72283f640a42a25da952f1d31b451c7b6a16d976bff04f15557094881d6fcdc
- docs/development.md — SHA256 05512c8caaa00417b215a1acc2111eb9c412730aadf9776680b2e1ca05f67498
- scripts/check_foundation.py — SHA256 b60f0884d4dd9c2e8016e253fe1250b806bfacb2b8d23df4220671725a9d09f0

## Previous checkpoint report (historical evidence)

The current sections above supersede the earlier pending-state/count statements.
Prior report SHA256: da9007f3cab904d1fb825dd8201d74f7dfe0860f910e4089514e19ed8a7dea60.

<details>
<summary>Preserved identity/read and earlier checkpoint reports</summary>

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

</details>

</details>

</details>

</details>

</details>

</details>

</details>
