import { apiFetch, apiUrls } from "../../lib/api";
import { createFoundationClient } from "./client";

// The real browser adapter retains P01's URL validation, session lookup and
// bearer/cookie defaults. No public Supabase table is an authorization source.
export const foundationApi = createFoundationClient(apiUrls, apiFetch);
