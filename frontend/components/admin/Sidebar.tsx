/** Sidebar navigation component. */

"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAdminWebSocket } from "@/lib/hooks/useAdminWebSocket";
import { api } from "@/lib/api";

const navigation = [
  { name: "Agents", href: "/admin/agents", icon: "🤖" },
  { name: "Conversations", href: "/admin/conversations", icon: "💬" },
  { name: "Notifications", href: "/admin/notifications", icon: "🔔" },
  { name: "Audit", href: "/admin/audit", icon: "📋" },
  { name: "Stats", href: "/admin/stats", icon: "📊" },
  { name: "Instagram Test", href: "/admin/instagram-test", icon: "🧪" },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const [needsHumanCount, setNeedsHumanCount] = useState(0);
  const { onStatsUpdate, onNewEscalation } = useAdminWebSocket();

  // Load initial stats
  useEffect(() => {
    const loadStats = async () => {
      try {
        const stats = await api.getStats();
        setNeedsHumanCount(stats.needs_human || 0);
      } catch (err) {
        console.error("Failed to load stats:", err);
      }
    };
    loadStats();
  }, []);

  // Listen for stats updates
  useEffect(() => {
    const unsubscribeStats = onStatsUpdate((stats) => {
      if (stats.needs_human !== undefined) {
        setNeedsHumanCount(stats.needs_human);
      }
    });

    const unsubscribeEscalation = onNewEscalation(() => {
      // Reload stats when new escalation occurs
      api.getStats()
        .then((stats) => {
          setNeedsHumanCount(stats.needs_human || 0);
        })
        .catch((err) => {
          console.error("Failed to reload stats:", err);
        });
    });

    return () => {
      unsubscribeStats();
      unsubscribeEscalation();
    };
  }, [onStatsUpdate, onNewEscalation]);

  return (
    <aside className="w-64 bg-white border-r border-[#D4AF37]/20 flex flex-col flex-shrink-0" aria-label="Admin navigation">
      <div className="p-6 border-b border-[#D4AF37]/20">
        <h1 className="text-xl font-bold text-[#D4AF37]">Agent</h1>
        <p className="text-sm text-gray-600">Admin Panel</p>
      </div>
      <nav className="flex-1 p-4 space-y-2" aria-label="Main navigation">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          const isConversations = item.href === "/admin/conversations";
          const showBadge = isConversations && needsHumanCount > 0;

          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center justify-between gap-3 px-4 py-2 rounded-sm transition-all duration-200 ${
                isActive
                  ? "bg-[#F5D76E]/20 text-[#B8860B] font-medium border-l-2 border-[#D4AF37]"
                  : "text-gray-700 hover:bg-[#F5D76E]/10 hover:text-[#D4AF37]"
              }`}
              aria-current={isActive ? "page" : undefined}
              aria-label={`Navigate to ${item.name}${showBadge ? ` (${needsHumanCount} require attention)` : ""}`}
            >
              <div className="flex items-center gap-3">
                <span className="text-xl" aria-hidden="true">{item.icon}</span>
                <span>{item.name}</span>
              </div>
              {showBadge && (
                <span
                  className="bg-[#F59E0B] text-white text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center"
                  aria-label={`${needsHumanCount} conversation${needsHumanCount !== 1 ? "s" : ""} require${needsHumanCount === 1 ? "s" : ""} attention`}
                >
                  {needsHumanCount > 99 ? "99+" : needsHumanCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
};



