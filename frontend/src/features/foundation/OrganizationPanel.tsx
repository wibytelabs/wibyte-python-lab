import { useEffect, useSyncExternalStore } from "react";
import type { OrganizationWorkspace } from "./organizations";
import OrganizationView from "./OrganizationView";

type Props = { workspace: OrganizationWorkspace; actor: string; pathname: string };
export default function OrganizationPanel({ workspace, actor, pathname }: Props) {
  const state = useSyncExternalStore(workspace.subscribe, workspace.getSnapshot, workspace.getSnapshot);
  useEffect(() => workspace.start(actor, pathname), [workspace, actor, pathname]);
  return <OrganizationView state={state} actor={actor} actions={workspace} />;
}
