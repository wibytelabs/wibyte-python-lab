import { supabase } from "./supabase";
import { createApiUrls } from "./apiUrls";
import { createApiFetch } from "./apiClient";

export const apiUrls = createApiUrls(
  import.meta.env.VITE_API_URL,
  window.location.origin,
);
export const API_URL = apiUrls.httpBase;

const getSession = () => supabase.auth.getSession();
const fetcher = window.fetch.bind(window);

// Preserve the two existing callers' distinct cookie defaults.
export const apiFetch = createApiFetch(
  apiUrls.requestUrl, getSession, fetcher, { credentials: "include" },
);
export const settingsApiFetch = createApiFetch(
  apiUrls.requestUrl, getSession, fetcher,
);
