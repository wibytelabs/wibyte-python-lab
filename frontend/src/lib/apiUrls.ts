/** Pure URL contract; importing this module never initializes authentication. */
export function createApiUrls(
  configuredBase: string | undefined,
  pageOrigin: string,
) {
  const raw = configuredBase || "/api";
  if (
    /[\s\\?#]/.test(raw) ||
    !(raw.startsWith("/") && !raw.startsWith("//") ||
      /^https?:\/\//i.test(raw))
  ) {
    throw new Error("API base must be an HTTP(S) URL or an absolute local path.");
  }

  const page = new URL(pageOrigin);
  if (!["http:", "https:"].includes(page.protocol) ||
      page.username || page.password) {
    throw new Error("Page origin must use HTTP(S) without credentials.");
  }

  const base = new URL(raw, page.origin);
  if (!["http:", "https:"].includes(base.protocol) ||
      !base.hostname || base.username || base.password || base.port === "0") {
    throw new Error("API base must use HTTP(S) without credentials.");
  }
  base.pathname = base.pathname.replace(/\/+$/, "");
  const httpBase = base.href.replace(/\/+$/, "");
  const prefix = base.pathname.replace(/\/+$/, "");

  function requestUrl(input: string | URL): string {
    const rawInput = String(input);
    if (/[\s\\]/.test(rawInput)) {
      throw new Error("Invalid API request URL.");
    }
    const target = new URL(rawInput, page.origin);
    if (
      target.origin !== base.origin ||
      target.username || target.password || target.hash ||
      !(target.pathname === prefix ||
        target.pathname.startsWith(prefix + "/"))
    ) {
      throw new Error("API request must stay within the configured API base.");
    }
    return target.href;
  }

  function httpUrl(endpoint: string): string {
    if (
      /[\s\\#]/.test(endpoint) ||
      endpoint.startsWith("//") ||
      /^[a-z][a-z0-9+.-]*:/i.test(endpoint)
    ) {
      throw new Error("API endpoint must be a local path.");
    }
    for (const segment of endpoint.split("?")[0].split("/")) {
      if ([".", ".."].includes(decodeURIComponent(segment))) {
        throw new Error("API endpoint must not contain dot segments.");
      }
    }
    return requestUrl(httpBase + "/" + endpoint.replace(/^\/+/, ""));
  }

  function webSocketUrl(endpoint: string): string {
    const target = new URL(httpUrl(endpoint));
    target.protocol = target.protocol === "https:" ? "wss:" : "ws:";
    return target.href;
  }

  return { httpBase, httpUrl, webSocketUrl, requestUrl };
}
