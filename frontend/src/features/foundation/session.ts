import { FoundationApiError } from "./client.ts";
import type { FoundationClient, Me } from "./client.ts";

export type AuthSession = { user: { id: string } };
export type FoundationAuth = {
  getSession: () => Promise<{ data: { session: AuthSession | null } }>;
  onAuthStateChange: (listener: (event: string, session: AuthSession | null) => void) => {
    data: { subscription: { unsubscribe: () => void } };
  };
  signOut: () => Promise<{ error: unknown }>;
};
export type FoundationState =
  | { kind: "checking"; signedIn: boolean }
  | { kind: "guest"; signedIn: false }
  | { kind: "ready"; signedIn: true; me: Me }
  | { kind: "error"; signedIn: boolean; message: string; requestId?: string };

/** Small external store: auth events invalidate data before any new account load. */
export function createFoundationSession(auth: FoundationAuth, api: Pick<FoundationClient, "me">) {
  let state: FoundationState = { kind: "checking", signedIn: false };
  const listeners = new Set<() => void>();
  let active = false, run = 0, revision = 0, request = 0;
  let current: AuthSession | null = null;
  let pending: AbortController | undefined;
  function publish(next: FoundationState) { state = next; listeners.forEach((listener) => listener()); }
  function failure(error: unknown, signedIn: boolean) {
    publish({ kind: "error", signedIn, message: error instanceof FoundationApiError ? error.message : "Unable to check your account. Please try again.",
      requestId: error instanceof FoundationApiError ? error.requestId : undefined });
  }
  async function apply(session: AuthSession | null, generation: number) {
    current = session ? { user: { id: session.user.id } } : null;
    pending?.abort();
    const sequence = ++request;
    if (!session) { publish({ kind: "guest", signedIn: false }); return; }
    const abort = new AbortController(); pending = abort;
    publish({ kind: "checking", signedIn: true });
    try {
      const me = await api.me(abort.signal);
      if (!active || generation !== run || sequence !== request) return;
      if (me.user.id !== session.user.id) throw new FoundationApiError(502, "invalid_response");
      publish({ kind: "ready", signedIn: true, me });
    } catch (error) {
      if (!active || generation !== run || sequence !== request || abort.signal.aborted) return;
      failure(error, true);
    }
  }
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    start: () => {
      if (active) return () => {};
      active = true; const generation = ++run, initialRevision = revision;
      publish({ kind: "checking", signedIn: false });
      const { data: { subscription } } = auth.onAuthStateChange((_event, session) => {
        if (!active || generation !== run) return;
        revision++;
        // Do not return/await an API request inside the provider auth callback.
        void apply(session, generation);
      });
      void auth.getSession().then(({ data }) => {
        if (active && generation === run && revision === initialRevision) void apply(data.session, generation);
      }).catch((error: unknown) => {
        if (active && generation === run && revision === initialRevision) failure(error, false);
      });
      return () => {
        if (generation !== run || !active) return;
        active = false; request++; revision++; current = null; pending?.abort(); subscription.unsubscribe();
        publish({ kind: "checking", signedIn: false });
      };
    },
    reload: () => {
      if (!active) return;
      const generation = run, operationRevision = ++revision;
      if (current) { void apply(current, generation); return; }
      publish({ kind: "checking", signedIn: false });
      void auth.getSession().then(({ data }) => {
        if (active && generation === run && revision === operationRevision) void apply(data.session, generation);
      }).catch((error: unknown) => {
        if (active && generation === run && revision === operationRevision) failure(error, false);
      });
    },
    signOut: async () => {
      const generation = run, operationRevision = ++revision;
      request++; pending?.abort(); publish({ kind: "checking", signedIn: false });
      try {
        const { error } = await auth.signOut();
        if (!active || generation !== run || revision !== operationRevision) return;
        if (error) { failure(new Error(), Boolean(current)); return; }
        revision++; void apply(null, generation);
      } catch { if (active && generation === run && revision === operationRevision) failure(new Error(), Boolean(current)); }
    },
  };
}
