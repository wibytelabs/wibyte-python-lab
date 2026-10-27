import type { FormEvent } from "react";
import type { OrganizationState, OrganizationWorkspace, OrganizationUIError } from "./organizations";

type Props = { state: OrganizationState; actor: string; actions: OrganizationWorkspace };
function ErrorNotice({ error }: { error?: OrganizationUIError }) {
  return error ? <div role="alert" className="foundation-error"><p>{error.message}</p>
    {error.requestId && <p className="foundation-muted">Request reference: {error.requestId}</p>}</div> : null;
}

export default function OrganizationView({ state, actor, actions }: Props) {
  if (state.actor !== actor) return <p role="status">Loading organization access…</p>;
  if (state.routeError) return <div role="alert"><p>{state.routeError}</p><button type="button" onClick={actions.home}>Organization directory</button></div>;
  const fields = [
    ["name", "Organization name", "text", 160], ["contact_email", "Contact email", "email", 254],
    ["primary_admin_email", "Initial Primary Admin email", "email", 254], ["home_region", "Home region", "text", 64],
  ] as const;
  const receipt = state.creation;
  const showReceipt = receipt && (!state.selected || state.selected === receipt.org_id);
  function submit(event: FormEvent) { event.preventDefault(); void actions.create(); }
  return <div className="foundation-organizations">
    {state.selected ? <section aria-label="Organization detail">
      <div className="foundation-toolbar"><h3>Organization detail</h3><button type="button" onClick={actions.home}>Back to directory</button></div>
      {state.detailBusy && <p role="status">Loading organization…</p>}<ErrorNotice error={state.detailError} />
      {state.detail && <><h4>{state.detail.name}</h4><dl className="foundation-detail">
        <dt>Status</dt><dd>{state.detail.status.replaceAll("_", " ")}</dd><dt>Type</dt><dd>{state.detail.organization_type}</dd>
        <dt>Contact email</dt><dd>{state.detail.contact_email}</dd><dt>Home region</dt><dd>{state.detail.home_region}</dd>
        <dt>Record version</dt><dd>{state.detail.version}</dd><dt>Primary membership</dt><dd>{state.detail.primary_admin_membership_id}</dd>
      </dl><p className="foundation-muted">Organization reference: {state.detail.id}</p>
        {state.detail.status === "pending" && <p>Pending organizations do not grant tenant access. Invitation acceptance and activation are separate steps.</p>}
        {state.detail.status === "recovery_required" && <p>Primary recovery is required. Ordinary status changes cannot bypass recovery.</p>}
        <a href={`/foundation/orgs/${state.detail.id}`}>Link to this organization</a>
      </>}
      <button type="button" onClick={actions.refreshDetail} disabled={state.detailBusy}>Refresh organization</button>
    </section> : <>
      <section aria-label="Organization directory"><h3>Organization directory</h3>
        <form className="foundation-toolbar" onSubmit={(event) => { event.preventDefault(); void actions.search(); }}>
          <label>Search organizations<input maxLength={120} value={state.search} onChange={(event) => actions.setSearch(event.target.value)} /></label>
          <button type="submit" disabled={state.directoryBusy}>Search</button>
        </form><ErrorNotice error={state.directoryError} />
        {state.directoryBusy && <p role="status">Loading directory…</p>}
        {state.directory && (state.directory.items.length === 0 ? <p>No matching organizations.</p> : <ul className="foundation-directory">
          {state.directory.items.map((org) => <li key={org.id}><button type="button" onClick={() => { void actions.select(org.id); }}>{org.name}</button>
            <span>{org.organization_type} · {org.status.replaceAll("_", " ")} · {org.home_region}</span></li>)}
        </ul>)}
        {state.directory?.next_cursor && <button type="button" disabled={state.directoryBusy} onClick={() => { void actions.loadMore(); }}>Load more organizations</button>}
      </section>
      <section aria-label="Create pending organization"><h3>Create a pending organization</h3>
        <p>The initial Primary Admin receives an invitation. Creating this record does not approve an account or activate organization access.</p>
        <ErrorNotice error={state.createError} />
        <form onSubmit={submit}>
          <fieldset className="foundation-form" disabled={state.locked || state.creating}>
            <legend className="foundation-sr-only">Organization and initial invitation</legend>
            {fields.map(([field, label, type, max]) => <label key={field} htmlFor={`foundation-${field}`}>{label}
              <input id={`foundation-${field}`} type={type} maxLength={max} required value={state.form[field]}
                aria-invalid={Boolean(state.createError?.fields[`body.${field}`])}
                aria-describedby={state.createError?.fields[`body.${field}`] ? `foundation-${field}-error` : undefined}
                onChange={(event) => actions.setField(field, event.target.value)} />
              {state.createError?.fields[`body.${field}`] && <span id={`foundation-${field}-error`} className="foundation-field-error">Check this field.</span>}
            </label>)}
            <label>Organization type<select value={state.form.organization_type} onChange={(event) => actions.setField("organization_type", event.target.value)}>
              <option value="school">School</option><option value="university">University</option><option value="training">Training</option><option value="other">Other</option>
            </select></label>
            <label>Reason<textarea minLength={5} maxLength={1000} required value={state.form.reason}
              aria-invalid={Boolean(state.createError?.fields["body.reason"])} onChange={(event) => actions.setField("reason", event.target.value)} /></label>
          </fieldset>
          <button type="submit" disabled={state.creating || Boolean(state.creation)}>{state.creating ? "Creating…" : state.locked ? "Retry same request" : "Create pending organization"}</button>
        </form>
        {state.locked && !state.creation && !state.creating && <p>The earlier request may have completed. Retry these same values, or check the directory before starting another request.</p>}
        {state.locked && <button type="button" disabled={state.creating} onClick={actions.newRequest}>Start a new request</button>}
      </section>
    </>}
    {showReceipt && <section aria-label="Initial invitation status" className="foundation-result">
      <h3>Pending organization recorded</h3><p>{state.replayed ? "The original committed result was returned. No second organization was created." : "The organization and initial invitation were recorded."}</p>
      <p>The designated membership is pending invitation acceptance. Delivery integration is pending until a configured adapter acknowledges the job.</p>
      <p className="foundation-muted">Organization reference: {receipt.org_id}<br />Job reference: {receipt.job_id}</p>
      {!state.selected && <button type="button" onClick={() => { void actions.select(receipt.org_id); }}>View organization</button>}
      <ErrorNotice error={state.jobError} />
      {state.job && <><p>Job status: {state.job.state}</p><p>{state.job.delivery_status === "simulated" ? "Simulated test result. No real delivery is confirmed."
        : state.job.delivery_status === "provider_accepted" ? "Provider accepted the request. Inbox delivery is not confirmed." : "Delivery integration pending. No delivery is confirmed."}</p>
        {state.job.last_error_code && <p className="foundation-muted">Job error code: {state.job.last_error_code}</p>}</>}
      <button type="button" disabled={state.jobBusy} onClick={() => { void actions.refreshJob(); }}>{state.jobBusy ? "Refreshing job…" : "Refresh invitation job"}</button>
    </section>}
  </div>;
}
