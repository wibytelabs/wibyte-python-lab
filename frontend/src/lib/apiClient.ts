type SessionResult = {
  data: { session: { access_token?: string } | null };
};

/** Injectable dependencies keep request tests independent of Supabase/browser state. */
export function createApiFetch(
  resolveUrl: (input: string | URL) => string,
  getSession: () => Promise<SessionResult>,
  fetcher: typeof fetch,
  defaults: RequestInit = {},
) {
  return async function apiFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    const request = input instanceof Request ? input : null;
    // Validate the destination before reading or attaching a token.
    const target = resolveUrl(request ? request.url : input as string | URL);
    const headers = new Headers(request?.headers);
    new Headers(defaults.headers).forEach((value, name) => headers.set(name, value));
    new Headers(init.headers).forEach((value, name) => headers.set(name, value));

    const { data } = await getSession();
    if (data.session?.access_token) {
      headers.set("Authorization", `Bearer ${data.session.access_token}`);
    }

    const options = { ...defaults, ...init, headers };
    if (request && init.credentials === undefined) {
      options.credentials = request.credentials;
    }
    return fetcher(request ?? target, options);
  };
}
