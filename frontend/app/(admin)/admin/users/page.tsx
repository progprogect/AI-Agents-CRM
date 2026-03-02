/** Admin Users management page — super admin only. */

"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { UserPlus, Trash2 } from "lucide-react";
import { isSuperAdmin, getAdminToken } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";

const getApiUrl = (): string => {
  if (typeof window !== "undefined" && !window.location.host.startsWith("localhost")) return "";
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
};

interface AdminUser {
  email: string;
  created_by: string;
  is_active: boolean;
  created_at: string | null;
}

function authHeaders() {
  const token = getAdminToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function UsersPage() {
  const router = useRouter();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);

  const [removingEmail, setRemovingEmail] = useState<string | null>(null);

  // Guard: only super admins
  useEffect(() => {
    if (!isSuperAdmin()) {
      router.replace("/admin/agents");
    }
  }, [router]);

  const fetchUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/admin/auth/users`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      setUsers(await res.json());
    } catch (e) {
      setError("Failed to load users.");
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isSuperAdmin()) fetchUsers();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/admin/auth/users`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ email: inviteEmail.trim().toLowerCase() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setInviteError(data?.detail ?? "Failed to add user.");
        return;
      }
      setInviteEmail("");
      setShowInviteForm(false);
      await fetchUsers();
    } catch {
      setInviteError("Unable to connect.");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRemove = async (email: string) => {
    if (!confirm(`Remove access for ${email}?`)) return;
    setRemovingEmail(email);
    try {
      const res = await fetch(
        `${getApiUrl()}/api/v1/admin/auth/users/${encodeURIComponent(email)}`,
        { method: "DELETE", headers: authHeaders() }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data?.detail ?? "Failed to remove user.");
        return;
      }
      await fetchUsers();
    } catch {
      alert("Unable to connect.");
    } finally {
      setRemovingEmail(null);
    }
  };

  if (!isSuperAdmin()) return null;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Users</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage who can access the admin panel.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          icon={<UserPlus size={16} />}
          onClick={() => { setShowInviteForm(!showInviteForm); setInviteError(null); }}
        >
          Add User
        </Button>
      </div>

      {/* Invite form */}
      {showInviteForm && (
        <form
          onSubmit={handleInvite}
          className="mb-6 p-4 border border-[#BEBAB7] rounded-sm bg-white"
        >
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Email address
          </label>
          <div className="flex gap-2">
            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-sm text-sm focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C]"
              disabled={inviteLoading}
            />
            <Button type="submit" variant="primary" size="sm" isLoading={inviteLoading}>
              Send Invite
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => { setShowInviteForm(false); setInviteEmail(""); setInviteError(null); }}
            >
              Cancel
            </Button>
          </div>
          {inviteError && (
            <p className="mt-2 text-sm text-red-600">{inviteError}</p>
          )}
          <p className="mt-2 text-xs text-gray-500">
            The user will be able to log in via email OTP immediately.
          </p>
        </form>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-sm">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Users table */}
      <div className="bg-white rounded-sm shadow-sm border border-[#BEBAB7] overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#EEEAE7]">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-[#443C3C] uppercase tracking-wider text-xs">
                Email
              </th>
              <th className="px-4 py-3 text-left font-medium text-[#443C3C] uppercase tracking-wider text-xs">
                Added by
              </th>
              <th className="px-4 py-3 text-left font-medium text-[#443C3C] uppercase tracking-wider text-xs">
                Status
              </th>
              <th className="px-4 py-3 text-left font-medium text-[#443C3C] uppercase tracking-wider text-xs">
                Date
              </th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="py-12 text-center">
                  <LoadingSpinner size="sm" />
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-12 text-center text-gray-500 text-sm">
                  No regular users yet. Use "Add User" to grant access.
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr
                  key={user.email}
                  className="border-t border-[#EEEAE7] hover:bg-[#EEEAE7]/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-gray-900 truncate max-w-[180px]">
                    {user.email}
                  </td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-[140px]">
                    {user.created_by}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium ${
                        user.is_active
                          ? "bg-green-100 text-green-800"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {user.created_at
                      ? new Date(user.created_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {user.is_active && (
                      <button
                        onClick={() => handleRemove(user.email)}
                        disabled={removingEmail === user.email}
                        className="inline-flex items-center justify-center w-8 h-8 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors duration-150 disabled:opacity-50"
                        aria-label={`Remove ${user.email}`}
                      >
                        {removingEmail === user.email ? (
                          <LoadingSpinner size="sm" />
                        ) : (
                          <Trash2 size={15} />
                        )}
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-gray-400">
        Super admins defined in <code className="bg-gray-100 px-1 rounded">ALLOWED_ADMIN_EMAILS</code> env var are not shown here and cannot be managed through the UI.
      </p>
    </div>
  );
}
