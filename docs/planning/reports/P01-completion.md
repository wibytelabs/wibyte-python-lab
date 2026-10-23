# P01 completion report

Date: 23 October 2026, Asia/Kolkata.
Status: implementation and mandatory local acceptance complete; ready for Astra review.
P02 has not started and must wait for review.

## Result and evidence ownership

The developer executed the commands through the agreed copy/paste workflow.
This report records their returned output, reviewed against the P01 handoff,
plus read-only source/diff review. It does not represent an independently
executed production, browser or provider validation.

P01.1 baseline/isolation, P01.2 check entry point, P01.3 URL/auth extraction,
P01.4 idle defaults, and P01.5 CI/developer guide are implemented. All final
mandatory local checks passed. The developer explicitly selected
"Defer smoke to Astra review" for optional authenticated browser/provider smoke.

## Repository and checkpoints

Repository: /home/wibyte/wibyte-python-lab, the intended development replica.
Origin was checked without printing credentials and matches
https://github.com/wibytelabs/wibyte-python-lab.git.
The separate Codex app worktree was not used for implementation.

Base and validation HEAD: 400fc1efc42794e9da42c6ef565f93c71d4dc58f.
Validation branch: main, with the P01 working changes.
Tracked baseline was clean. Existing untracked planning documents, DOCX/PDF
attachments and work/ archives were preserved and excluded from P01 staging.
At report preparation there were no staged changes or checkpoint commits.
The final terminal step creates codex/p01-foundation and records checkpoint
receipts below before committing the report. The commit containing this
report is the final foundation checkpoint; its own SHA is resolved from Git
history rather than embedded in itself.

## Implemented contracts

- scripts/check_local.py derives its root from its file, works from /tmp,
  checks prerequisites before expensive work, and returns nonzero on missing
  tools/images/files, child failures/timeouts, empty Python discovery or skips.
  --prepare pulls a missing pinned Node runtime and builds only a dedicated
  dependency image; a normal run requires those cached runtimes.
- The dependency image contains pinned backend requirements, with an
  allowlisted two-file build context and no application/env/data. Its
  wpl-p01-checks tag hashes the requirements and test Dockerfile. Application
  image tags and Compose services are not rebuilt or recreated.
- A fresh source snapshot includes only declared code/config/manifests/assets
  and tests, including new unstaged source. It excludes private env, real DB,
  .git, credentials, backups and work/; symlinks are rejected. Snapshot
  directory permissions support the explicit unprivileged container user.
- Backend tests have no network or Docker socket, a read-only root/source,
  bounded writable /tmp tmpfs and a synthetic /tmp/fixture.db. Config precedence
  fixtures use additional temporary source/dotenv copies, never backend/.env.
- Frontend contract tests, build and lint run offline. Only locked npm
  installation has network access. Its writable source copy and dependencies
  are disposable. Clean synthetic environments avoid inherited provider values.
  Setup tests use a temporary HOME/config and synthetic mocked fixtures.
- apiUrls.ts accepts relative /api[/], absolute local APIs with optional
  prefix, and absolute HTTP(S) APIs. Missing/empty base falls back to
  same-origin /api. Joins preserve the prefix and encoded identifiers.
  URL parsing derives ws/wss without silently upgrading explicit HTTP.
  Invalid schemes, credentials, query/fragment bases, external endpoints and
  endpoint dot traversal fail. Requests must stay inside the configured API
  origin/prefix before session lookup.
- apiClient.ts supplies the shared injected fetch implementation; api.ts binds
  it to Supabase getSession/browser fetch. App retains credentials=include;
  Settings retains the browser default. Caller options/headers/Request/body/
  AbortSignal and raw Response behavior are preserved. FormData receives no
  forced content type; no missing-token bearer header is synthesized.
- Terminal uses the shared resolved WS URL and an encoded lab identifier.
  Its first authenticate JSON frame, token prop, xterm/ref lifecycle,
  Run/Stop and output handling are unchanged. Settings temporarily retains
  apiUrl, supplied by shared API_URL. Backend routes and Nginx prefixes remain.
- Omitted idle defaults and newly generated/example values are 35 minutes.
  Explicit positive 30/45/other values remain authoritative. Process values
  override dotenv; invalid/nonpositive values fail. Existing private env and
  loaded running-service timeout values were not changed.
- Seven pre-existing lint errors were fixed narrowly: reset-password routing
  now wraps a separate component whose auth hooks are unconditional, and an
  unused process-exit callback parameter was removed.
- CI uses the same entry point on ubuntu-24.04 with host Python 3.14.4,
  documented v7 checkout/setup-python actions, contents:read and no persisted
  checkout credentials. It targets the development repository, without
  provider secrets, deploy/publish jobs, cloud identity or privileged PR trigger.
- docs/development.md documents prerequisites, commands, isolation, URL/default
  contracts, optional smoke, troubleshooting and cleanup. Historical docs gain
  short pointers. Existing ignore rules suffice because all new artifacts stay
  in temporary directories; no broad source/report-hiding rules were added.

## Baseline checks

All rows below are actual developer-run output from this phase.

| Command/check | Environment | Passed / failed / skipped | Evidence |
| --- | --- | --- | --- |
| python3 -m unittest scripts.test_setup -v | Host Python 3.14.4, Compose 2.40.3 | 15 / 0 / 0 | Original cases passed |
| Initial backend invocation | Cached wpl-backend:dev, copied source | 0 backend cases executed; loader error | scripts import failed before tests |
| Snapshot visibility diagnostics | Cached backend image | Not a suite | PermissionError identified private 0700 temporary-directory traversal |
| Corrected isolated backend baseline | wpl-backend:dev a85bfdcf0a1f; offline, read-only source/root, tmpfs DB | 8 / 0 / 0 | Original cases passed in 10.456s |
| npm ci --no-audit --no-fund | Host Node 22.22.1/npm 9.2.0, temporary source, committed lock | Exit 0 | 172 packages installed |
| npm run build | Same disposable host environment | Exit 0 | TypeScript/Vite 8.2.1 build passed; bundle warning |
| npm run lint | Same disposable host environment | 7 errors, 2 warnings; exit 1 | Six conditional-hook errors and one unused parameter |
| Initial TS contract invocation | Host distro Node 22.22.1 | 0 contract cases executed | ERR_NO_TYPESCRIPT; runtime lacked compiled stripping support |
| Corrected URL/request contracts | Cached official Node image, offline snapshot | 19 / 0 / 0 | Docker runtime established as supported path |

The failed harness/runtime attempts were diagnosed rather than represented
as backend or frontend behavior regressions. No lockfile upgrades or lint
rule suppression were used.

## Final executed acceptance checks

First full runner command, executed from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py --prepare

That built the dedicated backend dependency image and passed 55 tests plus
build/lint. Review then added empty/skipped-suite and missing-image contracts.

Final command, again executed from /tmp:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

| Final runner group | Runtime / command | Passed / failed / skipped |
| --- | --- | --- |
| Runner failure/isolation contracts | Host Python 3.14.4; unittest discovery with zero/skip enforcement | 11 / 0 / 0 |
| Setup regressions | Host Python 3.14.4 and synthetic Compose parsing | 16 / 0 / 0 |
| Backend regressions and idle fixtures | Pinned Python 3.14 dependency image; isolated unittest discovery | 12 / 0 / 0 |
| Frontend URL/request contracts | Pinned Node 22 image; node --experimental-strip-types --test | 19 / 0 / 0 |
| Total | Same local/CI check entry point | 58 / 0 / 0 |
| Locked frontend install | npm --prefix /app/frontend ci --no-audit --no-fund | Exit 0; 170 packages |
| Production frontend build | npm --prefix /app/frontend run build | Exit 0; TypeScript/Vite 8.2.1 |
| Frontend lint | npm --prefix /app/frontend run lint | Exit 0; 0 errors, 2 existing warnings |
| Workflow validation | PyYAML BaseLoader in offline dependency image | YAML parsed; events/permissions/credential policy/shared command assertions passed |
| Diff whitespace review | git diff --check | Passed |

Exact runtime identities printed by both complete runs:

- Node: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
- Backend: wpl-p01-checks:899e64d57cc5c3eb,
  sha256:2eefbf13414a7abf8670d57cd33afb22887cee6a1e620c78d11bb252012ea028
- Backend base: python:3.14-slim,
  sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4

The host baseline used npm 9.2.0; final frontend checks use the pinned
container's npm. Different optional/platform package counts do not imply a
lockfile change; backend/requirements.txt and frontend/package-lock.json
remain unchanged.

## F01-F17 disposition

| ID | Disposition and evidence |
| --- | --- |
| F01 | Pass: all original 15 setup cases retained; final 16 pass, including preservation/adoption fixtures |
| F02 | Pass: all original 8 backend cases retained; final group has 12 passes and fixture-only migrations |
| F03 | Pass: relative /api on HTTP preserves host/port/prefix and derives ws |
| F04 | Pass: relative /api/ on HTTPS derives wss without duplicate join slash |
| F05 | Pass: absolute localhost APIs with/without prefix honored; explicit HTTP retained |
| F06 | Pass: HTTPS and encoded identifier/endpoint behavior covered |
| F07 | Pass: invalid schemes, credentials, base queries/fragments and external destinations rejected |
| F08 | Pass: leading/trailing join slashes preserve the configured prefix |
| F09 | Pass: missing/empty base explicitly tested and documented as same-origin /api |
| F10 | Pass: mocked session/fetch retain bearer, caller headers/body/method/signal/credentials and raw Response |
| F11 | Pass: missing token, session rejection, network failure and FormData behavior covered without provider calls |
| F12 | Pass: omitted backend default 35 and fresh setup fixture generates 35 |
| F13 | Pass: explicit 30/45 and process-over-file precedence in disposable copies |
| F14 | Pass: zero/negative/noninteger/empty idle values fail backend/setup validation |
| F15 | Pass: missing/failed/timed-out child, missing tool/image, empty and skipped Python suites fail nonzero |
| F16 | Pass: actual production build/lint exit zero; warnings disclosed |
| F17 | Pass within local scope: allowlist/exclusion/symlink tests, offline backend command assertions, synthetic fixture DB and reviewed container/build contexts |

## Unrun integration and remaining findings

Authenticated browser/provider smoke: NOT RUN; explicitly deferred by the
developer to Astra review. Existing services were not rebuilt/restarted with
this candidate and no disposable authenticated session/repo was arranged.
No login/settings/files/editor/Python stdin/Stop/GUI/Git push browser pass is
claimed. Existing protocol preservation is source-reviewed and supported by
focused contracts, not an end-to-end authenticated validation.

Optional real Docker/nginx smoke: NOT RUN. It remains separately opt-in and
uses existing development images/socket/host network, outside normal checks.
Remote GitHub Actions execution: NOT VERIFIED at report preparation; local
YAML validation and the shared command passed. A backup push may trigger CI;
its remote result must be reviewed separately rather than inferred.

No Supabase/GitHub/Resend account change, consent, student-repository mutation, GKE/cloud,
original deployment, live DB migration, DNS or TLS operation was performed.
No private env or active student file was read for these checks. There was
no byte-for-byte pre/post live-data comparison, so preservation is supported
by the scoped commands/isolation and source review, not a live-data audit.

Two pre-existing loadGitStatus exhaustive-deps warnings remain at App.tsx
lines 1159/1165 in this candidate. The frontend bundle remains approximately
801.66 kB (215.16 kB gzip), triggering the existing large-bundle warning.
Existing Starlette TestClient/httpx and legacy Docker-builder warnings remain.
No broad dependency/security upgrade or fresh audit claim is included.

Tenant/Postgres/RLS/jobs, trusted Git, safe file confinement, durable recovery,
distributed slots, repository sets, assessments, media and cloud deployment
remain later-phase work. Current known legacy risks from the planning audit
are not resolved by this local foundation.

## External effects, rollback and review

Effects: local temporary test files/containers, public dependency downloads,
and one dedicated labeled backend image retained as a cache. Normal test
containers use --rm; ownership cleanup completed without reported failure.
No existing application/student image tag or running service was changed.
No billable cloud resources or provider settings were created/upgraded.

Rollback only the explicitly listed P01 paths or revert the P01 checkpoint
commits after reviewing their contents. Do not use blanket git clean/reset,
delete untracked planning/attachments/work, or restart services for test rollback.
No data migration rollback exists. Remove cached test images only by verified
exact ID/label; never broadly prune Docker resources.

Astra should review F01-F17, this source manifest/narrow diff, cookie/upload/
terminal compatibility, offline isolation and CI policy, the two lint warnings,
remote CI if available, and the explicit smoke deferral. Accept or request
corrections before issuing P02. This report does not authorize P02 or certify
production readiness.

## Exact P01 file manifest

The following 24 files plus this report are the complete P01 change set.
Other previously untracked planning/reference/work files are excluded.
Hashes identify the tested implementation and final documentation candidate;
the report itself is omitted from hashing to avoid a recursive self-hash.

| Path | SHA-256 |
| --- | --- |
| AUTH_SETUP.md | 33b1e1e5fa83fbb1e0dab88eb4223ded9ee037a8cfcfac0dbf5e128c41777991 |
| README.md | f90a644688117bd25d48aebcb03cb52e300aee181ddf72c1918119d1cda9f375 |
| backend/.env.example | b66177f58f38b2345f1aaacca671f2d74dbf76db4c410ee65256cc46f90c4b44 |
| backend/app/config.py | 6457cf285ba564938fa4c93acec1109f4c98317833fa997356670b31d5eeb6c0 |
| docs/architecture.md | a409b9f0d9219f6a6883b17a87c073ba354b361be42017dbc2a8ea6772ef15d5 |
| docs/deployment.md | f020748c7fdedaddf477694c13285b0a2aa12d859a819225ec102d65e0aac75a |
| docs/setup.md | e752ff6d4ae703a949f969aa048c99be186cc4f06c2903c80c8ff3c1adbc6c94 |
| frontend/src/App.tsx | f76984cb50b14ef0deb457638e91bb7d784a9b38792aa9dc10f0c4567b555b3a |
| frontend/src/MULTI_USER_BACKEND_SETUP.md | 3c53b038c92d0e6f4d6f82683e2d70cac9ba35051d50dd2dd5aecbd6d5598901 |
| frontend/src/SettingsPanel.tsx | d72bc402250818b6072636d780c56e8f06763811313a398334a869cef69179ce |
| frontend/src/Terminal.tsx | d9fd8636bd94a90723faa41c9dd8467c5669708b140758d3127e5ea593f0ae87 |
| scripts/setup.py | 9c547e1e9a9aa0731b12348a16a66fe85ea7e6a1ba4ba8b416da6c6dfc8ff0b3 |
| scripts/test_setup.py | 8490014757f4e308c65ba5d7ec57f497bb469f9ac970fad5f970f4aeaed51ac4 |
| .github/workflows/checks.yml | f2aa5015178e55caeaa1edb3e99cffbb0dfd089ee6bbcb790ccfcb86d648dbf8 |
| docs/development.md | b209c3c8d31fd7a1b0b4cf0ac9518db5a4574307dbcb2891cbaf664bd7f756ec |
| frontend/src/lib/api.ts | ec41ee3f3a2877051997a9886c9e797997f44171f36e985de0bead7116371171 |
| frontend/src/lib/apiClient.ts | b26f5e6971f284650b3c232077092da1f8aa85984d6dc21f4ae97327fcf9a603 |
| frontend/src/lib/apiUrls.ts | 2cdb88476f9c48d25f858c9f4a24148f659ade730cb730c797d987ea9ea4aab0 |
| frontend/tests/apiClient.test.mjs | a2db436198e49da1d1f16b20aefd5485a347e792e6ec1d91df1dff4010296d5d |
| frontend/tests/apiUrls.test.mjs | 9d8493e55acc6e50b9eec250eafd9efb39f53ded5a1e014fcb19fde6b81b2a8f |
| scripts/Dockerfile.checks | 66be1c27573578c4d4c1765ce59b24cd2ea2befbb18d3fa0624ae52e8727f447 |
| scripts/check_local.py | 645643971095fd67cae89c3ee1b1e68edb3fa02d00170b91df7b7071d880bdc9 |
| scripts/test_check_local.py | 0e9ca6a5c517772d9b7fbb8ec201b8220a7bde0f5afb5783c6ff5b44894b547b |
| scripts/test_idle_defaults.py | e760654a2df9fc463e9932d08a64d9f5725cfc08c71ca3c3ddde1dae703918ee |

## Checkpoint receipts

```
13d2d1618321b99b14fbe4690356abc33fca89a8 Centralize frontend API URLs and authenticated requests
e40f88c590fb6418ad7b857baac9dc101ea5ed59 Default new labs to 35 idle minutes while preserving overrides
```

Final ownership inventory: no wpl.check.run containers remained.
The final runner/CI/docs checkpoint is the commit containing this report.
