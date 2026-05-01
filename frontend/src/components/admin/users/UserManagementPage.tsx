"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi, type UserResponse, type UserCreateRequest, type UserUpdateRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";

type UserRole = "admin" | "qa" | "dev";

const ROLE_BADGE: Record<UserRole, string> = {
  admin: "bg-purple-500/20 text-purple-300 border border-purple-500/30",
  qa: "bg-green-500/20 text-green-300 border border-green-500/30",
  dev: "bg-blue-500/20 text-blue-300 border border-blue-500/30",
};

// ─────────────────────────────────────────────────────────────────────────────
// Create/Edit modal
// ─────────────────────────────────────────────────────────────────────────────

interface UserFormModal {
  mode: "create" | "edit";
  user?: UserResponse;
  onClose: () => void;
  onSave: (data: UserCreateRequest | UserUpdateRequest, username?: string) => void;
  saving: boolean;
  error: string | null;
}

function UserFormModal({ mode, user, onClose, onSave, saving, error }: UserFormModal) {
  const [username, setUsername] = useState(user?.username ?? "");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [role, setRole] = useState<UserRole>(user?.role ?? "qa");
  const [isActive, setIsActive] = useState(user?.is_active ?? true);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "create") {
      onSave({ username, password, full_name: fullName, role } as UserCreateRequest);
    } else {
      const updates: UserUpdateRequest = { full_name: fullName, role, is_active: isActive };
      if (password) updates.password = password;
      onSave(updates, user?.username);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-[#1a2234] border border-white/10 rounded-2xl p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-white mb-5">
          {mode === "create" ? "Create User" : `Edit: ${user?.username}`}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "create" && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Username</label>
              <input
                required
                minLength={3}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[#0d1420] border border-white/10 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/60"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Full Name</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[#0d1420] border border-white/10 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/60"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Password {mode === "edit" && <span className="text-gray-600">(leave blank to keep)</span>}
            </label>
            <input
              type="password"
              required={mode === "create"}
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[#0d1420] border border-white/10 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/60"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="w-full px-3 py-2 rounded-lg bg-[#0d1420] border border-white/10 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/60"
            >
              <option value="admin">Admin — full access</option>
              <option value="qa">QA — all except LLM chat</option>
              <option value="dev">Dev — all except create pipeline</option>
            </select>
          </div>

          {mode === "edit" && (
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="rounded"
              />
              <span className="text-sm text-gray-300">Active</span>
            </label>
          )}

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-white/10 text-gray-300 text-sm hover:bg-white/5 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold transition"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export function UserManagementPage() {
  const { isAdmin, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [modal, setModal] = useState<{ mode: "create" | "edit"; user?: UserResponse } | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: authApi.listUsers,
    enabled: isAdmin,
  });

  const createMutation = useMutation({
    mutationFn: (data: UserCreateRequest) => authApi.createUser(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setModal(null); },
    onError: (err: Error) => setModalError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ username, data }: { username: string; data: UserUpdateRequest }) =>
      authApi.updateUser(username, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setModal(null); },
    onError: (err: Error) => setModalError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (username: string) => authApi.deleteUser(username),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setDeleteTarget(null); },
  });

  if (!authLoading && !isAdmin) {
    router.replace("/pipelines");
    return null;
  }

  const handleSave = (data: UserCreateRequest | UserUpdateRequest, username?: string) => {
    setModalError(null);
    if (modal?.mode === "create") {
      createMutation.mutate(data as UserCreateRequest);
    } else if (username) {
      updateMutation.mutate({ username, data: data as UserUpdateRequest });
    }
  };

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="min-h-screen bg-[#101622] p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">User Management</h1>
            <p className="text-sm text-gray-400 mt-1">Manage application users and their roles</p>
          </div>
          <button
            onClick={() => { setModal({ mode: "create" }); setModalError(null); }}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition"
          >
            + New User
          </button>
        </div>

        {/* Role permission legend */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {(["admin", "qa", "dev"] as UserRole[]).map((r) => (
            <div key={r} className="bg-[#1a2234] border border-white/10 rounded-xl p-4">
              <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium mb-2 ${ROLE_BADGE[r]}`}>
                {r.toUpperCase()}
              </span>
              <p className="text-xs text-gray-400">
                {r === "admin" && "Full access to everything"}
                {r === "qa" && "All features except LLM chat"}
                {r === "dev" && "All features except creating pipeline templates"}
              </p>
            </div>
          ))}
        </div>

        {/* Users table */}
        <div className="bg-[#1a2234] border border-white/10 rounded-2xl overflow-hidden">
          {isLoading ? (
            <div className="p-8 text-center text-gray-500">Loading users…</div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-gray-500">No users found.</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left px-5 py-3 text-xs font-medium text-gray-400">Username</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-gray-400">Full Name</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-gray-400">Role</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-gray-400">Status</th>
                  <th className="text-right px-5 py-3 text-xs font-medium text-gray-400">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {users.map((u) => (
                  <tr key={u.username} className="hover:bg-white/2 transition">
                    <td className="px-5 py-3.5 text-sm font-mono text-white">{u.username}</td>
                    <td className="px-5 py-3.5 text-sm text-gray-300">{u.full_name || "—"}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_BADGE[u.role]}`}>
                        {u.role.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${u.is_active ? "bg-green-400" : "bg-gray-600"}`} />
                      <span className={`text-xs ${u.is_active ? "text-green-400" : "text-gray-500"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right space-x-2">
                      <button
                        onClick={() => { setModal({ mode: "edit", user: u }); setModalError(null); }}
                        className="text-xs px-3 py-1 rounded-lg border border-white/10 text-gray-300 hover:bg-white/5 transition"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setDeleteTarget(u.username)}
                        className="text-xs px-3 py-1 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Create / Edit modal */}
      {modal && (
        <UserFormModal
          mode={modal.mode}
          user={modal.user}
          onClose={() => setModal(null)}
          onSave={handleSave}
          saving={saving}
          error={modalError}
        />
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm bg-[#1a2234] border border-white/10 rounded-2xl p-6 shadow-2xl">
            <h2 className="text-base font-semibold text-white mb-2">Delete user?</h2>
            <p className="text-sm text-gray-400 mb-5">
              Are you sure you want to delete <strong className="text-white">{deleteTarget}</strong>? This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="flex-1 py-2 rounded-lg border border-white/10 text-gray-300 text-sm hover:bg-white/5 transition"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget!)}
                disabled={deleteMutation.isPending}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm font-semibold transition"
              >
                {deleteMutation.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
