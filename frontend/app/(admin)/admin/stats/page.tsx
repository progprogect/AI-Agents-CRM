/** Statistics page with marketing metrics, change indicators, chart, and period filter. */

"use client";

import { useEffect, useState, useCallback } from "react";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { StatCardGroup } from "@/components/admin/StatCardGroup";
import { PeriodComparison } from "@/components/admin/PeriodComparison";
import { Select } from "@/components/shared/Select";
import type { Stats, Period } from "@/lib/types/stats";

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("today");
  const [includeComparison, setIncludeComparison] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      setIsLoading(true);
      const statsData = await api.getStats({
        period,
        include_comparison: includeComparison,
      });
      setStats(statsData);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load statistics");
      }
    } finally {
      setIsLoading(false);
    }
  }, [period, includeComparison]);

  useEffect(() => {
    loadStats();
    // Refresh every 10 seconds
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, [loadStats]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="bg-red-50 border-l-4 border-red-500 p-4">
        <p className="text-sm text-red-700">{error || "Failed to load statistics"}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Statistics</h1>
        <div className="w-48">
          <Select
            value={period}
            onChange={(e) => setPeriod(e.target.value as Period)}
            options={[
              { value: "today", label: "Today" },
              { value: "last_7_days", label: "Last 7 days" },
              { value: "last_30_days", label: "Last 30 days" },
            ]}
          />
        </div>
      </div>

      {includeComparison && stats.comparison && (
        <PeriodComparison
          comparison={stats.comparison}
          currentStats={{
            total_conversations: stats.total_conversations,
            ai_active: stats.ai_active,
            needs_human: stats.needs_human,
            human_active: stats.human_active,
            closed: stats.closed,
            marketing_new: stats.marketing_new,
            marketing_booked: stats.marketing_booked,
            marketing_no_response: stats.marketing_no_response,
            marketing_rejected: stats.marketing_rejected,
          }}
          enabled={includeComparison}
          onToggle={setIncludeComparison}
        />
      )}

      {!includeComparison && (
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="comparison-toggle"
              checked={includeComparison}
              onChange={(e) => setIncludeComparison(e.target.checked)}
              className="h-4 w-4 text-[#251D1C] focus:ring-[#251D1C] border-gray-300 rounded"
            />
            <label htmlFor="comparison-toggle" className="text-sm font-medium text-gray-700">
              Show comparison with previous period
            </label>
          </div>
        </div>
      )}

      <StatCardGroup
        title="Overview"
        cards={[
          {
            label: "Total Conversations",
            value: stats.total_conversations,
            change: stats.comparison?.total_conversations,
            icon: "💬",
            colorClass: "bg-[#EEEAE7]/10 text-[#443C3C] border-[#251D1C]/30",
          },
        ]}
        columns={1}
      />

      <StatCardGroup
        title="Technical Statuses"
        cards={[
          {
            label: "AI Active",
            value: stats.ai_active,
            change: stats.comparison?.ai_active,
            icon: "🤖",
            colorClass: "bg-[#EEEAE7]/20 text-[#443C3C] border-[#251D1C]/40",
          },
          {
            label: "Needs Human",
            value: stats.needs_human,
            change: stats.comparison?.needs_human,
            icon: "👤",
            colorClass: "bg-[#F59E0B]/10 text-[#D97706] border-[#F59E0B]/30",
          },
          {
            label: "Human Active",
            value: stats.human_active,
            change: stats.comparison?.human_active,
            icon: "✋",
            colorClass: "bg-[#3B82F6]/10 text-[#2563EB] border-[#3B82F6]/30",
          },
          {
            label: "Closed",
            value: stats.closed,
            change: stats.comparison?.closed,
            icon: "✅",
            colorClass: "bg-gray-50 text-gray-700 border-gray-200",
          },
        ]}
        columns={4}
      />

      <StatCardGroup
        title="Marketing Statuses"
        cards={[
          {
            label: "New",
            value: stats.marketing_new,
            change: stats.comparison?.marketing_new,
            icon: "✨",
            colorClass: "bg-blue-100 text-blue-800 border border-blue-200",
          },
          {
            label: "Booked",
            value: stats.marketing_booked,
            change: stats.comparison?.marketing_booked,
            icon: "✅",
            colorClass: "bg-green-100 text-green-800 border border-green-200",
          },
          {
            label: "No Response",
            value: stats.marketing_no_response,
            change: stats.comparison?.marketing_no_response,
            icon: "⏳",
            colorClass: "bg-gray-100 text-gray-800 border border-gray-200",
          },
          {
            label: "Rejected",
            value: stats.marketing_rejected,
            change: stats.comparison?.marketing_rejected,
            icon: "❌",
            colorClass: "bg-red-100 text-red-800 border border-red-200",
          },
        ]}
        columns={4}
      />
    </div>
  );
}
