import { FoundationApiError } from "./client.ts";
import type { Completion, FoundationClient, Job, Me, Member, Preview, TenantOrganization } from "./client.ts";

type Mode = "transfer" | "recovery";
type PreviewSummary = Omit<Preview, "confirmation">;
type UIError = { message: string; requestId?: string; fields: Record<string, string>; code?: string };
export function primaryAccess(me: Me) {
  const active = me.user.global_state === "active";
  return { recovery: active && me.capabilities.includes("recovery"),
    memberships: active ? me.memberships.items.filter((member) => member.can_enter && member.status === "active" &&
      member.organization_status === "active" && member.roles.includes("admin")) : [] };
}
export type PrimaryState = {
  actor: string | null; mode: Mode; memberships: Me["memberships"]["items"]; recovery: boolean;
  org: string; detail?: TenantOrganization; members: Member[]; cursor: string | null; loading: boolean;
  target: string; version: string; reason: string; preview?: PreviewSummary; preparing: boolean;
  acknowledged: boolean; confirming: boolean; uncertain: boolean; completion?: Completion; replayed: boolean;
  job?: Job; jobBusy: boolean; error?: UIError;
};
function initial(actor: string | null): PrimaryState {
  return { actor, mode: "transfer", memberships: [], recovery: false, org: "", members: [], cursor: null,
    loading: false, target: "", version: "", reason: "", preparing: false, acknowledged: false,
    confirming: false, uncertain: false, replayed: false, jobBusy: false };
}
function failure(error: unknown): UIError {
  return error instanceof FoundationApiError ? { message: error.message, requestId: error.requestId, fields: error.fields, code: error.code }
    : { message: "The request could not be completed. Try again.", fields: {} };
}
const validId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) && value !== "00000000-0000-0000-0000-000000000000";

/** Confirmation material stays private to this account-bound workflow, never in view state or storage. */
export function createPrimaryWorkspace(api: FoundationClient) {
  let state = initial(null), active = false, revision = 0, readSequence = 0, jobSequence = 0;
  let readAbort: AbortController | undefined, jobAbort: AbortController | undefined;
  let confirmation: { org: string; mode: Mode; body: { transfer_id: string; expected_version: number; confirmation: string } } | undefined;
  const listeners = new Set<() => void>();
  function update(change: Partial<PrimaryState>) { state = { ...state, ...change };listeners.forEach((listener) => listener()); }
  function cancelReads() { readAbort?.abort();jobAbort?.abort();readSequence++;jobSequence++; }
  function clear() { revision++;active = false;confirmation = undefined;cancelReads();state = initial(null);listeners.forEach((listener) => listener()); }
  function permitted() { return state.mode === "recovery" ? state.recovery : state.memberships.some((member) => member.org_id === state.org); }
  function locked() { return state.preparing || state.confirming || state.uncertain || Boolean(state.preview || state.completion); }
  function reset() {
    if (state.confirming || state.preparing) return;
    revision++;confirmation = undefined;jobAbort?.abort();jobSequence++;
    update({ preview: undefined, acknowledged: false, uncertain: false, completion: undefined, replayed: false, job: undefined, jobBusy: false, error: undefined });
  }
  async function load(append = false) {
    if (!active || state.mode !== "transfer" || !permitted() || locked() || state.loading && append) return;
    if (append && !state.cursor) return;
    readAbort?.abort();const abort = new AbortController();readAbort = abort;
    const scope = revision, sequence = ++readSequence, org = state.org, actor = state.actor;
    update({ loading: true, error: undefined });
    try {
      const detail = append ? state.detail : await api.tenantOrganization(org, abort.signal);
      if (!active || scope !== revision || actor !== state.actor || sequence !== readSequence || org !== state.org || abort.signal.aborted) return;
      if (!detail || detail.id !== org) throw new FoundationApiError(502, "invalid_response");
      const own = state.memberships.find((member) => member.org_id === org);
      const isPrimary = detail.status === "active" && detail.primary_admin_membership_id === own?.id;
      // A normal administrator can inspect the organization, but only its current primary gets a selector.
      const page = isPrimary ? await api.members(org, append ? state.cursor ?? undefined : undefined, abort.signal) : { items: [], next_cursor: null };
      if (!active || scope !== revision || actor !== state.actor || sequence !== readSequence || org !== state.org || abort.signal.aborted) return;
      const rows = append ? [...state.members, ...page.items] : page.items;
      update({ detail, version: String(detail.version), loading: false, members: [...new Map(rows.map((row) => [row.id, row])).values()], cursor: page.next_cursor });
    } catch (error) {
      if (active && scope === revision && sequence === readSequence && !abort.signal.aborted) update({ loading: false, error: failure(error) });
    }
  }
  async function prepare() {
    if (!active || !permitted() || locked() || state.loading) return;
    const expected = Number(state.version);
    const own = state.memberships.find((member) => member.org_id === state.org);
    const eligible = state.mode === "recovery" || state.detail?.status === "active" && state.detail.primary_admin_membership_id === own?.id &&
      state.members.some((member) => member.id === state.target && member.id !== own?.id && member.status === "active" && member.user_id && member.roles.includes("admin"));
    if (!validId(state.org) || !validId(state.target) || !/^[1-9][0-9]*$/.test(state.version) || !Number.isSafeInteger(expected) || expected > 2147483647 ||
        state.reason.trim().length < 5 || state.reason.length > 1000 || !eligible) {
      update({ error: { message: "Select an eligible administrator, current version and a reason of at least five characters.", fields: {} } });return;
    }
    const scope = revision, actor = state.actor, org = state.org, mode = state.mode;
    update({ preparing: true, error: undefined });
    try {
      const body = { target_membership_id: state.target, expected_version: expected, reason: state.reason.trim() };
      const result = await (mode === "recovery" ? api.previewRecovery(org, body) : api.previewTransfer(org, body));
      if (scope !== revision || actor !== state.actor) return;
      if (result.org_id !== org || result.to_membership_id !== body.target_membership_id || result.expected_version !== expected || result.operation !== mode ||
          !result.former_primary_retains_admin || mode === "transfer" && result.from_membership_id !== own?.id) throw new FoundationApiError(502, "invalid_response");
      confirmation = { org, mode, body: { transfer_id: result.transfer_id, expected_version: result.expected_version, confirmation: result.confirmation } };
      // Explicit projection ensures the opaque confirmation is never handed to React/DOM.
      update({ preparing: false, preview: { transfer_id: result.transfer_id, org_id: result.org_id, from_membership_id: result.from_membership_id,
        to_membership_id: result.to_membership_id, expected_version: result.expected_version, expires_at: result.expires_at,
        former_primary_retains_admin: result.former_primary_retains_admin, operation: result.operation }, acknowledged: false });
    } catch (error) { if (scope === revision && actor === state.actor) update({ preparing: false, error: failure(error) }); }
  }
  async function refreshJob() {
    const receipt = state.completion;if (!active || !receipt || !permitted()) return;
    jobAbort?.abort();const abort = new AbortController();jobAbort = abort;
    const scope = revision, sequence = ++jobSequence, actor = state.actor, org = state.org, mode = state.mode;
    update({ jobBusy: true, error: undefined });
    try {
      const job = await (mode === "recovery" ? api.recoveryJob(org, receipt.job_id, abort.signal) : api.tenantJob(org, receipt.job_id, abort.signal));
      if (!active || scope !== revision || actor !== state.actor || sequence !== jobSequence || abort.signal.aborted) return;
      if (job.job_id !== receipt.job_id || job.kind !== "notify_primary_transfer") throw new FoundationApiError(502, "invalid_response");
      update({ job, jobBusy: false });
    } catch (error) { if (active && scope === revision && sequence === jobSequence && !abort.signal.aborted) update({ jobBusy: false, error: failure(error) }); }
  }
  async function confirm() {
    const operation = confirmation;
    if (!active || !permitted() || !operation || !state.preview || !state.acknowledged || state.confirming || state.completion) return;
    // An uncertain result may already be committed; retry its exact receipt even after preview expiry.
    if (!state.uncertain && Date.parse(state.preview.expires_at) <= Date.now()) {
      confirmation = undefined;update({ preview: undefined, error: { message: "This preview expired. Reload the record and review a new preview.", fields: {} } });return;
    }
    const scope = revision, actor = state.actor;
    update({ confirming: true, error: undefined });
    try {
      const result = await (operation.mode === "recovery" ? api.confirmRecovery(operation.org, operation.body) : api.confirmTransfer(operation.org, operation.body));
      if (scope !== revision || actor !== state.actor || confirmation !== operation) return;
      if (result.data.org_id !== operation.org || result.data.transfer_id !== operation.body.transfer_id || result.data.primary_admin_membership_id !== state.preview?.to_membership_id)
        throw new FoundationApiError(502, "invalid_response");
      confirmation = undefined;
      update({ confirming: false, uncertain: false, completion: result.data, replayed: result.replayed, preview: undefined });
      if (active) void refreshJob();
    } catch (error) {
      if (scope !== revision || actor !== state.actor || confirmation !== operation) return;
      const definitive = error instanceof FoundationApiError && [401, 403, 404, 409, 422].includes(error.status);
      if (definitive) confirmation = undefined;
      update({ confirming: false, uncertain: !definitive, ...(definitive ? { preview: undefined, acknowledged: false } : {}), error: failure(error) });
    }
  }
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener);return () => { listeners.delete(listener); }; },
    clear, reset, load, prepare, confirm, refreshJob,
    start: (me: Me) => {
      if (state.actor !== me.user.id) { clear();state = initial(me.user.id); }
      const access = primaryAccess(me);active = true;
      const scopeAllowed = state.mode === "recovery" ? access.recovery : access.memberships.some((member) => member.org_id === state.org);
      if (state.org && !scopeAllowed) { revision++;confirmation = undefined;cancelReads();state = initial(me.user.id); }
      const mode = access.memberships.length === 0 && access.recovery ? "recovery" : state.mode;
      update({ ...access, mode, loading: false, jobBusy: false });
      if (state.mode === "transfer" && state.org && !locked()) void load();
      else if (state.completion) void refreshJob();
      return () => { active = false;cancelReads(); };
    },
    setMode: (mode: Mode) => {
      if (locked() || mode === "recovery" && !state.recovery || mode === "transfer" && state.memberships.length === 0) return;
      reset();cancelReads();update({ mode, org: "", detail: undefined, members: [], cursor: null, loading: false, target: "", version: "", reason: "" });
    },
    setOrganization: (org: string) => {
      if (locked()) return;
      reset();cancelReads();update({ org, detail: undefined, members: [], cursor: null, loading: false, target: "", version: "" });
      if (state.mode === "transfer") void load();
    },
    setField: (field: "target" | "version" | "reason", value: string) => {
      if (locked() || field === "version" && state.mode !== "recovery") return;
      update({ [field]: value });
    },
    acknowledge: (value: boolean) => { if (!state.confirming && !state.completion) update({ acknowledged: value }); },
  };
}
export type PrimaryWorkspace = ReturnType<typeof createPrimaryWorkspace>;
