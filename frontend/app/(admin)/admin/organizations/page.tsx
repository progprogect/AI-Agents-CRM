"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Plus, ToggleLeft, ToggleRight, Users } from "lucide-react";
import { isPlatformAdmin, getAdminToken, isAuthenticated } from "@/lib/auth";
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

interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_by: string;
  created_at: string;
}

interface OrgMember {
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export default function OrganizationsPage() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [expandedOrg, setExpandedOrg] = useState<string | null>(null);
  const [orgMembers, setOrgMembers] = useState<Record<string, OrgMember[]>>({});

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/admin/login");
      return;
    }
    if (!isPlatformAdmin()) {
      router.replace("/admin/agents");
    }
  }, [router]);

  const fetchOrgs = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/platform/orgs`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      setOrgs(await res.json());
    } catch {
      setError("Не удалось загрузить список организаций.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isPlatformAdmin()) fetchOrgs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/platform/orgs`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          name,
          owner_email: ownerEmail,
          owner_password: ownerPassword || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Ошибка ${res.status}`);
      }
      setName("");
      setOwnerEmail("");
      setOwnerPassword("");
      setShowCreate(false);
      await fetchOrgs();
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Ошибка создания.");
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (org: Organization) => {
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/platform/orgs/${org.id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ is_active: !org.is_active }),
      });
      if (!res.ok) throw new Error("Ошибка обновления.");
      await fetchOrgs();
    } catch {
      setError("Не удалось обновить статус организации.");
    }
  };

  const loadMembers = async (orgId: string) => {
    if (expandedOrg === orgId) {
      setExpandedOrg(null);
      return;
    }
    setExpandedOrg(orgId);
    if (orgMembers[orgId]) return;
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/platform/orgs/${orgId}/members`, {
        headers: authHeaders(),
      });
      if (!res.ok) return;
      setOrgMembers((prev) => ({ ...prev, [orgId]: await res.json() }));
    } catch {
      // silently ignore
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
    <div className="max-w-4xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Организации</h1>
          <p className="text-sm text-gray-500 mt-1">
            Управление клиентскими организациями (только для платформенного администратора)
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="w-4 h-4 mr-1" />
          Создать
        </Button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {showCreate && (
        <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-xl">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Новая организация</h2>
          <form onSubmit={handleCreate} className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Название организации</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="ООО «Пример»"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Email первого владельца</label>
              <input
                type="email"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="owner@company.com"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Пароль владельца <span className="text-gray-400">(необязательно)</span>
              </label>
              <input
                type="password"
                value={ownerPassword}
                onChange={(e) => setOwnerPassword(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Минимум 8 символов"
              />
            </div>
            {createError && <p className="text-xs text-red-600">{createError}</p>}
            <div className="flex gap-2">
              <Button type="submit" disabled={creating}>
                {creating ? "Создание..." : "Создать"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowCreate(false)}
              >
                Отмена
              </Button>
            </div>
          </form>
        </div>
      )}

      <div className="space-y-3">
        {orgs.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">
            Нет организаций. Создайте первую.
          </div>
        )}
        {orgs.map((org) => (
          <div
            key={org.id}
            className="bg-white border border-gray-200 rounded-xl overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <Building2 className={`w-5 h-5 ${org.is_active ? "text-blue-500" : "text-gray-300"}`} />
                <div>
                  <p className="text-sm font-medium text-gray-900">{org.name}</p>
                  <p className="text-xs text-gray-400">
                    /{org.slug} · создана {new Date(org.created_at).toLocaleDateString("ru-RU")}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => loadMembers(org.id)}
                  className="text-gray-400 hover:text-blue-500 transition-colors text-xs flex items-center gap-1"
                >
                  <Users className="w-4 h-4" />
                  Участники
                </button>
                <button
                  onClick={() => toggleActive(org)}
                  className={`transition-colors ${org.is_active ? "text-green-500 hover:text-gray-400" : "text-gray-300 hover:text-green-500"}`}
                  title={org.is_active ? "Деактивировать" : "Активировать"}
                >
                  {org.is_active ? (
                    <ToggleRight className="w-6 h-6" />
                  ) : (
                    <ToggleLeft className="w-6 h-6" />
                  )}
                </button>
              </div>
            </div>

            {expandedOrg === org.id && (
              <div className="border-t border-gray-100 px-4 py-3 bg-gray-50">
                {orgMembers[org.id] ? (
                  orgMembers[org.id].length === 0 ? (
                    <p className="text-xs text-gray-400">Нет участников</p>
                  ) : (
                    <ul className="space-y-1">
                      {orgMembers[org.id].map((m) => (
                        <li key={m.email} className="flex items-center gap-2 text-xs text-gray-600">
                          <span className="font-medium">{m.email}</span>
                          <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-600">
                            {m.role}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )
                ) : (
                  <LoadingSpinner />
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
