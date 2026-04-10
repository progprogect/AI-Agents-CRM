"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { UserPlus, Trash2, RefreshCw } from "lucide-react";
import { canManageTeam, getAdminToken, isAuthenticated } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";

const getApiUrl = (): string => {
  if (typeof window !== "undefined" && !window.location.host.startsWith("localhost")) return "";
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
};

function authHeaders() {
  const token = getAdminToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface TeamMember {
  email: string;
  role: "owner" | "admin" | "member";
  invited_by: string | null;
  is_active: boolean;
  created_at: string;
}

const ROLE_LABELS: Record<string, string> = {
  owner: "Владелец",
  admin: "Администратор",
  member: "Участник",
};

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-purple-100 text-purple-800",
  admin: "bg-blue-100 text-blue-800",
  member: "bg-gray-100 text-gray-700",
};

export default function TeamPage() {
  const router = useRouter();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [invitePassword, setInvitePassword] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);

  const [removingEmail, setRemovingEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/admin/login");
    }
  }, [router]);

  const fetchMembers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/team/members`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      setMembers(await res.json());
    } catch {
      setError("Не удалось загрузить список участников.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchMembers();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/team/members`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: inviteRole,
          password: invitePassword || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Ошибка ${res.status}`);
      }
      setInviteEmail("");
      setInvitePassword("");
      setInviteRole("member");
      setShowInviteForm(false);
      await fetchMembers();
    } catch (err: unknown) {
      setInviteError(err instanceof Error ? err.message : "Ошибка приглашения.");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRemove = async (email: string) => {
    if (!confirm(`Удалить участника ${email}?`)) return;
    setRemovingEmail(email);
    try {
      const res = await fetch(
        `${getApiUrl()}/api/v1/team/members/${encodeURIComponent(email)}`,
        { method: "DELETE", headers: authHeaders() }
      );
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      await fetchMembers();
    } catch {
      setError("Не удалось удалить участника.");
    } finally {
      setRemovingEmail(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Команда</h1>
          <p className="text-sm text-gray-500 mt-1">
            Управление участниками вашей организации
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchMembers}>
            <RefreshCw className="w-4 h-4 mr-1" />
            Обновить
          </Button>
          {canManageTeam() && (
            <Button onClick={() => setShowInviteForm(!showInviteForm)}>
              <UserPlus className="w-4 h-4 mr-1" />
              Пригласить
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {showInviteForm && (
        <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-xl">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Пригласить участника</h2>
          <form onSubmit={handleInvite} className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Email</label>
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="user@example.com"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Роль</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "admin" | "member")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="member">Участник</option>
                <option value="admin">Администратор</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Пароль <span className="text-gray-400">(необязательно)</span>
              </label>
              <input
                type="password"
                value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Минимум 8 символов"
              />
            </div>
            {inviteError && (
              <p className="text-xs text-red-600">{inviteError}</p>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={inviteLoading}>
                {inviteLoading ? "Отправка..." : "Пригласить"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowInviteForm(false)}
              >
                Отмена
              </Button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {members.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">
            Нет участников в организации
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Роль</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Добавлен</th>
                {canManageTeam() && (
                  <th className="px-4 py-3" />
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {members.map((m) => (
                <tr key={m.email} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-gray-900">{m.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_COLORS[m.role] || "bg-gray-100"}`}
                    >
                      {ROLE_LABELS[m.role] ?? m.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {new Date(m.created_at).toLocaleDateString("ru-RU")}
                  </td>
                  {canManageTeam() && (
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleRemove(m.email)}
                        disabled={removingEmail === m.email}
                        className="text-gray-400 hover:text-red-500 disabled:opacity-40 transition-colors"
                        title="Удалить участника"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
