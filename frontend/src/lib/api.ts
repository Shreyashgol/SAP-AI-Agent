import axios, { type AxiosInstance } from "axios";

export interface APIResponse<T> {
  success: boolean;
  data: T | null;
  message?: string;
  request_id?: string;
}

export interface ErrorResponse {
  success: false;
  error: { code: string; message: string; field?: string };
  request_id?: string;
}

// ── Auth / tenant config ─────────────────────────────────────────────────────
// Every backend call needs an X-Tenant-ID header and a Bearer token (login itself
// also needs X-Tenant-ID). For the local demo we bootstrap a login with the seeded
// admin; override via Vite env vars in a real deployment / proper login flow.
const env =
  (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
const TENANT_ID = env.VITE_TENANT_ID ?? "2d829cfe-fb6f-40b8-9276-699b82b9ff5e";
const DEMO_EMAIL = env.VITE_DEMO_EMAIL ?? "demo@example.com";
const DEMO_PASSWORD = env.VITE_DEMO_PASSWORD ?? "Demo123!pass";

const TOKEN_KEY = "access_token";
const TENANT_KEY = "tenant_id";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function getTenant(): string {
  return localStorage.getItem(TENANT_KEY) ?? TENANT_ID;
}
function setAuth(token: string, tenant: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(TENANT_KEY, tenant);
}
function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TENANT_KEY);
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  roles: string[];
  domains: string[];
}

/** Sign in with email + password. The backend resolves the org from the email,
 * so we deliberately send NO X-Tenant-ID (raw axios, bypassing the interceptor). */
export async function signIn(email: string, password: string): Promise<AuthUser> {
  const res = await axios.post(
    "/api/v1/auth/login",
    { email, password },
    { headers: { "Content-Type": "application/json" }, withCredentials: true },
  );
  const data = res.data?.data ?? res.data;
  setAuth(data.access_token, data.user.tenant_id);
  return data.user as AuthUser;
}

/** Self-serve signup — creates a new organization and signs in. */
export async function signUp(
  organizationName: string,
  fullName: string,
  email: string,
  password: string,
): Promise<AuthUser> {
  const res = await axios.post(
    "/api/v1/auth/register",
    { organization_name: organizationName, full_name: fullName, email, password },
    { headers: { "Content-Type": "application/json" }, withCredentials: true },
  );
  const data = res.data?.data ?? res.data;
  setAuth(data.access_token, data.user.tenant_id);
  return data.user as AuthUser;
}

/** Continue with the seeded demo account (dev fallback). Single login call that
 * returns the user directly — no separate /auth/me round-trip, so a failure
 * surfaces the real login error (bad creds / backend or Redis down). */
export async function continueAsDemo(): Promise<AuthUser> {
  const res = await axios.post(
    "/api/v1/auth/login",
    { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    {
      headers: { "Content-Type": "application/json", "X-Tenant-ID": TENANT_ID },
      withCredentials: true,
    },
  );
  const data = res.data?.data ?? res.data;
  setAuth(data.access_token, data.user?.tenant_id ?? TENANT_ID);
  return data.user as AuthUser;
}

/** Current signed-in user from the token. */
export async function fetchMe(): Promise<AuthUser> {
  const res = await api.get("/auth/me");
  return (res.data?.data ?? res.data) as AuthUser;
}

/** Request a password reset. Returns a dev reset token when the backend has no
 * email service configured (non-production), else just a message. */
export async function forgotPassword(
  email: string,
): Promise<{ message: string; reset_token?: string | null }> {
  const res = await axios.post(
    "/api/v1/auth/forgot-password",
    { email },
    { headers: { "Content-Type": "application/json" } },
  );
  return res.data?.data ?? res.data;
}

/** Set a new password using a reset token. */
export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await axios.post(
    "/api/v1/auth/reset-password",
    { token, new_password: newPassword },
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function signOut(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } catch {
    /* best-effort — clear locally regardless */
  }
  clearAuth();
}

const api: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Attach tenant + bearer on every request.
api.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  (config.headers as Record<string, string>)["X-Tenant-ID"] = getTenant();
  const token = getToken();
  if (token) {
    (config.headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

let authInFlight: Promise<void> | null = null;

/** Ensure a valid token exists, logging in with the demo admin if needed. */
export async function ensureAuth(force = false): Promise<void> {
  if (!force && getToken()) return;
  if (authInFlight) return authInFlight;

  authInFlight = (async () => {
    const res = await axios.post(
      "/api/v1/auth/login",
      { email: DEMO_EMAIL, password: DEMO_PASSWORD },
      { headers: { "Content-Type": "application/json", "X-Tenant-ID": TENANT_ID } },
    );
    const data = res.data?.data ?? res.data;
    const token: string = data.access_token;
    const tenant: string = data.user?.tenant_id ?? TENANT_ID;
    setAuth(token, tenant);
  })().finally(() => {
    authInFlight = null;
  });

  return authInFlight;
}

// On 401, try a silent refresh (httpOnly cookie) once and retry; if that fails,
// clear the session so the app routes back to sign-in.
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      try {
        const res = await axios.post(
          "/api/v1/auth/refresh",
          {},
          { withCredentials: true, headers: { "X-Tenant-ID": getTenant() } },
        );
        const data = res.data?.data ?? res.data;
        if (data?.access_token) {
          localStorage.setItem(TOKEN_KEY, data.access_token);
          return api(original);
        }
      } catch {
        /* refresh failed */
      }
      clearAuth();
    }
    return Promise.reject(error);
  },
);

export { api as apiClient };
export default api;
