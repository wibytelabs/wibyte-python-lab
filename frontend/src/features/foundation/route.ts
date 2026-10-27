/** A public feature flag selects a screen, never an authorization grant. */
export function isFoundationRoute(flag: string | undefined, pathname: string): boolean {
  return flag === "true" && (pathname === "/foundation" || pathname.startsWith("/foundation/"));
}
