import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles, Loader2 } from "lucide-react";
import { useAuth } from "@/stores/auth";

function errMessage(e: unknown): string {
  const detail = (e as { response?: { data?: { error?: { message?: string }; detail?: string } } })
    ?.response?.data;
  return detail?.error?.message ?? detail?.detail ?? "Could not create your account.";
}

export default function SignUpPage() {
  const navigate = useNavigate();
  const { signUp } = useAuth();
  const [org, setOrg] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordTooShort = password.length > 0 && password.length < 8;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit =
    org.trim() && fullName.trim() && email.trim() && password.length >= 8 && confirm === password;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      await signUp(org.trim(), fullName.trim(), email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500";

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white shadow-sm mb-3">
            <Sparkles className="w-5 h-5" />
          </div>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Create your organization</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Set up a new SAP B1 workspace</p>
        </div>

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
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Organization name</label>
            <input value={org} onChange={(e) => setOrg(e.target.value)} required className={inputClass} placeholder="Acme Inc." />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Your name</label>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required className={inputClass} placeholder="Jane Doe" />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required className={inputClass} placeholder="you@company.com" />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required className={inputClass} placeholder="At least 8 characters" />
            {passwordTooShort && <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">Use at least 8 characters.</p>}
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
            Create organization
          </button>
        </form>

        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-4">
          Already have an account?{" "}
          <Link to="/signin" className="text-blue-600 dark:text-blue-400 font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
