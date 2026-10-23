import assert from "node:assert/strict";
import test from "node:test";
import { createAccountLookup } from "../src/lib/accountLookup.ts";

const cases = [
  [undefined, "http://localhost:8080", "http://localhost:8080/api/auth/account-status"],
  [undefined, "https://page.example.invalid", "https://page.example.invalid/api/auth/account-status"],
  ["", "http://localhost:8080", "http://localhost:8080/api/auth/account-status"],
  ["", "https://page.example.invalid", "https://page.example.invalid/api/auth/account-status"],
  ["/api/", "https://page.example.invalid", "https://page.example.invalid/api/auth/account-status"],
  ["https://api.example.invalid/prefix/", "https://page.example.invalid", "https://api.example.invalid/prefix/auth/account-status"],
  ["http://localhost:8000", "http://localhost:8080", "http://localhost:8000/auth/account-status"],
];
const answer = (body, status = 200) => new Response(JSON.stringify(body), { status });

for (const [base, page, expected] of cases) {
  test("production public lookup URL: " + String(base) + " from " + page, async () => {
    let actual;
    const lookup = createAccountLookup(base, page, async (input) => {
      actual = input;
      return answer({ status: "new" });
    });
    assert.equal(await lookup("fixture@example.invalid"), "new");
    assert.equal(actual, expected);
  });
}

test("production lookup accepts new/confirmed/unconfirmed without changing their meaning", async () => {
  for (const status of ["new", "confirmed", "unconfirmed"]) {
    const lookup = createAccountLookup("/api", "https://page.example.invalid",
      async () => answer({ status }));
    assert.equal(await lookup("fixture@example.invalid"), status);
  }
});

test("production lookup stays public and sends only the JSON email", async () => {
  const calls = [];
  const lookup = createAccountLookup("/api", "https://page.example.invalid",
    async (...args) => { calls.push(args); return answer({ status: "new" }); });
  await lookup("fixture@example.invalid");
  const [, init] = calls[0];
  assert.equal(init.method, "POST");
  assert.deepEqual(JSON.parse(init.body), { email: "fixture@example.invalid" });
  assert.equal(new Headers(init.headers).get("Content-Type"), "application/json");
  assert.equal(new Headers(init.headers).has("Authorization"), false);
  assert.equal(Object.hasOwn(init, "credentials"), false);
  assert.deepEqual(Object.keys(init).sort(), ["body", "headers", "method"]);
});

test("production lookup preserves meaningful HTTP errors and fallback errors", async () => {
  for (const [body, message] of [
    [{ detail: "synthetic-rate-limit" }, "synthetic-rate-limit"],
    [{ detail: {} }, "Unable to check your account. Please try again."],
  ]) {
    const lookup = createAccountLookup("/api", "https://page.example.invalid",
      async () => answer(body, 429));
    await assert.rejects(lookup("fixture@example.invalid"), { message });
  }
});

test("production lookup rejects malformed JSON and invalid/missing statuses", async () => {
  for (const body of ["not json", "null", "[]", "{}", '{"status":"admin"}', '{"status":null}']) {
    const lookup = createAccountLookup("/api", "https://page.example.invalid",
      async () => new Response(body));
    await assert.rejects(lookup("fixture@example.invalid"),
      { message: "Unable to check your account. Please try again." });
  }
});

test("production lookup propagates fetch rejection", async () => {
  const failure = new Error("synthetic-network-failure");
  const lookup = createAccountLookup("/api", "https://page.example.invalid",
    async () => { throw failure; });
  await assert.rejects(lookup("fixture@example.invalid"), (error) => error === failure);
});

test("invalid configured base is rejected before any public fetch", () => {
  let called = false;
  assert.throws(() => createAccountLookup("ftp://example.invalid",
    "https://page.example.invalid", async () => { called = true; return new Response(); }));
  assert.equal(called, false);
});
