import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, Loader2, CheckCircle2 } from "lucide-react";
import { resetPassword } from "@/lib/api";
import { authErrMessage } from "@/lib/authError";

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const tooShort = password.length > 0 && password.length < 8;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = token.trim() && password.length >= 8 && confirm === password;

  const inputClass =
    "w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token.trim(), password);
      setDone(true);
      setTimeout(() => navigate("/signin", { replace: true }), 1500);
    } catch (err) {
      setError(authErrMessage(err, "Could not reset the password. The link may have expired."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white shadow-sm mb-3">
            <KeyRound className="w-5 h-5" />
          </div>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Set a new password</h1>
        </div>

        {done ? (
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0" />
            <p className="text-sm text-gray-700 dark:text-gray-200">
              Password updated. Redirecting you to sign in…
            </p>
          </div>
        ) : (
          <form
            onSubmit={onSubmit}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm space-y-4"
          >
            {error && (
              <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-100 dark:border-red-900 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {!params.get("token") && (
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Reset token</label>
                <input value={token} onChange={(e) => setToken(e.target.value)} required className={inputClass} placeholder="Paste your reset token" />
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">New password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required className={inputClass} placeholder="At least 8 characters" />
              {tooShort && <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">Use at least 8 characters.</p>}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Confirm password</label>
              <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required className={inputClass} placeholder="Re-enter password" />
              {mismatch && <p className="text-xs text-red-500 dark:text-red-400 mt-1">Passwords don't match.</p>}
            </div>

            <button
              type="submit"
              disabled={busy || !canSubmit}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Update password
            </button>
          </form>
        )}

        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-4">
          <Link to="/signin" className="text-blue-600 dark:text-blue-400 font-medium hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
