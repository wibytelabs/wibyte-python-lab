import assert from "node:assert/strict";
import test from "node:test";
import { createApiUrls } from "../src/lib/apiUrls.ts";

const cases = [
  ["/api", "http://localhost:8080", "http://localhost:8080/api", "ws:"],
  ["/api/", "https://page.example.invalid", "https://page.example.invalid/api", "wss:"],
  ["http://localhost:8000", "http://localhost:8080", "http://localhost:8000", "ws:"],
  ["http://localhost:8080/api", "https://page.example.invalid", "http://localhost:8080/api", "ws:"],
  ["https://wpl.example.invalid/api/", "http://localhost:8080", "https://wpl.example.invalid/api", "wss:"],
];

for (const [base, page, expected, scheme] of cases) {
  test(`HTTP and terminal contract: ${base} from ${page}`, () => {
    const urls = createApiUrls(base, page);
    assert.equal(urls.httpBase, expected);
    assert.equal(urls.httpUrl("/labs/id/terminal"), expected + "/labs/id/terminal");
    const socket = new URL(urls.webSocketUrl("/labs/id/terminal"));
    assert.equal(socket.protocol, scheme);
    assert.equal(socket.host, new URL(expected).host);
    assert.equal(socket.pathname, new URL(expected + "/labs/id/terminal").pathname);
  });
}

test("missing and empty bases fall back to same-origin /api", () => {
  for (const base of [undefined, ""]) {
    assert.equal(
      createApiUrls(base, "https://page.example.invalid").httpBase,
      "https://page.example.invalid/api",
    );
  }
});

test("joining preserves prefixes, trailing endpoints and encoded identifiers", () => {
  const urls = createApiUrls("/api///", "https://page.example.invalid");
  assert.equal(urls.httpUrl("health"), urls.httpBase + "/health");
  assert.equal(urls.httpUrl("/health/"), urls.httpBase + "/health/");
  const endpoint = `/labs/${encodeURIComponent("name / ü")}/terminal`;
  assert.equal(new URL(urls.webSocketUrl(endpoint)).pathname, "/api" + endpoint);
  assert.equal(urls.httpUrl("/files?path=a%2Fb"), urls.httpBase + "/files?path=a%2Fb");
});

test("invalid bases fail before authentication can be attached", () => {
  for (const base of [
    "ftp://example.invalid/api", "ws://example.invalid/api",
    "https://user:secret@example.invalid/api",
    "https://example.invalid/api?x=1", "https://example.invalid/api#",
    "//other.example.invalid/api", "api", "http:example.invalid",
    " https://example.invalid/api", "/api\\other",
    "http://localhost:0", "http://localhost:99999",
  ]) {
    assert.throws(() => createApiUrls(base, "https://page.example.invalid"), undefined, base);
  }
});

test("external endpoints and path traversal are rejected", () => {
  const urls = createApiUrls("/api", "https://page.example.invalid");
  for (const endpoint of [
    "https://other.example.invalid/steal", "//other.example.invalid",
    "\\other.example.invalid", "/../steal", "/%2e%2e/steal",
    "/labs/../health", "/health#fragment",
  ]) {
    assert.throws(() => urls.httpUrl(endpoint), undefined, endpoint);
  }
});

test("existing absolute request URLs must remain within the API prefix", () => {
  const urls = createApiUrls("/api", "https://page.example.invalid");
  assert.equal(urls.requestUrl(urls.httpBase + "/health"), urls.httpBase + "/health");
  for (const target of [
    "https://other.example.invalid/api/health",
    "https://page.example.invalid/api-other/health",
    "https://user:secret@page.example.invalid/api/health",
    "https://page.example.invalid/api/health#fragment",
  ]) {
    assert.throws(() => urls.requestUrl(target));
  }
});
