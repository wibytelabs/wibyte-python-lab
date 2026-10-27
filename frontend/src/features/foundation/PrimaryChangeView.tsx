import type { FormEvent } from "react";
import type { PrimaryState, PrimaryWorkspace } from "./primaryChanges";

type Props = { state: PrimaryState; actor: string; actions: PrimaryWorkspace };
export default function PrimaryChangeView({ state, actor, actions }: Props) {
  if (state.actor !== actor) return <p role="status">Checking primary-change access…</p>;
  if (!state.recovery && state.memberships.length === 0) return null;
  const recovery = state.mode === "recovery";
  const frozen = state.preparing || state.confirming || state.uncertain || Boolean(state.preview || state.completion);
  const own = state.memberships.find((member) => member.org_id === state.org);
  const primary = state.detail?.status === "active" && state.detail.primary_admin_membership_id === own?.id;
  const targets = state.members.filter((member) => member.status === "active" && member.user_id && member.id !== own?.id && member.roles.includes("admin"));
  const preview = state.preview, result = state.completion;
  const invalid = (field: string) => Boolean(state.error?.fields[`body.${field}`]);
  function submit(event: FormEvent) { event.preventDefault();void actions.prepare(); }
  return <section className="foundation-card" aria-label="Protected primary changes"><h2>Protected Primary Admin changes</h2>
    <p>Review the current and replacement memberships before confirming. The server checks current authority, target eligibility, record version and recent sign-in.</p>
    <form onSubmit={submit}>
      <fieldset className="foundation-form" disabled={frozen}>
        <legend className="foundation-sr-only">Primary change scope and preview</legend>
        <label>Change type<select value={state.mode} onChange={(event) => actions.setMode(event.target.value === "recovery" ? "recovery" : "transfer")}>
          {state.memberships.length > 0 && <option value="transfer">Transfer my Primary Admin designation</option>}
          {state.recovery && <option value="recovery">Executive recovery for an explicit organization</option>}
        </select></label>
        {recovery ? <>
          <label>Organization reference<input required aria-invalid={invalid("org_id")} maxLength={36} value={state.org} onChange={(event) => actions.setOrganization(event.target.value)} /></label>
          <label>Reviewed current record version<input required aria-invalid={invalid("expected_version")} type="number" min={1} max={2147483647} step={1} value={state.version} onChange={(event) => actions.setField("version", event.target.value)} /></label>
          <label>Replacement administrator membership reference<input required aria-invalid={invalid("target_membership_id")} maxLength={36} value={state.target} onChange={(event) => actions.setField("target", event.target.value)} /></label>
        </> : <>
          <label>Organization<select required value={state.org} onChange={(event) => actions.setOrganization(event.target.value)}>
            <option value="">Choose your organization</option>{state.memberships.map((member) => <option key={member.id} value={member.org_id}>{member.organization_name}</option>)}
          </select></label>
          {primary && <label>Replacement active administrator<select required aria-invalid={invalid("target_membership_id")} value={state.target} onChange={(event) => actions.setField("target", event.target.value)}>
            <option value="">Choose a replacement</option>{targets.map((member) => <option key={member.id} value={member.id}>{member.full_name || "Administrator"} · {member.id}</option>)}
          </select></label>}
        </>}
        <label>Reason<textarea required aria-invalid={invalid("reason")} minLength={5} maxLength={1000} value={state.reason} onChange={(event) => actions.setField("reason", event.target.value)} /></label>
      </fieldset>
      {recovery && <p>Use the organization, version and eligible membership references from an authorized review. Recovery does not open a tenant roster or grant organization membership. Only an organization requiring recovery can complete this change.</p>}
      {!recovery && state.loading && <p role="status">Loading current organization and administrators…</p>}
      {!recovery && state.detail && <p>Current Primary Admin membership: {state.detail.primary_admin_membership_id} · Record version: {state.detail.version}</p>}
      {!recovery && state.detail && !primary && <p>Your membership is not the current Primary Admin. Only that person can use the ordinary transfer path.</p>}
      {!recovery && primary && !state.loading && targets.length === 0 && <p>No eligible replacement is shown on this page. Load more administrators if available.</p>}
      {!recovery && state.cursor && <button type="button" disabled={frozen || state.loading} onClick={() => { void actions.load(true); }}>Load more members</button>}
      {!recovery && state.org && <button type="button" disabled={frozen || state.loading} onClick={() => { void actions.load(); }}>Reload organization</button>}
      <button type="submit" disabled={frozen || state.loading || !state.org || !recovery && !primary}>{state.preparing ? "Preparing preview…" : "Review primary change"}</button>
    </form>
    {state.error && <div role="alert" className="foundation-error"><p>{state.error.message}</p>
      {Object.keys(state.error.fields).length > 0 && <p>Check the organization, replacement, version and reason fields.</p>}
      {state.error.requestId && <p className="foundation-muted">Request reference: {state.error.requestId}</p>}
      {state.error.code === "recent_auth_required" && <p>Sign in again to establish recent authentication, then reload and review a new preview.</p>}
      {state.error.code === "version_conflict" && <p>Reload the organization or obtain its current reviewed version, then review a new preview.</p>}
    </div>}
    {preview && <section className="foundation-result" aria-label="Confirm primary change"><h3>{recovery ? "Confirm executive recovery" : "Confirm Primary Admin transfer"}</h3>
      <dl className="foundation-detail"><dt>Organization</dt><dd>{preview.org_id}</dd><dt>Current primary membership</dt><dd>{preview.from_membership_id}</dd>
        <dt>Replacement membership</dt><dd>{preview.to_membership_id}</dd><dt>Expected version</dt><dd>{preview.expected_version}</dd>
        <dt>Preview expires</dt><dd>{preview.expires_at}</dd><dt>Reason</dt><dd>{state.reason}</dd></dl>
      <p>The former Primary Admin retains the ordinary admin role. This change does not remove a global account suspension.</p>
      <p>{recovery ? "Successful recovery restores the organization to active with the eligible replacement." : "The designated Primary Admin will change to the replacement membership."} Notification delivery remains a separate job.</p>
      <label className="foundation-confirm"><input type="checkbox" checked={state.acknowledged} disabled={state.confirming} onChange={(event) => actions.acknowledge(event.target.checked)} />
        I have reviewed the organization, current and replacement memberships, reason and consequences.</label>
      <button type="button" disabled={!state.acknowledged || state.confirming} onClick={() => { void actions.confirm(); }}>{state.confirming ? "Confirming…" : state.uncertain ? "Retry the same confirmation" : "Confirm primary change"}</button>
      {state.uncertain && <p>The result is uncertain and may already be committed. Retry this same confirmation to obtain the original result before starting another change.</p>}
    </section>}
    {result && <section className="foundation-result" aria-label="Primary change result"><h3>Primary change recorded</h3>
      <p>{state.replayed ? "The original committed result was returned. No second designation change was made." : "The designation change was committed."}</p>
      <p>Organization: {result.org_id}<br />Current Primary Admin membership: {result.primary_admin_membership_id}<br />Record version: {result.version}</p>
      <p>The former primary retains the ordinary admin role. Existing global account blocks remain in force.</p>
      <p>Notification job: {result.job_id}. Delivery integration is pending. No delivery is confirmed.</p>
      {state.job && <p>Current notification status: {state.job.state} · {state.job.delivery_status.replaceAll("_", " ")}</p>}
      <button type="button" disabled={state.jobBusy} onClick={() => { void actions.refreshJob(); }}>{state.jobBusy ? "Refreshing notification…" : "Refresh notification job"}</button>
    </section>}
    {(preview || result || state.uncertain) && <button type="button" disabled={state.confirming || state.preparing} onClick={actions.reset}>Clear this review to start another change</button>}
  </section>;
}
