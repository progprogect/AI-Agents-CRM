/** Sidebar navigation component — responsive drawer on mobile, static on desktop. */

"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAdminWebSocket } from "@/lib/hooks/useAdminWebSocket";
import { api } from "@/lib/api";
import { isSuperAdmin } from "@/lib/auth";

import {
  Bot,
  MessageSquare,
  Bell,
  ClipboardList,
  BarChart3,
  FlaskConical,
  Users,
  Kanban,
  MessageCircle,
  X,
} from "lucide-react";

const baseNavigation = [
  { name: "Agents", href: "/admin/agents", icon: <Bot size={20} /> },
  { name: "Conversations", href: "/admin/conversations", icon: <MessageSquare size={20} /> },
  { name: "CRM", href: "/admin/crm", icon: <Kanban size={20} /> },
  { name: "Notifications", href: "/admin/notifications", icon: <Bell size={20} /> },
  { name: "Audit", href: "/admin/audit", icon: <ClipboardList size={20} /> },
  { name: "Statistics", href: "/admin/stats", icon: <BarChart3 size={20} /> },
  { name: "Instagram Test", href: "/admin/instagram-test", icon: <FlaskConical size={20} /> },
  { name: "WhatsApp Test", href: "/admin/whatsapp-test", icon: <MessageCircle size={20} /> },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const pathname = usePathname();
  const [needsHumanCount, setNeedsHumanCount] = useState(0);
  const { onStatsUpdate, onNewEscalation } = useAdminWebSocket();

  // Build navigation dynamically — super admin gets Users link
  const navigation = [
    ...baseNavigation,
    ...(isSuperAdmin()
      ? [{ name: "Users", href: "/admin/users", icon: <Users size={20} /> }]
      : []),
  ];

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
    <aside
      className={[
        // Base styles (mobile-first: fixed drawer)
        "fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-[#BEBAB7]",
        "flex flex-col flex-shrink-0",
        // Slide animation
        "transition-transform duration-300 ease-in-out",
        isOpen ? "translate-x-0" : "-translate-x-full",
        // Desktop: always visible, part of normal flow
        "md:static md:translate-x-0 md:z-auto",
      ].join(" ")}
      aria-label="Admin navigation"
    >
      {/* Logo row — contains close button on mobile */}
      <div className="relative flex items-center h-[72px] px-6 border-b border-[#BEBAB7] flex-shrink-0">
        <Image
          src="/logo.svg"
          alt="CAworks"
          width={120}
          height={32}
          className="h-8 w-auto"
          priority
        />
        {/* Close button — mobile only */}
        <button
          onClick={onClose}
          className="absolute right-4 top-1/2 -translate-y-1/2 md:hidden p-1.5 rounded-sm text-gray-400 hover:text-gray-600 hover:bg-[#EEEAE7] transition-colors"
          aria-label="Close navigation menu"
        >
          <X size={20} />
        </button>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          const isConversations = item.href === "/admin/conversations";
          const showBadge = isConversations && needsHumanCount > 0;

          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={`group flex items-center justify-between gap-3 px-4 py-3 md:py-2 rounded-sm transition-all duration-200 ${
                isActive
                  ? "bg-[#EEEAE7] text-[#443C3C] font-medium border-l-2 border-[#251D1C]"
                  : "text-gray-700 hover:bg-[#EEEAE7]/50 hover:text-[#251D1C]"
              }`}
              aria-current={isActive ? "page" : undefined}
              aria-label={`Navigate to ${item.name}${showBadge ? ` (${needsHumanCount} require attention)` : ""}`}
            >
              <div className="flex items-center gap-3">
                <span
                  className={`flex items-center justify-center transition-colors duration-200 group-hover:text-[#251D1C] ${isActive ? "text-[#251D1C]" : "text-gray-500"}`}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
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
