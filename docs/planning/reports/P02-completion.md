# P02 completion evidence — checkpoint P02.1 only

Status: IN PROGRESS. P02.1 local gate passed on 25 October 2026; P02.2–P02.8 have
not begun. P02 is not accepted or complete. Stop for architectural review only
once the remaining authorized phase work and final report are complete.

## Source identity and scope

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

## Actual execution evidence

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

## Database/runtime identities and isolation

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

## Configuration and remaining gates

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

## Exact implementation paths and hashes

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
