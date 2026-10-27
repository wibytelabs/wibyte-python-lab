import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { component } from "./renderFoundation.mjs";
import { createOrganizationWorkspace } from "../src/features/foundation/organizations.ts";
import { createFoundationClient, FoundationApiError } from "../src/features/foundation/client.ts";
import { createApiUrls } from "../src/lib/apiUrls.ts";
import { createApiFetch } from "../src/lib/apiClient.ts";
const actor = "22222222-2222-4222-8222-222222222222", other = "77777777-7777-4777-8777-777777777777";
const org = "11111111-1111-4111-8111-111111111111", member = "33333333-3333-4333-8333-333333333333";
const jobId = "44444444-4444-4444-8444-444444444444", key = "55555555-5555-4555-8555-555555555555";
const now = "2026-10-27T00:00:00Z";
const record = { id: org, name: "Synthetic School", organization_type: "school", home_region: "test-region", status: "pending", version: 1, created_at: now,
  contact_email: "contact@example.invalid", primary_admin_membership_id: member, access_epoch: 1, updated_at: now };
const receipt = { org_id: org, status: "pending", primary_admin_membership_id: member, invitation_status: "pending", job_id: jobId, delivery_status: "pending_integration", version: 1 };
const job = { job_id: jobId, kind: "deliver_primary_invitation", state: "queued", delivery_status: "pending_integration", attempts: 0, max_attempts: 3, last_error_code: null, created_at: now, updated_at: now };
const body = { name: record.name, organization_type: "school", contact_email: record.contact_email, primary_admin_email: "primary@example.invalid", home_region: record.home_region, reason: "Synthetic provisioning test" };
const settle = async () => { for (let i = 0; i < 4; i++) await new Promise((resolve) => setImmediate(resolve)); };
function deferred() { let resolve;const promise = new Promise((yes) => { resolve = yes; });return { promise, resolve }; }
function fixture(overrides = {}) {
  return { organizations: async () => ({ items: [record], next_cursor: null }), organization: async () => record,
    createOrganization: async () => ({ data: receipt, replayed: false }), initialJob: async () => job, ...overrides };
}
function workspace(api = fixture()) { return createOrganizationWorkspace(api, () => key); }
function fill(work) { for (const [name, value] of Object.entries(body)) work.setField(name, value); }
const view = (await component("OrganizationView")).view;
const render = (work, current = actor) => renderToStaticMarkup(createElement(view, { state: work.getSnapshot(), actor: current, actions: work }));

test("uncertain creation retries the exact production request key/body and reports committed replay", async () => {
  const calls = [];let failures = 1;
  const urls = createApiUrls("/api", "https://page.example.invalid");
  const fetch = createApiFetch(urls.requestUrl, async () => ({ data: { session: { access_token: "synthetic-token" } } }), async (url, init) => {
    if (init.method === "POST") {
      calls.push({ url, body: init.body, key: new Headers(init.headers).get("Idempotency-Key") });
      if (failures--) throw new Error("synthetic transport outage");
      return new Response(JSON.stringify(receipt), { status: 201, headers: { "Idempotency-Replayed": "true" } });
    }
    return new Response(JSON.stringify(String(url).includes("/jobs/") ? job : { items: [record], next_cursor: null }));
  }, { credentials: "include" });
  const work = workspace(createFoundationClient(urls, fetch));const stop = work.start(actor, "/foundation");fill(work);
  await work.create();assert.equal(work.getSnapshot().locked, true);work.setField("name", "Changed");
  await work.create();assert.equal(calls.length, 2);assert.deepEqual(calls[0], calls[1]);assert.equal(calls[0].key, key);
  assert.deepEqual(JSON.parse(calls[0].body), body);assert.equal(work.getSnapshot().replayed, true);
  assert.match(render(work), /original committed result/);stop();
});

test("duplicate submissions share one pending operation and completed creation cannot submit again", async () => {
  const pending = deferred();let calls = 0;const work = workspace(fixture({ createOrganization: () => { calls++;return pending.promise; } }));
  const stop = work.start(actor, "/foundation");fill(work);const first = work.create();await work.create();assert.equal(calls, 1);
  assert.equal(work.getSnapshot().creating, true);pending.resolve({ data: receipt, replayed: false });await first;
  await work.create();assert.equal(calls, 1);assert.equal(work.getSnapshot().creation.org_id, org);stop();
});

test("validation rejection unlocks field correction and a fresh request identity", async () => {
  const keys = [];let next = 0;
  const work = createOrganizationWorkspace(fixture({ createOrganization: async (_body, requestKey) => {
    keys.push(requestKey);if (keys.length === 1) throw new FoundationApiError(422, "validation_error", undefined, { "body.name": "Invalid value." });
    return { data: receipt, replayed: false };
  } }), () => `${key.slice(0,-1)}${++next}`);
  const stop = work.start(actor, "/foundation");fill(work);await work.create();assert.equal(work.getSnapshot().locked, false);
  assert.match(render(work), /aria-invalid="true"/);assert.match(render(work), /Check this field/);
  work.setField("name", "Corrected School");await work.create();assert.notEqual(keys[0], keys[1]);stop();
});

test("same-account access refresh retains frozen retry values while stopping reads", async () => {
  const requests = [];const work = workspace(fixture({ createOrganization: async (value, requestKey) => {
    requests.push({ value, requestKey });throw new FoundationApiError(0, "network_unavailable");
  } }));
  let stop = work.start(actor, "/foundation");fill(work);await work.create();stop();stop = work.start(actor, "/foundation");
  assert.equal(work.getSnapshot().locked, true);await work.create();assert.deepEqual(requests[0], requests[1]);
  assert.match(render(work), /earlier request may have completed/);work.newRequest();assert.equal(work.getSnapshot().locked, false);
  assert.equal(work.getSnapshot().form.name, "");stop();
});

test("creation result is retained across temporary unmount but discarded on account change", async () => {
  const pending = deferred();const work = workspace(fixture({ createOrganization: () => pending.promise }));
  let stop = work.start(actor, "/foundation");fill(work);const request = work.create();stop();
  pending.resolve({ data: receipt, replayed: false });await request;assert.equal(work.getSnapshot().creation.org_id, org);
  stop = work.start(actor, "/foundation");assert.equal(work.getSnapshot().creation.org_id, org);stop();
  stop = work.start(other, "/foundation");assert.equal(work.getSnapshot().creation, undefined);assert.equal(work.getSnapshot().form.name, "");stop();
});

test("account change and explicit logout clear cached data and fence old mutation replies", async () => {
  const pending = deferred();const work = workspace(fixture({ createOrganization: () => pending.promise }));
  let stop = work.start(actor, "/foundation");fill(work);const request = work.create();stop();stop = work.start(other, "/foundation");
  pending.resolve({ data: receipt, replayed: false });await request;assert.equal(work.getSnapshot().creation, undefined);
  assert.equal(work.getSnapshot().actor, other);work.clear();assert.equal(work.getSnapshot().actor, null);assert.equal(work.getSnapshot().directory, undefined);stop();
});

test("directory pagination preserves server cursor and removes overlapping rows", async () => {
  const calls = [];const work = workspace(fixture({ organizations: async (options) => {
    calls.push(options);return { items: [record], next_cursor: calls.length === 1 ? "opaque-page" : null };
  } }));
  const stop = work.start(actor, "/foundation");await settle();await work.loadMore();
  assert.equal(calls[1].cursor, "opaque-page");assert.equal(work.getSnapshot().directory.items.length, 1);
  assert.equal(work.getSnapshot().directory.next_cursor, null);stop();
});

test("new searches abort and fence older results even when transport ignores abort", async () => {
  const first = deferred();const calls = [];const work = workspace(fixture({ organizations: (options, signal) => {
    calls.push({ options, signal });return calls.length === 1 ? first.promise : Promise.resolve({ items: [], next_cursor: null });
  } }));
  const stop = work.start(actor, "/foundation");work.setSearch("x".repeat(200));await work.search();
  assert.equal(calls[0].signal.aborted, true);assert.equal(calls[1].options.search.length, 120);
  first.resolve({ items: [record], next_cursor: null });await settle();assert.deepEqual(work.getSnapshot().directory.items, []);stop();
});

test("deep links fetch exact detail and inaccessible or mismatched records never substitute", async () => {
  let requested;const work = workspace(fixture({ organization: async (id) => { requested = id;throw new FoundationApiError(404, "not_found"); } }));
  let stop = work.start(actor, `/foundation/orgs/${org}`);await settle();assert.equal(requested, org);
  assert.equal(work.getSnapshot().detail, undefined);assert.match(render(work), /unavailable in your current context/);stop();
  const mismatch = workspace(fixture({ organization: async () => ({ ...record, id: other }) }));stop = mismatch.start(actor, `/foundation/orgs/${org}`);
  await settle();assert.equal(mismatch.getSnapshot().detail, undefined);assert.match(render(mismatch), /unexpected response/);stop();
});

test("unknown foundation paths show a fixed route error without directory or detail requests", () => {
  let calls = 0;const work = workspace(fixture({ organizations: async () => { calls++; }, organization: async () => { calls++; } }));
  const stop = work.start(actor, "/foundation/unknown");assert.equal(calls, 0);assert.match(render(work), /requested page is unavailable/);stop();
});

test("actual organization form and pending details render escaped data and no implicit access", async () => {
  const work = workspace(fixture({ organization: async () => ({ ...record, name: "<script>private</script>" }) }));
  let stop = work.start(actor, "/foundation");fill(work);await settle();let html = render(work);
  assert.match(html, /type="email"/);assert.match(html, /maxLength="254"/i);assert.match(html, /does not approve an account/);
  assert.match(html, /Organization directory/);assert.doesNotMatch(render(work, other), /Synthetic School/);
  await work.select(org);html = render(work);assert.match(html, /&lt;script&gt;private&lt;\/script&gt;/);
  assert.match(html, /Pending organizations do not grant tenant access/);assert.match(html, /Record version/);stop();
});

test("actual invitation status distinguishes queued, simulated and provider acceptance without delivery claims", async () => {
  let current = job;const work = workspace(fixture({ initialJob: async () => current }));const stop = work.start(actor, "/foundation");
  fill(work);await work.create();await settle();assert.match(render(work), /Delivery integration pending/);
  current = { ...job, state: "succeeded", delivery_status: "simulated" };await work.refreshJob();assert.match(render(work), /No real delivery is confirmed/);
  current = { ...job, state: "succeeded", delivery_status: "provider_accepted" };await work.refreshJob();assert.match(render(work), /Inbox delivery is not confirmed/);
  assert.match(render(work), /pending invitation acceptance/);assert.doesNotMatch(render(work), />Delivered</);stop();
});
