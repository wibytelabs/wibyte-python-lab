import { createApiUrls } from "./apiUrls.ts";

export type AccountStatus = "new" | "confirmed" | "unconfirmed";

/** Public lookup shared by signup and resend; no authentication dependency. */
export function createAccountLookup(
  configuredBase: string | undefined,
  pageOrigin: string,
  fetcher: typeof fetch,
) {
  const endpoint = createApiUrls(configuredBase, pageOrigin)
    .httpUrl("/auth/account-status");

  return async function lookupAccountStatus(email: string): Promise<AccountStatus> {
    const response = await fetcher(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Unable to check your account. Please try again."
      );
    }
    if (!["new", "confirmed", "unconfirmed"].includes(data?.status)) {
      throw new Error("Unable to check your account. Please try again.");
    }
    return data.status;
  };
}
