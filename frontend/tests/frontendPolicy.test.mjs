import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createResultPolicy } from "../../scripts/run_frontend_tests.mjs";

const harness = fileURLToPath(new URL("../../scripts/run_frontend_tests.mjs", import.meta.url));
const passing = "import test from 'node:test'; test('synthetic-pass', () => {});";

function execute(sources) {
  const directory = mkdtempSync(join(tmpdir(), "wpl-frontend-policy-"));
  try {
    const files = sources.map((source, index) => {
      const path = join(directory, "fixture-" + index + ".mjs");
      writeFileSync(path, source);
      return path;
    });
    const result = spawnSync(process.execPath,
      ["--experimental-strip-types", harness, ...files], {
        cwd: directory,
        // Do not inherit the parent test worker's NODE_TEST_CONTEXT/flags.
        env: {
          PATH: process.env.PATH || "/usr/local/bin:/usr/bin:/bin",
          HOME: directory, TMPDIR: directory, LANG: "C.UTF-8",
        },
        encoding: "utf8", timeout: 5000, maxBuffer: 1024 * 1024,
      });
    assert.ifError(result.error);
    return { ...result, output: result.stdout + result.stderr };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("passing modules retain registered-case and stdout/stderr diagnostics", () => {
  const result = execute([
    passing + "console.log('synthetic-stdout-marker'); console.error('synthetic-stderr-marker');",
  ]);
  assert.equal(result.status, 0, result.output);
  for (const marker of ["synthetic-pass", "synthetic-stdout-marker", "synthetic-stderr-marker",
    "FRONTEND POLICY PASS:"]) assert.ok(result.output.includes(marker), result.output);
});

const rejected = [
  ["skip plus pass", passing + "test.skip('synthetic-skip', () => {});", /skipped/],
  ["runtime skip", "import test from 'node:test'; test('dynamic-skip', t => t.skip('synthetic-skip'));", /skipped/],
  ["TODO", "import test from 'node:test'; test.todo('synthetic-todo');", /todo/],
  ["assertion failure", "import test from 'node:test'; import assert from 'node:assert/strict'; test('synthetic-failure', () => assert.fail('synthetic-assertion-marker'));", /synthetic-assertion-marker/],
  ["module load failure", "import './synthetic-missing-module.mjs';", /synthetic-missing-module/],
  ["cancelled test", "import test from 'node:test'; test('synthetic-pending', () => new Promise(() => {}));", /pending|cancelled/],
  ["empty module beside passing module", "export const synthetic = true;", /Missing completed registered-test summary/],
  ["empty suite", "import {describe} from 'node:test'; describe('synthetic-empty-suite', () => {});", /registered/],
  ["early successful process exit", "import test from 'node:test'; test('not-executed', () => {}); process.exit(0);", /Missing completed registered-test summary/],
  ["test timeout", "import test from 'node:test'; test('synthetic-timeout', {timeout: 30}, async t => { const timer=setInterval(() => {}, 1000); t.after(() => clearInterval(timer)); await new Promise(() => {}); });", /timed out|timeout/],
];
for (const [name, source, diagnostic] of rejected) {
  test("mandatory result policy rejects " + name, (context) => {
    const result = execute([passing, source]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, diagnostic);
    assert.match(result.output, /FRONTEND POLICY FAIL:/);
    assert.doesNotMatch(result.output, /FRONTEND POLICY PASS:/);
    context.diagnostic("Synthetic " + name + ": rejected, original diagnostic preserved.");
  });
}

test("variable registered-test counts succeed without a fixed expected count", () => {
  const result = execute([passing, passing + "test('another-case', () => {});"]);
  assert.equal(result.status, 0, result.output);
  assert.match(result.output, /FRONTEND POLICY PASS: 3 registered tests across 2 modules/);
});

const counts = { tests: 1, passed: 1, failed: 0, cancelled: 0, skipped: 0, todo: 0 };
test("incomplete event stream without cumulative completion is rejected", () => {
  const file = resolve("/synthetic/contract.mjs");
  const policy = createResultPolicy([file]);
  policy.observe({ type: "test:summary", data: { file, success: true, counts } });
  assert.throws(() => policy.finish(), /Missing cumulative test summary/);
});

test("synthetic file-wrapper counts cannot inflate registered coverage", () => {
  const file = resolve("/synthetic/contract.mjs");
  const policy = createResultPolicy([file]);
  policy.observe({ type: "test:summary", data: { file, success: true, counts } });
  policy.observe({ type: "test:summary", data: {
    success: true, counts: { ...counts, tests: 2, passed: 2 },
  } });
  assert.throws(() => policy.finish(), /Cumulative count differs/);
});
