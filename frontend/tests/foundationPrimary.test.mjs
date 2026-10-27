import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { component } from "./renderFoundation.mjs";
import { createPrimaryWorkspace, primaryAccess } from "../src/features/foundation/primaryChanges.ts";
import { createFoundationClient, FoundationApiError } from "../src/features/foundation/client.ts";
import { createApiUrls } from "../src/lib/apiUrls.ts";
import { createApiFetch } from "../src/lib/apiClient.ts";
const actor = "22222222-2222-4222-8222-222222222222", other = "77777777-7777-4777-8777-777777777777";
const org = "11111111-1111-4111-8111-111111111111", member = "33333333-3333-4333-8333-333333333333";
const target = "44444444-4444-4444-8444-444444444444", transfer = "55555555-5555-4555-8555-555555555555", jobId = "66666666-6666-4666-8666-666666666666";
const now = new Date().toISOString(), later = new Date(Date.now() + 240000).toISOString();
const secret = "synthetic-opaque-confirmation-never-in-DOM";
const membership = { id: member, org_id: org, status: "active", version: 1, created_at: now, organization_name: "Synthetic School", organization_status: "active", roles: ["admin"], can_enter: true };
const me = { user: { id: actor, full_name: "Synthetic Primary", global_state: "active", version: 1, access_epoch: 1 }, capabilities: [], memberships: { items: [membership], next_cursor: null } };
const executive = { ...me, capabilities: ["recovery"], memberships: { items: [], next_cursor: null } };
const detail = { id: org, name: "Synthetic School", organization_type: "school", home_region: "test", status: "active", version: 4, access_epoch: 2, primary_admin_membership_id: member };
const replacement = { id: target, user_id: other, status: "active", version: 1, created_at: now, full_name: "Synthetic Replacement", roles: ["admin"] };
const preview = { transfer_id: transfer, org_id: org, from_membership_id: member, to_membership_id: target, expected_version: 4, expires_at: later, confirmation: secret, former_primary_retains_admin: true, operation: "transfer" };
const receipt = { transfer_id: transfer, org_id: org, primary_admin_membership_id: target, version: 5, access_epoch: 3, status: "active", job_id: jobId, delivery_status: "pending_integration" };
const job = { job_id: jobId, kind: "notify_primary_transfer", state: "queued", delivery_status: "pending_integration", attempts: 0, max_attempts: 3, last_error_code: null, created_at: now, updated_at: now };
const settle = async () => { for (let i = 0; i < 4; i++) await new Promise((resolve) => setImmediate(resolve)); };
function deferred() { let resolve;const promise = new Promise((yes) => { resolve = yes; });return { promise, resolve }; }
function fixture(overrides = {}) {
  return { tenantOrganization: async () => detail, members: async () => ({ items: [replacement], next_cursor: null }),
    previewTransfer: async () => preview, previewRecovery: async () => ({ ...preview, operation: "recovery" }),
    confirmTransfer: async () => ({ data: receipt, replayed: false }), confirmRecovery: async () => ({ data: receipt, replayed: false }),
    tenantJob: async () => job, recoveryJob: async () => job, ...overrides };
}
async function ordinary(api = fixture()) {
  const work = createPrimaryWorkspace(api);const stop = work.start(me);work.setOrganization(org);await settle();
  work.setField("target", target);work.setField("reason", "Synthetic reason for primary change");return { work, stop };
}
function recovery(api = fixture()) {
  const work = createPrimaryWorkspace(api);const stop = work.start(executive);work.setOrganization(org);
  work.setField("target", target);work.setField("version", "4");work.setField("reason", "Synthetic reviewed recovery reason");return { work, stop };
}
const view = (await component("PrimaryChangeView")).view;
const render = (work, current = actor) => renderToStaticMarkup(createElement(view, { state: work.getSnapshot(), actor: current, actions: work }));

test("only active effective admin memberships or a separate recovery grant expose a primary workflow", () => {
  assert.equal(primaryAccess(me).memberships.length, 1);
  for (const change of [{ status: "invite_pending" }, { can_enter: false }, { organization_status: "pending" }, { roles: ["student", "instructor"] }]) {
    assert.equal(primaryAccess({ ...me, memberships: { items: [{ ...membership, ...change }], next_cursor: null } }).memberships.length, 0);
  }
  assert.deepEqual(primaryAccess({ ...executive, user: { ...me.user, global_state: "pending" } }), { memberships: [], recovery: false });
  assert.equal(primaryAccess({ ...executive, capabilities: ["orgs"] }).recovery, false);
});

test("current ordinary primary loads a bounded roster and preserves real server page cursors", async () => {
  const cursors = [];const { work, stop } = await ordinary(fixture({ members: async (_org, cursor) => {
    cursors.push(cursor);return { items: [replacement], next_cursor: cursors.length === 1 ? "opaque-next" : null };
  } }));
  assert.equal(work.getSnapshot().version, "4");assert.equal(work.getSnapshot().detail.primary_admin_membership_id, member);
  await work.load(true);assert.deepEqual(cursors, [undefined, "opaque-next"]);assert.equal(work.getSnapshot().members.length, 1);stop();
});

test("a normal administrator cannot fetch a replacement roster or preview without current designation", async () => {
  let reads = 0, previews = 0;const { work, stop } = await ordinary(fixture({ tenantOrganization: async () => ({ ...detail, primary_admin_membership_id: target }),
    members: async () => { reads++;return { items: [], next_cursor: null }; }, previewTransfer: async () => { previews++;return preview; } }));
  await work.prepare();assert.equal(reads, 0);assert.equal(previews, 0);assert.equal(work.getSnapshot().preview, undefined);
  assert.match(render(work), /not the current Primary Admin/);stop();
});

test("production transfer preview and confirmation use exact tenant URLs, versions and a separate human acknowledgement", async () => {
  const calls = [];const urls = createApiUrls("/api", "https://page.example.invalid");
  const fetch = createApiFetch(urls.requestUrl, async () => ({ data: { session: { access_token: "synthetic-token" } } }), async (url, init) => {
    calls.push({ url: String(url), init });
    const value = String(url).endsWith("/preview") ? preview : init.method === "POST" ? receipt : String(url).includes("/jobs/") ? job : String(url).includes("/members?") ? { items: [replacement], next_cursor: null } : detail;
    return new Response(JSON.stringify(value), { headers: init.method === "POST" && !String(url).endsWith("/preview") ? { "Idempotency-Replayed": "false" } : {} });
  }, { credentials: "include" });
  const { work, stop } = await ordinary(createFoundationClient(urls, fetch));await work.prepare();await work.confirm();
  assert.equal(calls.filter((call) => call.init.method === "POST").length, 1);
  const html = render(work);assert.match(html, /Current primary membership/);assert.match(html, /Replacement membership/);
  assert.match(html, /retains the ordinary admin role/);assert.doesNotMatch(html, new RegExp(secret));
  assert.equal(JSON.stringify(work.getSnapshot()).includes(secret), false);
  work.acknowledge(true);await work.confirm();await settle();
  const posts = calls.filter((call) => call.init.method === "POST");assert.equal(posts.length, 2);
  assert.match(posts[0].url, new RegExp(`/api/v1/orgs/${org}/primary-admin-transfers/preview$`));
  assert.match(posts[1].url, new RegExp(`/api/v1/orgs/${org}/primary-admin-transfers$`));
  assert.equal(new Headers(posts[1].init.headers).get("If-Match"), '"4"');
  assert.deepEqual(JSON.parse(posts[1].init.body), { transfer_id: transfer, expected_version: 4, confirmation: secret });
  assert.equal(work.getSnapshot().completion.primary_admin_membership_id, target);assert.match(render(work), /No delivery is confirmed/);stop();
});

test("uncertain confirmation freezes inputs and retries exactly the same operation once acknowledged", async () => {
  const bodies = [];let calls = 0;const { work, stop } = await ordinary(fixture({ confirmTransfer: async (_org, body) => {
    bodies.push({ ...body });if (++calls === 1) throw new FoundationApiError(0, "network_unavailable");return { data: receipt, replayed: true };
  } }));
  await work.prepare();work.acknowledge(true);await work.confirm();assert.equal(work.getSnapshot().uncertain, true);
  work.setField("target", other);work.setMode("recovery");assert.equal(work.getSnapshot().target, target);
  assert.match(render(work), /Retry the same confirmation/);await work.confirm();assert.deepEqual(bodies[0], bodies[1]);
  assert.equal(work.getSnapshot().replayed, true);assert.match(render(work), /No second designation change/);stop();
});

test("duplicate confirmation clicks cause one in-flight request and no repeat after completion", async () => {
  const pending = deferred();let calls = 0;const { work, stop } = await ordinary(fixture({ confirmTransfer: () => { calls++;return pending.promise; } }));
  await work.prepare();work.acknowledge(true);const first = work.confirm();await work.confirm();assert.equal(calls, 1);
  pending.resolve({ data: receipt, replayed: false });await first;await work.confirm();assert.equal(calls, 1);stop();
});

test("expired unsubmitted previews cannot confirm and definitive version conflicts require a new review", async () => {
  let calls = 0;let current = { ...preview, expires_at: "2000-01-01T00:00:00Z" };
  const { work, stop } = await ordinary(fixture({ previewTransfer: async () => current, confirmTransfer: async () => { calls++;throw new FoundationApiError(409, "version_conflict"); } }));
  await work.prepare();work.acknowledge(true);await work.confirm();assert.equal(calls, 0);assert.equal(work.getSnapshot().preview, undefined);
  assert.match(render(work), /preview expired/);current = preview;await work.prepare();work.acknowledge(true);await work.confirm();
  assert.equal(calls, 1);assert.equal(work.getSnapshot().preview, undefined);assert.equal(work.getSnapshot().uncertain, false);
  assert.match(render(work), /Reload the organization/);stop();
});

test("uncertain confirmations can reconcile the same committed receipt after preview expiry", async () => {
  let calls = 0;const { work, stop } = await ordinary(fixture({ confirmTransfer: async () => {
    if (++calls === 1) throw new FoundationApiError(503, "data_unavailable");return { data: receipt, replayed: true };
  } }));
  await work.prepare();work.acknowledge(true);await work.confirm();
  // Advance the clock past the real stored preview expiry without a sleeping test.
  const originalNow = Date.now;Date.now = () => Date.parse(later) + 1000;
  try { await work.confirm(); } finally { Date.now = originalNow; }
  assert.equal(calls, 2);assert.equal(work.getSnapshot().replayed, true);stop();
});

test("recovery is an explicit target/version/reason workflow with no tenant impersonation", async () => {
  const requests = [];let tenantReads = 0;
  const { work, stop } = recovery(fixture({ tenantOrganization: async () => { tenantReads++;return detail; }, members: async () => { tenantReads++;return { items: [], next_cursor: null }; },
    previewRecovery: async (id, body) => { requests.push({ id, body });return { ...preview, operation: "recovery" }; },
    confirmRecovery: async (id, body) => { requests.push({ id, body });return { data: receipt, replayed: false }; } }));
  await work.prepare();assert.equal(tenantReads, 0);assert.equal(requests[0].id, org);assert.equal(requests[0].body.expected_version, 4);
  assert.match(render(work), /does not open a tenant roster/);assert.match(render(work), /Confirm executive recovery/);
  work.acknowledge(true);await work.confirm();assert.equal(requests[1].body.transfer_id, transfer);stop();
});

test("recent-auth errors discard confirmation and never turn account login age into authority", async () => {
  const { work, stop } = recovery(fixture({ confirmRecovery: async () => { throw new FoundationApiError(409, "recent_auth_required"); } }));
  await work.prepare();work.acknowledge(true);await work.confirm();assert.equal(work.getSnapshot().preview, undefined);
  assert.equal(JSON.stringify(work.getSnapshot()).includes(secret), false);assert.match(render(work), /establish recent authentication/);stop();
});

test("same-account access refresh retains an uncertain confirmation while account/grant changes fence it", async () => {
  let calls = 0;const { work, stop } = recovery(fixture({ confirmRecovery: async () => {
    if (++calls === 1) throw new FoundationApiError(0, "network_unavailable");return { data: receipt, replayed: true };
  } }));
  await work.prepare();work.acknowledge(true);await work.confirm();stop();let finish = work.start(executive);await work.confirm();
  assert.equal(work.getSnapshot().replayed, true);finish();finish = work.start({ ...executive, capabilities: [] });
  assert.equal(work.getSnapshot().completion, undefined);assert.equal(work.getSnapshot().preview, undefined);finish();
  finish = work.start({ ...me, user: { ...me.user, id: other } });assert.equal(work.getSnapshot().actor, other);assert.equal(work.getSnapshot().org, "");
  work.clear();assert.equal(work.getSnapshot().actor, null);finish();
});

test("old account preview and detail completions are ignored after a switch or cancellation", async () => {
  const pending = deferred();const { work, stop } = recovery(fixture({ previewRecovery: () => pending.promise }));
  const request = work.prepare();stop();const finish = work.start({ ...executive, user: { ...me.user, id: other } });
  pending.resolve({ ...preview, operation: "recovery" });await request;assert.equal(work.getSnapshot().preview, undefined);
  assert.doesNotMatch(render(work, actor), /Synthetic/);finish();
  const read = deferred();const otherWork = createPrimaryWorkspace(fixture({ tenantOrganization: () => read.promise }));
  const end = otherWork.start(me);otherWork.setOrganization(org);end();otherWork.clear();read.resolve(detail);await settle();
  assert.equal(otherWork.getSnapshot().detail, undefined);assert.equal(otherWork.getSnapshot().members.length, 0);
});

test("mismatched preview/result/job identities fail closed and never render success", async () => {
  const { work, stop } = await ordinary(fixture({ previewTransfer: async () => ({ ...preview, org_id: other }) }));
  await work.prepare();assert.equal(work.getSnapshot().preview, undefined);assert.match(render(work), /unexpected response/);stop();
  const f = await ordinary(fixture({ confirmTransfer: async () => ({ data: { ...receipt, primary_admin_membership_id: member }, replayed: false }) }));
  await f.work.prepare();f.work.acknowledge(true);await f.work.confirm();assert.equal(f.work.getSnapshot().completion, undefined);assert.equal(f.work.getSnapshot().uncertain, true);f.stop();
  const g = await ordinary(fixture({ tenantJob: async () => ({ ...job, kind: "deliver_invitation" }) }));await g.work.prepare();g.work.acknowledge(true);await g.work.confirm();await settle();
  assert.equal(g.work.getSnapshot().job, undefined);assert.match(render(g.work), /unexpected response/);g.stop();
});

test("actual preview and result views escape references, hide confirmation material and preserve pending notifications", async () => {
  const { work, stop } = recovery();await work.prepare();let html = render(work);
  assert.match(html, new RegExp(member));assert.match(html, new RegExp(target));assert.match(html, /type="checkbox"/);
  assert.match(html, /does not remove a global account suspension/);assert.doesNotMatch(html, new RegExp(secret));
  work.acknowledge(true);await work.confirm();await settle();html = render(work);
  assert.match(html, /Primary change recorded/);assert.match(html, /pending integration/);assert.match(html, /No delivery is confirmed/);
  assert.doesNotMatch(html, new RegExp(secret));assert.doesNotMatch(html, />Delivered</);stop();
});
