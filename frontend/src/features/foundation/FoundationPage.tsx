import { useEffect, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import type { FoundationClient } from "./client";
import { createFoundationSession } from "./session";
import type { FoundationAuth } from "./session";
import IdentityPanel from "./IdentityPanel";
import OrganizationPanel from "./OrganizationPanel";
import PrimaryChangePanel from "./PrimaryChangePanel";
import { createPrimaryWorkspace, primaryAccess } from "./primaryChanges";
import { createOrganizationWorkspace } from "./organizations";

type Props = { auth: FoundationAuth; api: FoundationClient; login: ReactNode; pathname?: string };

export default function FoundationPage({ auth, api, login, pathname = "/foundation" }: Props) {
  const [session] = useState(() => createFoundationSession(auth, api));
  const [organizations] = useState(() => createOrganizationWorkspace(api));
  const [primary] = useState(() => createPrimaryWorkspace(api));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  useEffect(() => session.start(), [session]);
  const canManage = state.kind === "ready" && state.me.user.global_state === "active" && state.me.capabilities.includes("orgs");
  useEffect(() => {
    if (state.kind === "guest" || state.kind === "ready" && !canManage) organizations.clear();
  }, [state.kind, canManage, organizations]);
  const access = state.kind === "ready" ? primaryAccess(state.me) : undefined;
  const canChange = Boolean(access && (access.recovery || access.memberships.length > 0));
  useEffect(() => {
    if (state.kind === "guest" || state.kind === "ready" && !canChange) primary.clear();
  }, [state.kind, canChange, primary]);
  return <IdentityPanel state={state} onRetry={session.reload} onSignOut={() => { void session.signOut(); }} login={login}
    primaryChanges={canChange && state.kind === "ready" ? <PrimaryChangePanel workspace={primary} me={state.me} /> : null}>
    {canManage && state.kind === "ready" && <OrganizationPanel workspace={organizations} actor={state.me.user.id} pathname={pathname} />}
  </IdentityPanel>;
}
