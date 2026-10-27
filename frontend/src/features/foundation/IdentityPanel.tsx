import type { ReactNode } from "react";
import type { FoundationState } from "./session";

type Props = { state: FoundationState; onRetry: () => void; onSignOut: () => void; login: ReactNode; children?: ReactNode; primaryChanges?: ReactNode };

export default function IdentityPanel({ state, onRetry, onSignOut, login, children, primaryChanges }: Props) {
  const ready = state.kind === "ready" ? state.me : undefined;
  const active = ready?.user.global_state === "active";
  return <main className="foundation-shell">
    <header className="foundation-header"><div><p className="foundation-eyebrow">Wibyte</p><h1>Organization workspace</h1></div>
      <nav aria-label="Account"><a href="/">Legacy lab</a>{state.signedIn && <button type="button" onClick={onSignOut}>Sign out</button>}</nav>
    </header>
    {state.kind === "checking" && <section className="foundation-card" role="status"><h2>Checking your access</h2><p>Please wait while we check your current account.</p></section>}
    {state.kind === "guest" && login}
    {state.kind === "error" && <section className="foundation-card" role="alert"><h2>Account check unavailable</h2><p>{state.message}</p>
      {state.requestId && <p className="foundation-muted">Request reference: {state.requestId}</p>}
      <button type="button" onClick={onRetry}>Try again</button></section>}
    {ready && <>
      <section className="foundation-card"><h2>{active ? "Your organization access" : "Your account status"}</h2>
        {!active && <p role="status">{ready.user.global_state === "pending" ? "Your account is pending. An invitation or account approval does not automatically grant organization access."
          : "Your account cannot enter an organization right now. Contact an authorized administrator."}</p>}
        {active && <p>Organization access follows your current memberships and roles.</p>}
        <p className="foundation-muted">Account status: {ready.user.global_state}</p>
        <button type="button" onClick={onRetry}>Refresh access</button>
      </section>
      {active && ready.capabilities.includes("orgs") && <section className="foundation-card" aria-label="Organization management"><h2>Organization management</h2><p>Your current account has organization management access.</p>{children}</section>}
      {active && ready.capabilities.includes("recovery") && <section className="foundation-card" aria-label="Primary recovery"><h2>Primary recovery</h2><p>Primary recovery requires a reason, an eligible replacement and recent sign-in.</p></section>}
      {active && primaryChanges}
      <section className="foundation-card"><h2>Memberships</h2>
        {ready.memberships.items.length === 0 ? <p>No organization memberships are available.</p> : <ul className="foundation-memberships">
          {ready.memberships.items.map((member) => <li key={member.id}><strong>{member.organization_name}</strong>
            <span>{member.roles.join(", ")} · {member.status}</span><span>{active && member.can_enter ? "Available" : "Not available"}</span></li>)}
        </ul>}
        {ready.memberships.next_cursor && <p className="foundation-muted">More memberships are available. This view shows the first page.</p>}
      </section>
    </>}
  </main>;
}
