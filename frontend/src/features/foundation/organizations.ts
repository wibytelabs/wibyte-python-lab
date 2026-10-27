import { FoundationApiError } from "./client.ts";
import type { FoundationClient, CreateOrganization, Creation, Job, Organization, OrganizationType } from "./client.ts";

type Directory = Awaited<ReturnType<FoundationClient["organizations"]>>;
export type OrganizationUIError = { message: string; fields: Record<string, string>; requestId?: string };
export type OrganizationState = {
  actor: string | null; search: string; directory?: Directory; directoryBusy: boolean; directoryError?: OrganizationUIError;
  selected?: string; detail?: Organization; detailBusy: boolean; detailError?: OrganizationUIError; routeError?: string;
  form: CreateOrganization; locked: boolean; creating: boolean; creation?: Creation; replayed: boolean; createError?: OrganizationUIError;
  job?: Job; jobBusy: boolean; jobError?: OrganizationUIError;
};
function emptyForm(): CreateOrganization { return { name: "", organization_type: "school", contact_email: "", primary_admin_email: "", home_region: "", reason: "" }; }
function initial(actor: string | null): OrganizationState {
  return { actor, search: "", directoryBusy: false, detailBusy: false, form: emptyForm(), locked: false,
    creating: false, replayed: false, jobBusy: false };
}
function failure(error: unknown): OrganizationUIError {
  return error instanceof FoundationApiError ? { message: error.message, fields: error.fields, requestId: error.requestId }
    : { message: "The request could not be completed. Please try again.", fields: {} };
}

/** Account-bound workflow; reads cancel on unmount, uncertain mutations retain their operation key. */
export function createOrganizationWorkspace(api: FoundationClient, newKey = () => crypto.randomUUID()) {
  let state = initial(null), active = false, generation = 0;
  let directorySequence = 0, detailSequence = 0, jobSequence = 0;
  let directoryAbort: AbortController | undefined, detailAbort: AbortController | undefined, jobAbort: AbortController | undefined;
  let attempt: { key: string; body: CreateOrganization; actor: string } | undefined;
  const listeners = new Set<() => void>();
  function update(change: Partial<OrganizationState>) { state = { ...state, ...change }; listeners.forEach((listener) => listener()); }
  function cancelReads() { directoryAbort?.abort(); detailAbort?.abort(); jobAbort?.abort(); }
  function clear() { generation++; active = false; cancelReads(); attempt = undefined; state = initial(null); listeners.forEach((listener) => listener()); }
  async function directory(append = false) {
    if (!active || !state.actor || state.directoryBusy && append) return;
    const cursor = append ? state.directory?.next_cursor : undefined;
    if (append && !cursor) return;
    directoryAbort?.abort(); const abort = new AbortController(); directoryAbort = abort;
    const sequence = ++directorySequence, scope = generation, actor = state.actor, search = state.search;
    update({ directoryBusy: true, directoryError: undefined });
    try {
      const result = await api.organizations({ search, ...(cursor ? { cursor } : {}) }, abort.signal);
      if (!active || scope !== generation || actor !== state.actor || sequence !== directorySequence) return;
      const items = append ? [...(state.directory?.items ?? []), ...result.items] : result.items;
      update({ directory: { items: [...new Map(items.map((item) => [item.id, item])).values()], next_cursor: result.next_cursor }, directoryBusy: false });
    } catch (error) {
      if (active && scope === generation && actor === state.actor && sequence === directorySequence && !abort.signal.aborted) update({ directoryBusy: false, directoryError: failure(error) });
    }
  }
  async function select(id: string) {
    if (!active || !state.actor) return;
    detailAbort?.abort(); const abort = new AbortController(); detailAbort = abort;
    const sequence = ++detailSequence, scope = generation, actor = state.actor;
    update({ selected: id, detail: undefined, detailBusy: true, detailError: undefined, routeError: undefined,
      job: undefined, jobError: undefined, jobBusy: false });
    jobAbort?.abort(); jobSequence++;
    try {
      const detail = await api.organization(id, abort.signal);
      if (!active || scope !== generation || actor !== state.actor || sequence !== detailSequence) return;
      if (detail.id !== id) throw new FoundationApiError(502, "invalid_response");
      update({ detail, detailBusy: false });
    } catch (error) {
      if (active && scope === generation && actor === state.actor && sequence === detailSequence && !abort.signal.aborted) update({ detailBusy: false, detailError: failure(error) });
    }
  }
  async function refreshJob() {
    const receipt = state.creation;
    if (!active || !receipt || !state.actor) return;
    jobAbort?.abort(); const abort = new AbortController(); jobAbort = abort;
    const sequence = ++jobSequence, scope = generation, actor = state.actor;
    update({ jobBusy: true, jobError: undefined });
    try {
      const job = await api.initialJob(receipt.org_id, receipt.job_id, abort.signal);
      if (!active || scope !== generation || actor !== state.actor || sequence !== jobSequence) return;
      if (job.job_id !== receipt.job_id) throw new FoundationApiError(502, "invalid_response");
      update({ job, jobBusy: false });
    } catch (error) {
      if (active && scope === generation && actor === state.actor && sequence === jobSequence && !abort.signal.aborted) update({ jobBusy: false, jobError: failure(error) });
    }
  }
  async function create() {
    if (!active || !state.actor || state.creating || state.creation) return;
    if (!attempt) attempt = { key: newKey(), body: { ...state.form }, actor: state.actor };
    const operation = attempt;
    update({ locked: true, creating: true, createError: undefined });
    try {
      const result = await api.createOrganization(operation.body, operation.key);
      // Unlike a read, a completed mutation is retained across a same-account
      // access-check unmount. Logout/account change clears the operation identity.
      if (attempt !== operation || state.actor !== operation.actor) return;
      update({ creation: result.data, replayed: result.replayed, creating: false, locked: true });
      if (active) { void directory(); void refreshJob(); }
    } catch (error) {
      if (attempt !== operation || state.actor !== operation.actor) return;
      const rejected = error instanceof FoundationApiError && error.status === 422;
      if (rejected) attempt = undefined;
      update({ creating: false, locked: !rejected, createError: failure(error) });
    }
  }
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    clear,
    start: (actor: string, pathname: string) => {
      if (state.actor !== actor) { clear(); state = initial(actor); }
      active = true; const scope = ++generation;
      update({ directoryBusy: false, detailBusy: false, jobBusy: false });
      const match = /^\/foundation\/orgs\/([0-9a-f-]{36})\/?$/i.exec(pathname);
      if (match) void select(match[1]);
      else if (pathname !== "/foundation" && pathname !== "/foundation/") update({ routeError: "The requested page is unavailable." });
      else { void directory(); if (state.creation) void refreshJob(); }
      return () => { if (scope === generation) { active = false; generation++; cancelReads(); } };
    },
    setSearch: (search: string) => {
      directoryAbort?.abort(); directorySequence++;
      update({ search: search.slice(0, 120), directory: undefined, directoryBusy: false, directoryError: undefined });
    },
    search: () => directory(), loadMore: () => directory(true), select,
    home: () => { detailAbort?.abort(); detailSequence++; update({ selected: undefined, detail: undefined, detailError: undefined, routeError: undefined }); void directory(); },
    refreshDetail: () => { if (state.selected) void select(state.selected); },
    setField: (field: keyof CreateOrganization, value: string) => {
      if (state.locked || state.creating || !Object.hasOwn(state.form, field)) return;
      if (field === "organization_type") {
        if (!["school", "university", "training", "other"].includes(value)) return;
        update({ form: { ...state.form, organization_type: value as OrganizationType } });
      } else update({ form: { ...state.form, [field]: value } });
    },
    newRequest: () => {
      if (state.creating) return;
      attempt = undefined; jobAbort?.abort(); jobSequence++;
      update({ form: emptyForm(), locked: false, createError: undefined, creation: undefined, replayed: false,
        job: undefined, jobError: undefined, jobBusy: false });
    },
    create, refreshJob,
  };
}
export type OrganizationWorkspace = ReturnType<typeof createOrganizationWorkspace>;
