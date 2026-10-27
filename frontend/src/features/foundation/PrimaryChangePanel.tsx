import { useEffect, useSyncExternalStore } from "react";
import type { Me } from "./client";
import type { PrimaryWorkspace } from "./primaryChanges";
import PrimaryChangeView from "./PrimaryChangeView";
type Props = { workspace: PrimaryWorkspace; me: Me };
export default function PrimaryChangePanel({ workspace, me }: Props) {
  const state = useSyncExternalStore(workspace.subscribe, workspace.getSnapshot, workspace.getSnapshot);
  useEffect(() => workspace.start(me), [workspace, me]);
  return <PrimaryChangeView state={state} actor={me.user.id} actions={workspace} />;
}
