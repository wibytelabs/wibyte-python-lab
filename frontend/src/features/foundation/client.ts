/** Foundation requests use the existing URL/auth client; no provider table reads. */
type Urls = { httpUrl: (endpoint: string) => string };
type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type OrganizationState = "pending" | "active" | "suspended" | "recovery_required";
export type OrganizationType = "school" | "university" | "training" | "other";
export type MemberRole = "admin" | "instructor" | "student";
export type Page<T> = { items: T[]; next_cursor: string | null };
export type CreateOrganization = {
  name: string; organization_type: OrganizationType; contact_email: string;
  primary_admin_email: string; home_region: string; reason: string;
};
export type PreviewInput = { target_membership_id: string; expected_version: number; reason: string };
export type ConfirmationInput = { transfer_id: string; expected_version: number; confirmation: string };
export type ListOptions = { cursor?: string; search?: string; status?: OrganizationState; organization_type?: OrganizationType };

const messages: Record<string, string> = {
  invalid_identity: "Your sign-in expired. Sign in again.",
  forbidden: "Your current account does not have permission for this action.",
  not_found: "This record is unavailable in your current context.",
  version_conflict: "This record changed. Reload it and review a new confirmation.",
  idempotency_conflict: "This retry belongs to different form values. Start a new request.",
  recent_auth_required: "Sign in again before confirming a primary change.",
  invalid_confirmation: "This confirmation expired or changed. Review a new preview.",
  target_ineligible: "Choose another active administrator in this organization.",
  preview_in_progress: "Another authorized person has a current preview. Try again after it expires.",
  validation_error: "Check the highlighted fields.",
  data_unavailable: "Application data is temporarily unavailable. Try again.",
  delivery_unavailable: "Invitation preparation is temporarily unavailable. Your request was not completed.",
  identity_unavailable: "Sign-in verification is temporarily unavailable. Try again.",
  network_unavailable: "Unable to reach the application. Retry the same request when connected.",
  invalid_response: "The application returned an unexpected response. Reload before continuing.",
  request_failed: "The request could not be completed. Try again.",
};

export class FoundationApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  fields: Record<string, string>;
  constructor(status: number, code: string, requestId?: string, fields: Record<string, string> = {}) {
    super(messages[code] ?? messages.request_failed);
    this.name = "FoundationApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fields = fields;
  }
}

function invalid(): never { throw new FoundationApiError(502, "invalid_response"); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function string(value: unknown, max = 512): string {
  if (typeof value !== "string" || value.length > max) return invalid();
  return value;
}
function positive(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1) return invalid();
  return value;
}
function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") return invalid();
  return value;
}
function oneOf<T extends string>(value: unknown, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) return invalid();
  return value as T;
}
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function uuid(value: unknown): string {
  const result = string(value, 36);
  if (!uuidPattern.test(result) || result === "00000000-0000-0000-0000-000000000000") return invalid();
  return result;
}
function pathId(value: string): string {
  if (typeof value !== "string" || !uuidPattern.test(value) || value === "00000000-0000-0000-0000-000000000000") {
    throw new TypeError("Select a valid record before continuing.");
  }
  return encodeURIComponent(value);
}
function timestamp(value: unknown): string {
  const result = string(value, 64);
  if (!Number.isFinite(Date.parse(result))) return invalid();
  return result;
}
function roles(value: unknown): MemberRole[] {
  if (!Array.isArray(value) || value.length > 3) return invalid();
  return value.map((role) => oneOf(role, ["admin", "instructor", "student"] as const));
}
function organizationState(value: unknown) {
  return oneOf(value, ["pending", "active", "suspended", "recovery_required"] as const);
}
function organizationType(value: unknown) {
  return oneOf(value, ["school", "university", "training", "other"] as const);
}
function memberState(value: unknown) { return oneOf(value, ["invite_pending", "active", "suspended", "removed"] as const); }
function page<T>(value: unknown, decode: (row: unknown) => T): Page<T> {
  const data = object(value);
  if (!Array.isArray(data.items) || data.items.length > 100) return invalid();
  return { items: data.items.map(decode), next_cursor: data.next_cursor === null ? null : string(data.next_cursor) };
}
function organization(value: unknown) {
  const data = object(value);
  return { id: uuid(data.id), name: string(data.name, 160), organization_type: organizationType(data.organization_type),
    home_region: string(data.home_region, 64), status: organizationState(data.status), version: positive(data.version),
    created_at: timestamp(data.created_at) };
}
function executiveOrganization(value: unknown) {
  const data = object(value);
  return { ...organization(data), contact_email: string(data.contact_email, 254),
    primary_admin_membership_id: uuid(data.primary_admin_membership_id), access_epoch: positive(data.access_epoch),
    updated_at: timestamp(data.updated_at) };
}
function tenantOrganization(value: unknown) {
  const data = object(value);
  return { id: uuid(data.id), name: string(data.name, 160), organization_type: organizationType(data.organization_type),
    home_region: string(data.home_region, 64), status: organizationState(data.status), version: positive(data.version),
    access_epoch: positive(data.access_epoch),
    contact_email: data.contact_email === undefined ? undefined : string(data.contact_email, 254),
    primary_admin_membership_id: data.primary_admin_membership_id === undefined ? undefined : uuid(data.primary_admin_membership_id) };
}
function member(value: unknown) {
  const data = object(value);
  return { id: uuid(data.id), user_id: data.user_id === null ? null : uuid(data.user_id), status: memberState(data.status),
    version: positive(data.version), created_at: timestamp(data.created_at),
    full_name: data.full_name === null ? null : string(data.full_name, 160), roles: roles(data.roles) };
}
function me(value: unknown) {
  const data = object(value), user = object(data.user);
  if (!Array.isArray(data.capabilities) || data.capabilities.length > 6) return invalid();
  const capabilities = data.capabilities.map((cap) => oneOf(cap, ["orgs", "users", "recovery", "executives", "observe", "approvals"] as const));
  const memberships = page(data.memberships, (value) => {
    const row = object(value);
    return { id: uuid(row.id), org_id: uuid(row.org_id), status: memberState(row.status), version: positive(row.version),
      created_at: timestamp(row.created_at), organization_name: string(row.organization_name, 160),
      organization_status: organizationState(row.organization_status), roles: roles(row.roles), can_enter: boolean(row.can_enter) };
  });
  return { user: { id: uuid(user.id), full_name: string(user.full_name, 160),
    global_state: oneOf(user.global_state, ["pending", "active", "suspended", "declined"] as const),
    access_epoch: positive(user.access_epoch), version: positive(user.version) }, memberships, capabilities };
}
function creation(value: unknown) {
  const row = object(value);
  return { org_id: uuid(row.org_id), status: oneOf(row.status, ["pending"] as const),
    primary_admin_membership_id: uuid(row.primary_admin_membership_id), invitation_status: oneOf(row.invitation_status, ["pending"] as const),
    job_id: uuid(row.job_id), delivery_status: oneOf(row.delivery_status, ["pending_integration"] as const), version: positive(row.version) };
}
function preview(value: unknown) {
  const row = object(value);
  return { transfer_id: uuid(row.transfer_id), org_id: uuid(row.org_id), from_membership_id: uuid(row.from_membership_id),
    to_membership_id: uuid(row.to_membership_id), expected_version: positive(row.expected_version),
    expires_at: timestamp(row.expires_at), confirmation: string(row.confirmation, 256),
    former_primary_retains_admin: boolean(row.former_primary_retains_admin), operation: oneOf(row.operation, ["transfer", "recovery"] as const) };
}
function completion(value: unknown) {
  const row = object(value);
  return { transfer_id: uuid(row.transfer_id), org_id: uuid(row.org_id), primary_admin_membership_id: uuid(row.primary_admin_membership_id),
    version: positive(row.version), access_epoch: positive(row.access_epoch), status: oneOf(row.status, ["active"] as const),
    job_id: uuid(row.job_id), delivery_status: oneOf(row.delivery_status, ["pending_integration"] as const) };
}
function job(value: unknown) {
  const row = object(value);
  if (typeof row.attempts !== "number" || !Number.isInteger(row.attempts) || row.attempts < 0 || row.attempts > 10 ||
      typeof row.max_attempts !== "number" || !Number.isInteger(row.max_attempts) || row.max_attempts < 1 || row.max_attempts > 10) return invalid();
  return { job_id: uuid(row.job_id), kind: oneOf(row.kind, ["deliver_invitation", "deliver_primary_invitation", "notify_primary_transfer"] as const),
    state: oneOf(row.state, ["queued", "running", "succeeded", "dead", "cancelled"] as const),
    delivery_status: oneOf(row.delivery_status, ["pending_integration", "simulated", "provider_accepted"] as const),
    attempts: row.attempts, max_attempts: row.max_attempts, last_error_code: row.last_error_code === null ? null : string(row.last_error_code, 64),
    created_at: timestamp(row.created_at), updated_at: timestamp(row.updated_at) };
}

export function createFoundationClient(urls: Urls, apiFetch: Fetch) {
  async function request<T>(endpoint: string, decode: (value: unknown) => T, init: RequestInit = {}, receiptStatus?: number) {
    let response: Response;
    try { response = await apiFetch(urls.httpUrl(endpoint), init); }
    catch (error) {
      if (error instanceof Error && error.name === "AbortError") throw error;
      throw new FoundationApiError(0, "network_unavailable");
    }
    let value: unknown;
    try { value = await response.json(); }
    catch { if (response.ok) return invalid(); }
    if (!response.ok) {
      const data = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
      const code = typeof data.code === "string" && Object.hasOwn(messages, data.code) ? data.code : "request_failed";
      const requestId = typeof data.request_id === "string" && /^[a-f0-9]{32}$/.test(data.request_id) ? data.request_id : undefined;
      const fields: Record<string, string> = {};
      if (data.field_errors && typeof data.field_errors === "object" && !Array.isArray(data.field_errors)) {
        for (const key of Object.keys(data.field_errors).slice(0, 20)) {
          if (/^[A-Za-z0-9_.]{1,120}$/.test(key)) fields[key] = "Invalid value.";
        }
      }
      throw new FoundationApiError(response.status, code, requestId, fields);
    }
    const replay = response.headers.get("Idempotency-Replayed");
    if (receiptStatus !== undefined && (response.status !== receiptStatus || (replay !== "true" && replay !== "false"))) return invalid();
    return { data: decode(value), replayed: replay === "true" };
  }
  async function read<T>(path: string, decode: (value: unknown) => T, signal?: AbortSignal) {
    return (await request(path, decode, { signal })).data;
  }
  function send<T>(path: string, body: object, decode: (value: unknown) => T, headers: Record<string, string> = {}, receiptStatus?: number) {
    return request(path, decode, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) }, receiptStatus);
  }
  function previewChange(org: string, body: PreviewInput, recovery: boolean) {
    const endpoint = recovery ? `/v1/platform/organizations/${pathId(org)}/primary-admin-recovery` : `/v1/orgs/${pathId(org)}/primary-admin-transfers`;
    return send(endpoint + "/preview", { target_membership_id: pathId(body.target_membership_id),
      expected_version: body.expected_version, reason: body.reason }, preview, { "If-Match": `"${body.expected_version}"` }).then((result) => result.data);
  }
  function confirmChange(org: string, body: ConfirmationInput, recovery: boolean) {
    const endpoint = recovery ? `/v1/platform/organizations/${pathId(org)}/primary-admin-recovery` : `/v1/orgs/${pathId(org)}/primary-admin-transfers`;
    return send(endpoint, { transfer_id: pathId(body.transfer_id), expected_version: body.expected_version, confirmation: body.confirmation },
      completion, { "If-Match": `"${body.expected_version}"` }, 200);
  }
  return {
    me: (signal?: AbortSignal) => read("/v1/me", me, signal),
    organizations: (options: ListOptions = {}, signal?: AbortSignal) => {
      const query = new URLSearchParams({ limit: "50" });
      for (const key of ["cursor", "search", "status", "organization_type"] as const) {
        const value = options[key];
        if (value !== undefined) query.set(key, value);
      }
      return read("/v1/platform/organizations?" + query.toString(), (value) => page(value, organization), signal);
    },
    organization: (org: string, signal?: AbortSignal) => read(`/v1/platform/organizations/${pathId(org)}`, executiveOrganization, signal),
    tenantOrganization: (org: string, signal?: AbortSignal) => read(`/v1/orgs/${pathId(org)}`, tenantOrganization, signal),
    members: (org: string, cursor?: string, signal?: AbortSignal) => {
      const query = new URLSearchParams({ limit: "100" }); if (cursor !== undefined) query.set("cursor", cursor);
      return read(`/v1/orgs/${pathId(org)}/members?${query}`, (value) => page(value, member), signal);
    },
    createOrganization: (body: CreateOrganization, key: string) => {
      if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(key)) throw new TypeError("A stable request key is required.");
      return send("/v1/platform/organizations", { name: body.name, organization_type: body.organization_type,
        contact_email: body.contact_email, primary_admin_email: body.primary_admin_email,
        home_region: body.home_region, reason: body.reason }, creation, { "Idempotency-Key": key }, 201);
    },
    initialJob: (org: string, id: string, signal?: AbortSignal) => read(`/v1/platform/organizations/${pathId(org)}/jobs/${pathId(id)}`, job, signal),
    tenantJob: (org: string, id: string, signal?: AbortSignal) => read(`/v1/orgs/${pathId(org)}/jobs/${pathId(id)}`, job, signal),
    recoveryJob: (org: string, id: string, signal?: AbortSignal) => read(`/v1/platform/organizations/${pathId(org)}/primary-admin-recovery/jobs/${pathId(id)}`, job, signal),
    previewTransfer: (org: string, body: PreviewInput) => previewChange(org, body, false),
    previewRecovery: (org: string, body: PreviewInput) => previewChange(org, body, true),
    confirmTransfer: (org: string, body: ConfirmationInput) => confirmChange(org, body, false),
    confirmRecovery: (org: string, body: ConfirmationInput) => confirmChange(org, body, true),
  };
}

export type FoundationClient = ReturnType<typeof createFoundationClient>;
export type Me = Awaited<ReturnType<FoundationClient["me"]>>;
export type Organization = Awaited<ReturnType<FoundationClient["organization"]>>;
export type TenantOrganization = Awaited<ReturnType<FoundationClient["tenantOrganization"]>>;
export type Member = Awaited<ReturnType<FoundationClient["members"]>>["items"][number];
export type Preview = Awaited<ReturnType<FoundationClient["previewTransfer"]>>;
export type Creation = Awaited<ReturnType<FoundationClient["createOrganization"]>>["data"];
export type Completion = Awaited<ReturnType<FoundationClient["confirmTransfer"]>>["data"];
export type Job = Awaited<ReturnType<FoundationClient["initialJob"]>>;
