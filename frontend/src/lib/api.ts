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
const TENANT_ID = env.VITE_TENANT_ID ?? "a480c09a-6cf4-463d-a052-53e01707a4b2";
const DEMO_EMAIL = env.VITE_DEMO_EMAIL ?? "onboarder@testcorp.com";
const DEMO_PASSWORD = env.VITE_DEMO_PASSWORD ?? "Admin123!pass";

const TOKEN_KEY = "access_token";
const TENANT_KEY = "tenant_id";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
function getTenant(): string {
  return localStorage.getItem(TENANT_KEY) ?? TENANT_ID;
}
function setAuth(token: string, tenant: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(TENANT_KEY, tenant);
}
function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
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

// On 401, drop the token, re-login once, and retry the original request.
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      clearAuth();
      try {
        await ensureAuth(true);
        return api(original);
      } catch {
        /* fall through to reject */
      }
    }
    return Promise.reject(error);
  },
);

export { api as apiClient };
export default api;
