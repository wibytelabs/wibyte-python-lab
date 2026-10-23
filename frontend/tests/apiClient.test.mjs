import assert from "node:assert/strict";
import test from "node:test";
import { createApiUrls } from "../src/lib/apiUrls.ts";
import { createApiFetch } from "../src/lib/apiClient.ts";

const urls = createApiUrls("/api", "https://page.example.invalid");
const target = urls.httpUrl("/health");

function fixture(session = { access_token: "synthetic-token" }, defaults = {}) {
  const calls = [];
  const response = new Response("synthetic-response", { status: 409 });
  let sessionCalls = 0;
  const apiFetch = createApiFetch(
    urls.requestUrl,
    async () => {
      sessionCalls++;
      return { data: { session } };
    },
    async (input, init) => {
      calls.push({ input, init });
      return response;
    },
    defaults,
  );
  return { apiFetch, calls, response, sessionCalls: () => sessionCalls };
}

test("bearer, caller options and raw Response are preserved", async () => {
  const f = fixture();
  const controller = new AbortController();
  const headers = new Headers({ "X-Fixture": "kept", Authorization: "replaced" });
  const body = JSON.stringify({ fixture: true });
  const response = await f.apiFetch(target, {
    method: "POST", body, headers, signal: controller.signal,
    credentials: "omit",
  });
  assert.equal(response, f.response);
  assert.equal(response.status, 409);
  assert.equal(f.calls[0].input, target);
  const options = f.calls[0].init;
  assert.equal(options.headers.get("Authorization"), "Bearer synthetic-token");
  assert.equal(options.headers.get("X-Fixture"), "kept");
  assert.equal(headers.get("Authorization"), "replaced");
  assert.equal(options.body, body);
  assert.equal(options.method, "POST");
  assert.equal(options.signal, controller.signal);
  assert.equal(options.credentials, "omit");
});

test("FormData upload receives no forced content type", async () => {
  const f = fixture();
  const body = new FormData();
  body.append("file", new Blob(["synthetic-code"]), "fixture.py");
  await f.apiFetch(target, { method: "POST", body });
  assert.equal(f.calls[0].init.body, body);
  assert.equal(f.calls[0].init.headers.has("Content-Type"), false);
});

test("missing sessions and tokens never produce Bearer undefined", async () => {
  for (const session of [null, {}, { access_token: undefined }, { access_token: "" }]) {
    const f = fixture(session);
    await f.apiFetch(target);
    assert.equal(f.calls[0].init.headers.has("Authorization"), false);
  }
});

test("session rejection propagates without calling fetch", async () => {
  const failure = new Error("synthetic-session-failure");
  let fetched = false;
  const apiFetch = createApiFetch(
    urls.requestUrl,
    async () => { throw failure; },
    async () => { fetched = true; return new Response(); },
  );
  await assert.rejects(apiFetch(target), (error) => error === failure);
  assert.equal(fetched, false);
});

test("network rejection propagates unchanged", async () => {
  const failure = new Error("synthetic-network-failure");
  const apiFetch = createApiFetch(
    urls.requestUrl,
    async () => ({ data: { session: null } }),
    async () => { throw failure; },
  );
  await assert.rejects(apiFetch(target), (error) => error === failure);
});

test("Request inputs retain body, signal, headers and explicit credentials", async () => {
  const f = fixture(undefined, { credentials: "include" });
  const request = new Request(target, {
    method: "PUT", body: "synthetic-body",
    headers: { "X-Request": "kept" }, credentials: "omit",
    signal: new AbortController().signal,
  });
  await f.apiFetch(request, { headers: { "X-Extra": "added" } });
  assert.equal(f.calls[0].input, request);
  assert.equal(request.bodyUsed, false);
  assert.equal(request.signal.aborted, false);
  assert.equal(f.calls[0].init.headers.get("X-Request"), "kept");
  assert.equal(f.calls[0].init.headers.get("X-Extra"), "added");
  assert.equal(f.calls[0].init.credentials, "omit");
});

test("App and Settings cookie defaults and caller overrides remain distinct", async () => {
  const app = fixture(undefined, { credentials: "include" });
  await app.apiFetch(target);
  assert.equal(app.calls[0].init.credentials, "include");
  await app.apiFetch(target, { credentials: "same-origin" });
  assert.equal(app.calls[1].init.credentials, "same-origin");
  const settings = fixture();
  await settings.apiFetch(target);
  assert.equal(settings.calls[0].init.credentials, undefined);
});

test("unapproved destinations are rejected before session lookup", async () => {
  const f = fixture();
  await assert.rejects(f.apiFetch("https://other.example.invalid/steal"));
  assert.equal(f.sessionCalls(), 0);
  assert.equal(f.calls.length, 0);
});

test("without a session, an existing caller authorization header is preserved", async () => {
  const f = fixture(null);
  await f.apiFetch(target, { headers: { Authorization: "synthetic-caller" } });
  assert.equal(f.calls[0].init.headers.get("Authorization"), "synthetic-caller");
});
