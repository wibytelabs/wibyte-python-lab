import assert from "node:assert/strict";
import test from "node:test";
import { component } from "./renderFoundation.mjs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createFoundationSession } from "../src/features/foundation/session.ts";
import { isFoundationRoute } from "../src/features/foundation/route.ts";
import { createFoundationClient, FoundationApiError } from "../src/features/foundation/client.ts";
import { createApiUrls } from "../src/lib/apiUrls.ts";
import { createApiFetch } from "../src/lib/apiClient.ts";

const user = "22222222-2222-4222-8222-222222222222";
const other = "77777777-7777-4777-8777-777777777777";
const org = "11111111-1111-4111-8111-111111111111";
const member = "33333333-3333-4333-8333-333333333333";
const me = { user: { id: user, full_name: "Synthetic person", global_state: "pending", version: 1, access_epoch: 1 },
  capabilities: [], memberships: { items: [], next_cursor: null } };
const answer = (value) => new Response(JSON.stringify(value));
const session = (id = user) => ({ user: { id }, access_token: "synthetic-token" });
function deferred() { let resolve, reject;const promise = new Promise((yes, no) => { resolve = yes;reject = no; });return { promise, resolve, reject }; }
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve)); };
function authFixture(initial = session()) {
  let listener;let unsubscribed = 0;let reads = 0;
  const initialResult = deferred();let current = initial;
  return {
    auth: { getSession: () => { reads++;return initialResult.promise; },
      onAuthStateChange: (callback) => { listener = callback;return { data: { subscription: { unsubscribe: () => { unsubscribed++; } } } }; },
      signOut: async () => { current = null;listener?.("SIGNED_OUT", null);return { error: null }; } },
    resolve: (value = initial) => initialResult.resolve({ data: { session: value } }),
    reject: (error) => initialResult.reject(error),
    emit: (value) => { current = value;listener?.("SIGNED_IN", value); },
    current: () => current, reads: () => reads, unsubscribed: () => unsubscribed,
  };
}

const panel = await component("IdentityPanel");
const page = await component("FoundationPage", { "./session": new URL("../src/features/foundation/session.ts", import.meta.url).href, "./IdentityPanel": panel.url });
const render = (state) => renderToStaticMarkup(createElement(panel.view, { state, onRetry() {}, onSignOut() {},
  login: createElement("p", null, "Synthetic sign-in view") }));

test("public feature flag only selects the foundation route and preserves reset/legacy paths", () => {
  for (const flag of [undefined, "", "false", "TRUE", "1"]) assert.equal(isFoundationRoute(flag, "/foundation"), false);
  assert.equal(isFoundationRoute("true", "/foundation"), true);
  assert.equal(isFoundationRoute("true", "/foundation/orgs/" + org), true);
  for (const path of ["/", "/reset-password", "/foundationish", "/labs"]) assert.equal(isFoundationRoute("true", path), false);
});

test("production session store reaches own pending me through P01 auth client without a legacy profile gate", async () => {
  const f = authFixture();const calls = [];
  const urls = createApiUrls("/api", "https://page.example.invalid");
  const apiFetch = createApiFetch(urls.requestUrl, async () => ({ data: { session: f.current() } }),
    async (url, init) => { calls.push({ url, init });return answer(me); }, { credentials: "include" });
  const controller = createFoundationSession(f.auth, createFoundationClient(urls, apiFetch));
  const states = [];const unsubscribe = controller.subscribe(() => states.push(controller.getSnapshot()));
  const stop = controller.start();f.resolve();await settle();
  assert.equal(controller.getSnapshot().kind, "ready");assert.deepEqual(controller.getSnapshot().me, me);
  assert.equal(calls.length, 1);assert.equal(calls[0].url, "https://page.example.invalid/api/v1/me");
  assert.equal(calls[0].init.headers.get("Authorization"), "Bearer synthetic-token");
  assert.equal(calls[0].init.credentials, "include");
  assert.ok(states.some((state) => state.kind === "checking" && state.signedIn));
  assert.doesNotMatch(JSON.stringify(controller.getSnapshot()), /synthetic-token|access_token/);
  stop();unsubscribe();assert.equal(f.unsubscribed(), 1);
});

test("account switch aborts old data and an older initial-session result cannot replace a newer auth event", async () => {
  const f = authFixture();const first = deferred();const second = deferred();const calls = [];
  const api = { me: (signal) => { calls.push(signal);return calls.length === 1 ? first.promise : second.promise; } };
  const controller = createFoundationSession(f.auth, api);const stop = controller.start();
  f.emit(session());f.emit(session(other));assert.equal(calls[0].aborted, true);
  f.resolve(session());first.resolve(me);second.resolve({ ...me, user: { ...me.user, id: other } });await settle();
  assert.equal(controller.getSnapshot().me.user.id, other);assert.equal(calls.length, 2);
  assert.equal(JSON.stringify(controller.getSnapshot()).includes(user), false);
  stop();
});

test("sign-out and cleanup clear account data and ignore late API responses", async () => {
  const f = authFixture();const pending = deferred();const api = { me: () => pending.promise };
  const controller = createFoundationSession(f.auth, api);const stop = controller.start();f.resolve();await settle();
  f.emit(null);assert.deepEqual(controller.getSnapshot(), { kind: "guest", signedIn: false });
  pending.resolve(me);await settle();assert.equal(controller.getSnapshot().kind, "guest");
  stop();assert.deepEqual(controller.getSnapshot(), { kind: "checking", signedIn: false });
  assert.equal(f.unsubscribed(), 1);f.emit(session(other));await settle();
  assert.equal(controller.getSnapshot().kind, "checking");
});

test("retry refreshes current access, sanitizes auth errors and rejects mismatched account responses", async () => {
  const f = authFixture();let count = 0;
  const controller = createFoundationSession(f.auth, { me: async () => {
    count++;if (count === 1) throw new FoundationApiError(503, "data_unavailable", "a".repeat(32));
    if (count === 2) return { ...me, user: { ...me.user, id: other } };return me;
  } });
  const stop = controller.start();f.resolve();await settle();
  assert.equal(controller.getSnapshot().kind, "error");assert.equal(controller.getSnapshot().requestId, "a".repeat(32));
  controller.reload();await settle();assert.equal(controller.getSnapshot().kind, "error");
  assert.match(controller.getSnapshot().message, /unexpected response/);
  controller.reload();await settle();assert.equal(controller.getSnapshot().kind, "ready");stop();
  const failure = authFixture();const broken = createFoundationSession(failure.auth, { me: async () => me });const cancel = broken.start();
  failure.reject(new Error("private auth/provider detail"));await settle();
  assert.equal(broken.getSnapshot().kind, "error");assert.doesNotMatch(broken.getSnapshot().message, /private|provider/);
  failure.auth.getSession = async () => ({ data: { session: session() } });broken.reload();await settle();
  assert.equal(broken.getSnapshot().kind, "ready");cancel();
});

test("provider sign-out clears the production store without exposing session or stale membership data", async () => {
  const f = authFixture();const controller = createFoundationSession(f.auth, { me: async () => me });
  const stop = controller.start();f.resolve();await settle();await controller.signOut();await settle();
  assert.deepEqual(controller.getSnapshot(), { kind: "guest", signedIn: false });stop();
});

test("actual pending and blocked identity views never render executive controls even with misleading capability fields", () => {
  for (const status of ["pending", "suspended", "declined"]) {
    const html = render({ kind: "ready", signedIn: true, me: { ...me, user: { ...me.user, global_state: status }, capabilities: ["orgs", "recovery"] } });
    assert.doesNotMatch(html, /Organization management|Primary recovery/);
    assert.match(html, /Your account status/);assert.match(html, /Sign out/);
    if (status === "pending") assert.match(html, /Your account is pending/);
  }
});

test("actual active view renders only current capability panels and keeps unavailable membership state truthful", () => {
  const value = { ...me, user: { ...me.user, global_state: "active" }, memberships: { items: [{ id: member, org_id: org,
    organization_name: "Synthetic school", organization_status: "pending", roles: ["admin", "student"], status: "invite_pending", can_enter: false }], next_cursor: "next" } };
  const ordinary = render({ kind: "ready", signedIn: true, me: value });
  assert.doesNotMatch(ordinary, /Organization management|Primary recovery/);assert.match(ordinary, /Not available/);assert.match(ordinary, /admin, student/);
  const executive = render({ kind: "ready", signedIn: true, me: { ...value, capabilities: ["orgs"] } });
  assert.match(executive, /Organization management/);assert.doesNotMatch(executive, /Primary recovery/);
  const recovery = render({ kind: "ready", signedIn: true, me: { ...value, capabilities: ["recovery"] } });
  assert.match(recovery, /Primary recovery/);assert.doesNotMatch(recovery, /Organization management/);
  assert.match(recovery, /first page/);
});

test("actual guest/error views use supplied login, safe request references and escaped text", () => {
  assert.match(render({ kind: "guest", signedIn: false }), /Synthetic sign-in view/);
  const html = render({ kind: "error", signedIn: true, message: "Safe <script>alert(1)</script>", requestId: "b".repeat(32) });
  assert.match(html, /role="alert"/);assert.match(html, /Try again/);assert.match(html, /bbbbbbbb/);
  assert.doesNotMatch(html, /<script>/);
});

test("actual hook-based page render is unconditional and performs no auth or API side effects during rendering", () => {
  let called = 0;
  const auth = { getSession: async () => { called++;return { data: { session: null } }; }, onAuthStateChange: () => { called++;throw new Error(); }, signOut: async () => ({ error: null }) };
  const html = renderToStaticMarkup(createElement(page.view, { auth, api: { me: async () => { called++;return me; } }, login: null }));
  assert.match(html, /Checking your access/);assert.equal(called, 0);
});

test("a sign-out response from an older auth operation cannot erase a newly signed-in account", async () => {
  const f = authFixture();const result = deferred();f.auth.signOut = () => result.promise;
  const controller = createFoundationSession(f.auth, { me: async () => ({ ...me, user: { ...me.user, id: f.current().user.id } }) });
  const stop = controller.start();f.resolve();await settle();const signingOut = controller.signOut();
  f.emit(session(other));await settle();result.resolve({ error: null });await signingOut;await settle();
  assert.equal(controller.getSnapshot().kind, "ready");assert.equal(controller.getSnapshot().me.user.id, other);stop();
});

test("effect cleanup and development remount replace subscriptions and ignore the first generation request", async () => {
  const f = authFixture();f.auth.getSession = async () => ({ data: { session: f.current() } });
  const old = deferred();let calls = 0;
  const controller = createFoundationSession(f.auth, { me: () => { calls++;return calls === 1 ? old.promise : Promise.resolve({ ...me, user: { ...me.user, id: other } }); } });
  const firstStop = controller.start();await settle();firstStop();
  assert.equal(controller.getSnapshot().kind, "checking");const secondStop = controller.start();f.emit(session(other));
  old.resolve(me);await settle();assert.equal(controller.getSnapshot().me.user.id, other);
  firstStop();assert.equal(controller.getSnapshot().kind, "ready");secondStop();assert.equal(f.unsubscribed(), 2);
});
