import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { run } from "node:test";
import { spec } from "node:test/reporters";
import { pipeline } from "node:stream/promises";

/** Require real registered-test completion, never a synthetic file-import pass. */
export function createResultPolicy(files) {
  const expected = new Set(files.map((file) => resolve(file)));
  if (!files.length || expected.size !== files.length) {
    throw new Error("Mandatory frontend modules must be nonempty and unique.");
  }
  const summaries = new Map();
  const errors = [];
  let overall;
  let sawFailure = false;

  function validate(summary, label) {
    const counts = summary?.counts;
    const keys = ["tests", "passed", "failed", "cancelled", "skipped", "todo"];
    if (!counts || keys.some((key) =>
      !Number.isInteger(counts[key]) || counts[key] < 0)) {
      errors.push(label + ": invalid or incomplete test counts.");
      return;
    }
    if (counts.tests === 0) errors.push(label + ": no registered tests.");
    if (summary.success !== true || counts.passed !== counts.tests ||
        ["failed", "cancelled", "skipped", "todo"].some((key) => counts[key] !== 0)) {
      errors.push(label + ": rejected outcomes " + JSON.stringify(counts));
    }
  }

  return {
    observe(event) {
      if (event.type === "test:fail") sawFailure = true;
      if (event.type !== "test:summary") return;
      const data = event.data;
      if (typeof data?.file === "string") {
        const file = resolve(data.file);
        if (!expected.has(file)) {
          errors.push("Unexpected completed module: " + file);
        } else if (summaries.has(file)) {
          errors.push("Duplicate completed module: " + file);
        } else {
          summaries.set(file, data);
        }
      } else if (data && data.file === undefined) {
        if (overall) errors.push("Duplicate cumulative test summary.");
        overall = data;
      } else {
        errors.push("Malformed test summary.");
      }
    },
    finish() {
      for (const file of expected) {
        const summary = summaries.get(file);
        if (!summary) errors.push("Missing completed registered-test summary: " + file);
        else validate(summary, file);
      }
      if (!overall) errors.push("Missing cumulative test summary.");
      else validate(overall, "Cumulative summary");
      if (sawFailure) errors.push("A test assertion, loader or execution failed.");
      if (overall && summaries.size === expected.size) {
        const registered = [...summaries.values()]
          .reduce((sum, summary) => sum + (summary.counts?.tests ?? 0), 0);
        if (registered !== overall.counts?.tests) {
          errors.push("Cumulative count differs from completed registered tests.");
        }
      }
      if (errors.length) throw new Error(errors.join("\n"));
      return { tests: overall.counts.tests, modules: expected.size };
    },
  };
}

export async function runMandatoryTests(files) {
  const resolved = files.map((file) => resolve(file));
  const policy = createResultPolicy(resolved);
  // Execute this harness as a file, not node -e: Node inherits parent exec flags.
  await pipeline(
    run({ files: resolved, concurrency: false, isolation: "process" }),
    async function* observe(source) {
      for await (const event of source) {
        policy.observe(event);
        yield event;
      }
    },
    new spec(),
    process.stdout,
    { end: false },
  );
  // Flush original diagnostics before evaluating the stricter result policy.
  const result = policy.finish();
  console.log("FRONTEND POLICY PASS: " + result.tests +
    " registered tests across " + result.modules + " modules.");
  return result;
}

if (process.argv[1] &&
    import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    await runMandatoryTests(process.argv.slice(2));
  } catch (error) {
    console.error("FRONTEND POLICY FAIL:", error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
