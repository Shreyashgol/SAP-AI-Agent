/** Turn an axios/network error from an auth call into a user-facing message,
 * distinguishing "backend unreachable" and server errors from API messages. */
export function authErrMessage(e: unknown, fallback = "Something went wrong."): string {
  const err = e as {
    response?: { status?: number; data?: { error?: { message?: string }; detail?: string } };
    request?: unknown;
  };
  if (err?.request && !err?.response) {
    return "Cannot reach the backend. Is the server running?";
  }
  const data = err?.response?.data;
  const status = err?.response?.status;
  if (status === 500) return "Server error. Please try again.";
  return data?.error?.message ?? data?.detail ?? fallback;
}
