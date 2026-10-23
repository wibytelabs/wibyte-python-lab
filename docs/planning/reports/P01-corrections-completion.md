# P01 corrections completion report

Date: 23 October 2026, Asia/Kolkata.
Status: P01-R1/P01-R2 implemented and locally verified; awaiting Astra re-review.
P02 has not been prepared or implemented.

## Identity and scope

Reviewed baseline: f7bc5c4185c4093e6324128766728d492957b77d.
Branch: codex/p01-foundation, intentional wibytelabs development replica.
Initial tracked checkout was clean. Unrelated untracked planning, review/handoff,
attachments and work/ archives were preserved and excluded from staging.

The developer applied patches and executed commands through the agreed
terminal copy/paste workflow. Evidence below is their actual returned output,
reviewed with source/diff; it is not an independently rerun assistant suite.
Only the two findings in P01-corrections-f7bc5c4.md were corrected.
Original P01 completion/review evidence remains intact. Backend code/config,
requirements, package lock, workflow and runtime Dockerfiles did not change.

## P01-R1 production public lookup

LoginScreen binds createAccountLookup from frontend/src/lib/accountLookup.ts.
Signup and confirmation resend both use that binding (candidate lines 202/106).
Ordinary sign-in/reset and surrounding Supabase signup/resend logic are unchanged.

The production helper accepts API base, page origin and injected fetch. It uses
the existing createApiUrls resolver and joins /auth/account-status. Missing or
empty base uses same-origin /api/auth/account-status. Relative/absolute prefixes
normalize; explicit localhost without /api retains standalone addressing.

The public POST still sends JSON {email} and Content-Type application/json.
There is no Supabase import/session lookup, bearer injection, password payload
or credentials-policy override. The new/confirmed/unconfirmed status allowlist,
HTTP detail/fallback error, malformed-body error and fetch rejection retain
their original meaning. Tests execute this actual production helper.

| C01 behavior | Executed evidence |
| --- | --- |
| Missing/empty base on HTTP and HTTPS | Exact same-origin /api/auth/account-status |
| /api/ and trailing absolute HTTPS prefix | One separator, retained prefix |
| Explicit localhost without /api | Configured backend /auth/account-status |
| Successful status allowlist | new/confirmed/unconfirmed preserved |
| HTTP errors and malformed/invalid bodies | Original meaningful errors retained |
| Public request and network rejection | Email-only JSON, no auth/cookie override; rejection propagated |

All 13 focused lookup cases passed. Both real caller bindings were source-reviewed;
no real signup/resend email or provider operation was performed.

## P01-R2 mandatory frontend result policy

scripts/run_frontend_tests.mjs executes the Node test API with process isolation,
forwards the built-in spec diagnostics, then applies a stricter result policy.
Each requested module must emit a completed per-file test:summary with positive
registered-test count, all tests passed and zero failures/skips/TODOs/cancellations.
One cumulative summary must agree with the registered module counts.
Failure events and missing/duplicate/unexpected summaries are rejected.
No fixed test count is embedded in the guard.

The actual pinned image was probed. Registered tests produce per-file and
cumulative summaries; an empty module can produce a synthetic file pass without
a registered-test per-file summary. Such file-wrapper success is insufficient.
Two exploratory inline node -e probes yielded wrapper-only output and were
discarded as policy evidence. Node inherits parent eval flags; extra execArgv
does not replace them. The corrected file-based probe showed the real outcome
events. The delivered harness likewise executes as a file, not inline eval.

FRONTEND_TESTS declares apiUrls.test.mjs, apiClient.test.mjs,
accountLookup.test.mjs and frontendPolicy.test.mjs once. Prerequisites check
them; snapshot copying includes all four. FILES explicitly allowlists the new
harness. The actual frontend stage invokes it rather than bare node --test.
A rejected outcome propagates nonzero through run_container/run_checked/main
and prevents the global PASS statement.

| C02 behavior | Executed evidence |
| --- | --- |
| Passing cases/stdout/stderr | Accepted; original diagnostics retained |
| Pass plus skip; runtime t.skip; TODO | Synthetic stage fails nonzero, no frontend policy PASS |
| Assertion/module-load failure | Nonzero with original diagnostic markers |
| Cancellation and Node test timeout | Rejected with execution diagnostics |
| Empty module beside passing module; empty suite | Cannot satisfy registered-case coverage |
| Early process.exit(0) | Missing registered completion rejected |
| Variable case counts | Accepted without a fixed-count guard |
| Missing cumulative summary/inflated wrapper count | Rejected by policy tests |
| Overall runner rejection | Host tests inject rejection; main returns 1 without global PASS |
| Failure/timeout cleanup | Mocked command tests retain offline flags, error propagation and inspected-owned-ID cleanup |

Synthetic child failures/skips are expected inputs to passing policy tests, not
skips/failures of the real mandatory cases. Failed/timed-out container cleanup
was exercised through mocked command responses; actual focused/full containers
completed normal ownership cleanup. No live service was intentionally timed out.

## Commands and results

Initial production-helper focus:

    python3 /tmp/wpl-p01-r1-focused-4zr1n103.py

13 passed, zero failed/skipped/cancelled, in an offline disposable source copy.

Combined focused correction command:

    python3 /tmp/wpl-p01-corrections-focused-7d3cctuy.py

14 runner tests passed; Node harness syntax validation passed; 27 frontend
correction tests passed across 2 modules with zero failed/cancelled/skipped/TODO.
Synthetic rejection and diagnostic-preservation assertions passed.

Full entry point, executed from /tmp without --prepare:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/wibyte/wibyte-python-lab/scripts/check_local.py

| Final group/check | Actual result |
| --- | --- |
| Runner failure/isolation contracts | 14 passed, zero failures/skips |
| Setup regressions | 16 passed, zero failures/skips |
| Backend/idle regressions | 12 passed, zero failures/skips |
| Mandatory frontend contracts | 46 passed across 4 modules; zero failed/cancelled/skipped/TODO |
| Total | 88 passed; zero failed/skipped mandatory cases |
| npm ci --no-audit --no-fund | Exit 0; 170 packages in disposable copy |
| Production build: tsc -b and vite build | Exit 0; Vite 8.2.1, 87 modules transformed |
| npm run lint | Exit 0; zero errors, 2 existing warnings |
| git diff --check | Passed |
| Requirements/lockfile/workflow unchanged check | Passed |
| Offline PyYAML CI/source-policy assertions | Passed: permitted events, contents:read, no persisted credentials/secrets, same runner command |

Host Python 3.14.4 is the established setup/runner interpreter. Runtime
identities printed by this full run:

- Node: sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
- Backend: wpl-p01-checks:899e64d57cc5c3eb,
  sha256:2eefbf13414a7abf8670d57cd33afb22887cee6a1e620c78d11bb252012ea028

Cached runtimes were reused. No application or dependency image rebuild was
required. The previous 58-pass run remains historical evidence, not silently
relabeled as this 88-pass correction run.

## Isolation, warnings and limitations

Allowlisted snapshots remain disposable and exclude private env, live DB, .git,
credentials, backups and work/. New helper/test/harness inclusion was exercised
in focused and full runs. Backend tests retain synthetic /tmp DB, network none,
no socket, read-only root/source and bounded writable tmpfs. Frontend contracts,
build and lint remain offline; only locked npm install has network access.
Clean env, synthetic Vite settings, resource limits, outer timeouts and
ownership-checked cleanup are preserved. Policy fixtures use temporary dirs.

No private env, live DB, running service, student repository, application
provider setting, original labs.wibyte.in deployment, cloud resource or
application image was modified. No live-data byte-comparison audit is claimed.
Only authorized source-code checkpoint/backup operations follow these tests.

Two existing App.tsx exhaustive-deps warnings remain at lines 1159/1165 for
loadGitStatus. The large-bundle warning remains: approximately 801.77 kB,
215.19 kB gzip. Existing TestClient/httpx deprecation remains. None was
suppressed or expanded into unrelated cleanup/dependency upgrades.

Authenticated browser/provider smoke: NOT RUN; explicit deferral accepted in
Astra's previous review and not relabeled passed.
Optional Docker/nginx smoke: NOT RUN.
Remote Actions execution: NOT VERIFIED in this report. Local YAML validation
is separate evidence; a backup push may trigger CI. No remote CI success or
production/provider readiness is implied.

## New checkpoint and exact changed paths

The implementation commit below contains the eight tested code/test/guide
paths. A following report-only commit records the evidence. The final review
target is the commit containing this report, resolved with:

    git log -1 -- docs/planning/reports/P01-corrections-completion.md

Its own self-SHA is not embedded recursively. Source hashes identify the exact
tested candidate; the report itself is excluded from its own hash manifest.

Implementation commit: 370516e2dc08f401147b52a8fa75847864035bba

Final inventory: zero wpl.check.run test containers remained.

| Changed path | SHA-256 |
| --- | --- |
| docs/development.md | e8c3b11f9d7a3adac42eec581b7ed6c4c8fe7dc5e2067f465fde8715bfc16fff |
| frontend/src/LoginScreen.tsx | 441ce8b3c7a02d6d08f5726966449ad1abf2c26799dca8fd27ef6ef5d594ae97 |
| frontend/src/lib/accountLookup.ts | 1d7c001908f3b1a11001123f81c9b06596d1eedaf5c02b0caf4b80d8b56d5186 |
| frontend/tests/accountLookup.test.mjs | 2595d513bdb732ee713e754ebefafbe57e149642bbdeacb362a8f1ecf6ca6599 |
| frontend/tests/frontendPolicy.test.mjs | 393e583cb39031e842be9b76223234da9ea2db5681471f2a784da6b4593d16ea |
| scripts/check_local.py | 5a8bcd728e33b2914386598ca69bdcaed8801f8d81e75d7f2b37bee0b258beb5 |
| scripts/run_frontend_tests.mjs | 3d00859ebfbdd92a530bd37c74c1f7c0ed38b1a4d101097064b6935b66143e26 |
| scripts/test_check_local.py | 455478b1cd29c6088d5ad686f3d8952239bb9ddc1ca17292ec39a568bb619be3 |
| docs/planning/reports/P01-corrections-completion.md | This report; self-hash omitted |

Implementation diff from reviewed baseline:

    docs/development.md                    |  26 ++++++++
     frontend/src/LoginScreen.tsx           |  28 ++-------
     frontend/src/lib/accountLookup.ts      |  33 ++++++++++
     frontend/tests/accountLookup.test.mjs  |  82 +++++++++++++++++++++++++
     frontend/tests/frontendPolicy.test.mjs |  92 ++++++++++++++++++++++++++++
     scripts/check_local.py                 |  26 +++++---
     scripts/run_frontend_tests.mjs         | 107 +++++++++++++++++++++++++++++++++
     scripts/test_check_local.py            |  50 +++++++++++++++
     8 files changed, 414 insertions(+), 30 deletions(-)

Rollback only the reviewed correction implementation/report commits. Do not reset/clean unrelated work or restart services. There is no live-data migration or data rollback.

Astra should recheck C01 production callers/public behavior, C02 registered summaries/rejection/diagnostics/cleanup, retained F01-F17 regressions and explicit integration limits. Acceptance remains with Astra. Stop before P02.
