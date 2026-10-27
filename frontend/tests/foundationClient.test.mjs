import assert from "node:assert/strict";
import test from "node:test";
import { createFoundationClient, FoundationApiError } from "../src/features/foundation/client.ts";
import { createApiUrls } from "../src/lib/apiUrls.ts";
import { createApiFetch } from "../src/lib/apiClient.ts";

const org = "11111111-1111-4111-8111-111111111111";
const user = "22222222-2222-4222-8222-222222222222";
const member = "33333333-3333-4333-8333-333333333333";
const target = "44444444-4444-4444-8444-444444444444";
const jobId = "55555555-5555-4555-8555-555555555555";
const transfer = "66666666-6666-4666-8666-666666666666";
const time = "2026-10-27T00:00:00+00:00";
const me = { user: { id: user, full_name: "", global_state: "pending", version: 1, access_epoch: 1 },
  memberships: { items: [], next_cursor: null }, capabilities: [] };
const organization = { id: org, name: "Synthetic school", organization_type: "school", status: "pending", version: 3,
  home_region: "fixture", created_at: time, updated_at: time, access_epoch: 2, contact_email: "contact@example.invalid", primary_admin_membership_id: member };
const create = { org_id: org, primary_admin_membership_id: member, status: "pending", invitation_status: "pending",
  job_id: jobId, delivery_status: "pending_integration", version: 1 };
const preview = { transfer_id: transfer, org_id: org, from_membership_id: member, to_membership_id: target,
  expected_version: 3, expires_at: time, confirmation: "synthetic-one-use-confirmation", former_primary_retains_admin: true, operation: "transfer" };
const completion = { transfer_id: transfer, org_id: org, primary_admin_membership_id: target, version: 4,
  access_epoch: 3, status: "active", job_id: jobId, delivery_status: "pending_integration" };
const job = { job_id: jobId, kind: "deliver_primary_invitation", state: "queued", delivery_status: "pending_integration",
  attempts: 0, max_attempts: 5, last_error_code: null, created_at: time, updated_at: time };
const form = { name: "Synthetic school", organization_type: "school", contact_email: "contact@example.invalid",
  primary_admin_email: "primary@example.invalid", home_region: "fixture", reason: "Synthetic creation reason" };
const answer = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), { status, headers });
function fixture(handler, base = "/api", origin = "https://page.example.invalid") {
  const calls = []; let sessions = 0;
  const urls = createApiUrls(base, origin);
  const apiFetch = createApiFetch(urls.requestUrl, async () => { sessions++; return { data: { session: { access_token: "synthetic-signed-token" } } }; },
    async (url, init) => { calls.push({ url, init }); return handler(url, init, calls.length); }, { credentials: "include" });
  return { client: createFoundationClient(urls, apiFetch), calls, sessions: () => sessions };
}

test("foundation production me caller keeps default/custom API prefixes and P01 bearer/cookie defaults", async () => {
  for (const [base, expected] of [[undefined, "https://page.example.invalid/api/v1/me"], ["/api/", "https://page.example.invalid/api/v1/me"],
    ["https://api.example.invalid/prefix/", "https://api.example.invalid/prefix/v1/me"], ["http://localhost:8000", "http://localhost:8000/v1/me"]]) {
    const f = fixture(() => answer(me), base);
    assert.deepEqual(await f.client.me(), me);
    assert.equal(f.calls[0].url, expected);
    assert.equal(f.calls[0].init.headers.get("Authorization"), "Bearer synthetic-signed-token");
    assert.equal(f.calls[0].init.credentials, "include");
    assert.equal(f.calls[0].init.body, undefined);
  }
});

test("pending identity and multi-role summaries retain server meaning without email/profile authority or secret extras", async () => {
  const response = { ...me, user: { ...me.user, verified_email: "must-not-project@example.invalid" },
    memberships: { items: [{ id: member, org_id: org, status: "invite_pending", version: 2, created_at: time,
      organization_name: "Synthetic school", organization_status: "pending", roles: ["admin", "student"], can_enter: false }], next_cursor: "cursor" } };
  const f = fixture(() => answer(response)); const result = await f.client.me();
  assert.equal(result.user.global_state, "pending");assert.deepEqual(result.capabilities, []);
  assert.equal(result.memberships.items[0].can_enter, false);
  assert.deepEqual(result.memberships.items[0].roles, ["admin", "student"]);
  assert.equal(Object.hasOwn(result.user, "verified_email"), false);
});

test("directory caller encodes literal filters/cursors and bounded pages while detail and tenant projections stay distinct", async () => {
  const f = fixture((url) => answer(url.includes("?") ? { items: [organization], next_cursor: "synthetic cursor" } : organization));
  const page = await f.client.organizations({ search: "A&B % school", cursor: "a+b/=", status: "pending", organization_type: "school" });
  const url = new URL(f.calls[0].url);
  assert.equal(url.pathname, "/api/v1/platform/organizations");assert.equal(url.searchParams.get("limit"), "50");
  assert.equal(url.searchParams.get("search"), "A&B % school");assert.equal(url.searchParams.get("cursor"), "a+b/=");
  assert.equal(Object.hasOwn(page.items[0], "contact_email"), false);
  assert.equal((await f.client.organization(org)).contact_email, organization.contact_email);
  const hidden = fixture(() => answer({ id: org, name: organization.name, organization_type: "school", home_region: "fixture", status: "active", version: 3, access_epoch: 2 }));
  assert.equal((await hidden.client.tenantOrganization(org)).primary_admin_membership_id, undefined);
});

test("member selection caller preserves scoped roles/pending placeholders and sends only bounded pagination", async () => {
  const row = { id: member, user_id: null, status: "invite_pending", version: 1, created_at: time, full_name: null, roles: ["admin"] };
  const f = fixture(() => answer({ items: [row], next_cursor: null }));
  assert.deepEqual(await f.client.members(org, "cursor+value"), { items: [row], next_cursor: null });
  const url = new URL(f.calls[0].url);assert.equal(url.pathname, `/api/v1/orgs/${org}/members`);
  assert.equal(url.searchParams.get("limit"), "100");assert.equal(url.searchParams.get("cursor"), "cursor+value");
});

test("create caller retains supplied retry key/body, projects only approved fields and preserves committed replay flag", async () => {
  const f = fixture((_url, _init, count) => answer({ ...create, activation_token: "must-not-project" }, 201, { "Idempotency-Replayed": count === 1 ? "false" : "true" }));
  const first = await f.client.createOrganization({ ...form, actor_id: user, platform_role: "admin" }, "stable-synthetic-key");
  const next = await f.client.createOrganization(form, "stable-synthetic-key");
  assert.deepEqual(first.data, create);assert.deepEqual(first.data, next.data);
  assert.equal(first.replayed, false);assert.equal(next.replayed, true);
  for (const call of f.calls) {
    assert.deepEqual(JSON.parse(call.init.body), form);
    assert.equal(call.init.headers.get("Idempotency-Key"), "stable-synthetic-key");
    assert.equal(call.init.headers.get("Content-Type"), "application/json");
  }
  assert.equal(f.calls[0].init.body, f.calls[1].init.body);
});

test("transfer and recovery preview callers select explicit routes and keep version/target/reason bound", async () => {
  const body = { target_membership_id: target, expected_version: 3, reason: "Synthetic transfer reason" };
  const f = fixture((url) => answer({ ...preview, operation: url.includes("recovery") ? "recovery" : "transfer" }));
  assert.equal((await f.client.previewTransfer(org, { ...body, actor_id: user })).operation, "transfer");
  assert.equal((await f.client.previewRecovery(org, body)).operation, "recovery");
  assert.equal(new URL(f.calls[0].url).pathname, `/api/v1/orgs/${org}/primary-admin-transfers/preview`);
  assert.equal(new URL(f.calls[1].url).pathname, `/api/v1/platform/organizations/${org}/primary-admin-recovery/preview`);
  for (const call of f.calls) { assert.deepEqual(JSON.parse(call.init.body), body);assert.equal(call.init.headers.get("If-Match"), '"3"'); }
});

test("confirmation callers send only one-use preview/version/confirmation with If-Match and decode fixed replay receipts", async () => {
  const body = { transfer_id: transfer, expected_version: 3, confirmation: preview.confirmation };
  const f = fixture(() => answer({ ...completion, confirmation_hash: "not-public" }, 200, { "Idempotency-Replayed": "true" }));
  for (const method of ["confirmTransfer", "confirmRecovery"]) {
    const result = await f.client[method](org, { ...body, target_membership_id: member });
    assert.deepEqual(result, { data: completion, replayed: true });
  }
  for (const call of f.calls) { assert.deepEqual(JSON.parse(call.init.body), body);assert.equal(call.init.headers.get("If-Match"), '"3"'); }
  assert.match(f.calls[0].url, /primary-admin-transfers$/);assert.match(f.calls[1].url, /primary-admin-recovery$/);
});

test("job callers retain pending/simulated/provider accepted distinctions and remove payload/lease/token extras", async () => {
  for (const mode of ["pending_integration", "simulated", "provider_accepted"]) {
    const f = fixture(() => answer({ ...job, delivery_status: mode, private_payload_id: transfer, activation_token: "not-public", lease_owner: user }));
    for (const method of ["initialJob", "tenantJob", "recoveryJob"]) {
      const result = await f.client[method](org, jobId);assert.deepEqual(result, { ...job, delivery_status: mode });
      assert.equal(Object.hasOwn(result, "activation_token"), false);
    }
    assert.match(f.calls[0].url, /platform\/organizations/);assert.match(f.calls[1].url, /v1\/orgs/);assert.match(f.calls[2].url, /primary-admin-recovery\/jobs/);
  }
});

test("invalid record IDs and retry keys fail before authentication lookup or fetch", () => {
  const f = fixture(() => answer(me));
  for (const id of ["../org", "https://foreign.example.invalid", "bad%2fpath", "00000000-0000-0000-0000-000000000000"]) {
    assert.throws(() => f.client.organization(id), TypeError);assert.throws(() => f.client.tenantJob(org, id), TypeError);
  }
  for (const key of ["", "bad key", "x".repeat(129)]) assert.throws(() => f.client.createOrganization(form, key), TypeError);
  assert.equal(f.sessions(), 0);assert.equal(f.calls.length, 0);
});

test("HTTP errors preserve code/status/field names/request ID while discarding raw provider or SQL diagnostics", async () => {
  for (const [status, code] of [[401,"invalid_identity"],[403,"forbidden"],[409,"version_conflict"],[409,"recent_auth_required"],[422,"validation_error"],[503,"data_unavailable"]]) {
    const f = fixture(() => answer({ code, message: "private raw diagnostic secret", request_id: "a".repeat(32),
      field_errors: { "body.reason": "secret input", "unsafe key": "ignore" } }, status));
    await assert.rejects(f.client.me(), (error) => {
      assert.ok(error instanceof FoundationApiError);assert.equal(error.status, status);assert.equal(error.code, code);
      assert.equal(error.requestId, "a".repeat(32));assert.deepEqual(error.fields, { "body.reason": "Invalid value." });
      assert.doesNotMatch(error.message, /private|diagnostic|secret/);return true;
    });
  }
});

test("malformed successes, invalid states and missing replay evidence cannot be reported as success", async () => {
  for (const value of [null, [], {}, { ...me, user: { ...me.user, global_state: "approved" } }, { ...me, capabilities: ["superuser"] }]) {
    const f = fixture(() => answer(value));await assert.rejects(f.client.me(), { code: "invalid_response" });
  }
  const malformed = fixture(() => new Response("not-json"));await assert.rejects(malformed.client.me(), { code: "invalid_response" });
  const missing = fixture(() => answer(create, 201));await assert.rejects(missing.client.createOrganization(form, "valid-key"), { code: "invalid_response" });
  const queued = fixture(() => answer(create, 202, { "Idempotency-Replayed": "false" }));await assert.rejects(queued.client.createOrganization(form, "valid-key"), { code: "invalid_response" });
  const invalidJob = fixture(() => answer({ ...job, delivery_status: "delivered" }));await assert.rejects(invalidJob.client.initialJob(org, jobId), { code: "invalid_response" });
});

test("abort signals propagate and network failures get fixed redacted messages without response details", async () => {
  const controller = new AbortController();const failure = new DOMException("Synthetic abort", "AbortError");
  const f = fixture((_url, init) => { assert.equal(init.signal, controller.signal);throw failure; });
  await assert.rejects(f.client.me(controller.signal), (error) => error === failure);
  const network = fixture(() => { throw new Error("private transport/provider detail"); });
  await assert.rejects(network.client.me(), (error) => error.code === "network_unavailable" && !error.message.includes("private"));
});
