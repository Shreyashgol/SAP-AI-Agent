import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { KeyRound, Loader2, ArrowRight } from "lucide-react";
import { forgotPassword } from "@/lib/api";
import { authErrMessage } from "@/lib/authError";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await forgotPassword(email.trim());
      setSent(true);
      setDevToken(res.reset_token ?? null);
    } catch (err) {
      setError(authErrMessage(err, "Could not start the reset."));
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
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Reset your password</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">We'll send a reset link to your email</p>
        </div>

        {!sent ? (
          <form
            onSubmit={onSubmit}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm space-y-4"
          >
            {error && (
              <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-100 dark:border-red-900 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="you@company.com"
              />
            </div>
            <button
              type="submit"
              disabled={busy || !email}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Send reset link
            </button>
          </form>
        ) : (
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm space-y-4">
            <p className="text-sm text-gray-700 dark:text-gray-200">
              If an account exists for <span className="font-medium">{email}</span>, a password reset
              link has been issued.
            </p>
            {devToken ? (
              <>
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  No email service is configured, so here's your reset link (dev mode):
                </p>
                <button
                  onClick={() => navigate(`/reset-password?token=${encodeURIComponent(devToken)}`)}
                  className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-blue-700 transition-colors"
                >
                  Set a new password <ArrowRight className="w-4 h-4" />
                </button>
              </>
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Check your inbox and follow the link to set a new password.
              </p>
            )}
          </div>
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
