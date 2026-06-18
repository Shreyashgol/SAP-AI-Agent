import { useState } from "react";
import { UserPlus, Shield, ToggleLeft, ToggleRight, ChevronDown, ChevronRight } from "lucide-react";
import {
  useAdminUsers,
  useAdminRoles,
  useInviteUser,
  usePatchAdminUser,
  useAssignRole,
  type AdminUser,
} from "@/hooks/useAdmin";

// ── Invite form ───────────────────────────────────────────────────────────────

function InviteForm({ onClose }: { onClose: () => void }) {
  const { data: roles } = useAdminRoles();
  const invite = useInviteUser();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [roleId, setRoleId] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !fullName.trim()) return;
    await invite.mutateAsync({ email, full_name: fullName, role_id: roleId || undefined });
    onClose();
  }

  return (
    <form onSubmit={handleSubmit} className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 bg-gray-50 dark:bg-gray-800/60 space-y-4">
      <h3 className="font-medium text-gray-900 dark:text-gray-100">Invite User</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Full name</label>
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Jane Smith"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="jane@company.com"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Initial role (optional)</label>
          <select
            value={roleId}
            onChange={(e) => setRoleId(e.target.value)}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">No role</option>
            {(roles ?? []).map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white">Cancel</button>
        <button
          type="submit"
          disabled={invite.isPending}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-40"
        >
          {invite.isPending ? "Inviting…" : "Send invite"}
        </button>
      </div>
      {invite.isError && (
        <p className="text-xs text-red-600 dark:text-red-400">{(invite.error as Error).message}</p>
      )}
    </form>
  );
}

// ── User row ──────────────────────────────────────────────────────────────────

function UserRow({ user }: { user: AdminUser }) {
  const { data: roles } = useAdminRoles();
  const patch = usePatchAdminUser();
  const assignRole = useAssignRole();
  const [expanded, setExpanded] = useState(false);
  const [addingRole, setAddingRole] = useState(false);
  const [selectedRoleId, setSelectedRoleId] = useState("");

  function toggleActive() {
    patch.mutate({ id: user.id, body: { is_active: !user.is_active } });
  }

  async function handleAssign() {
    if (!selectedRoleId) return;
    await assignRole.mutateAsync({ userId: user.id, roleId: selectedRoleId });
    setAddingRole(false);
    setSelectedRoleId("");
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
      <div className="flex items-center gap-4 p-4 bg-white dark:bg-gray-800">
        {/* Expand toggle */}
        <button onClick={() => setExpanded((v) => !v)} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>

        {/* Avatar initials */}
        <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-700 dark:text-blue-300 flex items-center justify-center text-sm font-semibold shrink-0">
          {user.full_name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user.full_name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user.email}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {user.is_sso && (
            <span className="text-xs px-2 py-0.5 bg-violet-50 dark:bg-violet-950/40 text-violet-600 border border-violet-200 rounded">SSO</span>
          )}
          <button
            onClick={toggleActive}
            disabled={patch.isPending}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              user.is_active
                ? "bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-300 border-green-200 dark:border-green-900 hover:bg-green-100"
                : "bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
            }`}
            title={user.is_active ? "Click to deactivate" : "Click to activate"}
          >
            {user.is_active ? (
              <><ToggleRight className="w-3.5 h-3.5" /> Active</>
            ) : (
              <><ToggleLeft className="w-3.5 h-3.5" /> Inactive</>
            )}
          </button>
        </div>
      </div>

      {/* Role management panel */}
      {expanded && (
        <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/60 px-4 py-3 space-y-3">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Roles</p>

          {addingRole ? (
            <div className="flex items-center gap-2">
              <select
                value={selectedRoleId}
                onChange={(e) => setSelectedRoleId(e.target.value)}
                className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select role…</option>
                {(roles ?? []).map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
              <button
                onClick={handleAssign}
                disabled={!selectedRoleId || assignRole.isPending}
                className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-40"
              >
                Assign
              </button>
              <button onClick={() => setAddingRole(false)} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">Cancel</button>
            </div>
          ) : (
            <button
              onClick={() => setAddingRole(true)}
              className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800"
            >
              <Shield className="w-3.5 h-3.5" /> Add role
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { data: users, isLoading, isError } = useAdminUsers();
  const [showInvite, setShowInvite] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = (users ?? []).filter(
    (u) =>
      u.full_name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Admin — User Management</h1>
        <button
          onClick={() => setShowInvite((v) => !v)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
        >
          <UserPlus className="w-4 h-4" />
          Invite user
        </button>
      </div>

      {showInvite && <InviteForm onClose={() => setShowInvite(false)} />}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search users…"
        className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-100 dark:bg-gray-800 rounded-xl" />
          ))}
        </div>
      )}

      {isError && (
        <div className="text-center py-12 text-sm text-red-500">
          Could not load users. You may not have admin access.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <p className="text-center py-12 text-sm text-gray-400 dark:text-gray-500">No users found.</p>
          ) : (
            filtered.map((user) => <UserRow key={user.id} user={user} />)
          )}
        </div>
      )}

      <p className="text-xs text-gray-400 dark:text-gray-500 text-right">
        {filtered.length} of {users?.length ?? 0} user{users?.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}
