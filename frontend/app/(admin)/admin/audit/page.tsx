/** Audit logs page with filters, pagination, grouping, and CSV export. */

"use client";

import React, { useEffect, useState, useMemo } from "react";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { AuditFilters, AuditFiltersState } from "@/components/admin/AuditFilters";
import { AuditLogRow, AuditLog } from "@/components/admin/AuditLogRow";
import { Button } from "@/components/shared/Button";
import { formatDate } from "@/lib/utils/timeFormat";

const LOGS_PER_PAGE = 50;

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<AuditFiltersState>({
    dateRange: {
      start: new Date(new Date().setHours(0, 0, 0, 0)).toISOString(),
      end: new Date().toISOString(),
    },
  });
  const [displayedCount, setDisplayedCount] = useState(LOGS_PER_PAGE);

  useEffect(() => {
    loadLogs();
  }, [filters]);

  const loadLogs = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const params: {
        action?: string;
        resource_type?: string;
        start_date?: string;
        end_date?: string;
        sort?: string;
        limit?: number;
        admin_id?: string;
      } = {
        sort: "desc",
        limit: 1000, // Get more logs for filtering/search
      };

      if (filters.action) {
        params.action = filters.action;
      }
      if (filters.resourceType) {
        params.resource_type = filters.resourceType;
      }
      if (filters.dateRange.start) {
        params.start_date = filters.dateRange.start;
      }
      if (filters.dateRange.end) {
        params.end_date = filters.dateRange.end;
      }

      const logsData = await api.getAuditLogs(params);

      // Apply search filter client-side
      let filteredLogs = logsData;
      if (filters.search) {
        const searchLower = filters.search.toLowerCase();
        filteredLogs = logsData.filter(
          (log) =>
            log.resource_id.toLowerCase().includes(searchLower) ||
            log.admin_id.toLowerCase().includes(searchLower)
        );
      }

      setLogs(filteredLogs);
      setDisplayedCount(LOGS_PER_PAGE);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load audit logs");
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Group logs by day
  const groupedLogs = useMemo(() => {
    const groups: Record<string, { logs: AuditLog[]; timestamp: number }> = {};
    logs.forEach((log) => {
      const date = new Date(log.timestamp);
      const dayKey = formatDate(date);
      // Use start of day timestamp for consistent sorting
      const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
      if (!groups[dayKey]) {
        groups[dayKey] = { logs: [], timestamp: dayStart };
      }
      groups[dayKey].logs.push(log);
    });
    return groups;
  }, [logs]);

  const sortedGroupKeys = useMemo(() => {
    return Object.keys(groupedLogs).sort((a, b) => {
      return groupedLogs[b].timestamp - groupedLogs[a].timestamp;
    });
  }, [groupedLogs]);

  const displayedLogs = useMemo(() => {
    let count = 0;
    const result: { day: string; logs: AuditLog[] }[] = [];
    for (const dayKey of sortedGroupKeys) {
      if (count >= displayedCount) break;
      const dayLogs = groupedLogs[dayKey].logs;
      const remaining = displayedCount - count;
      if (count + dayLogs.length <= displayedCount) {
        result.push({ day: dayKey, logs: dayLogs });
        count += dayLogs.length;
      } else {
        result.push({ day: dayKey, logs: dayLogs.slice(0, remaining) });
        count += remaining;
      }
    }
    return result;
  }, [groupedLogs, sortedGroupKeys, displayedCount]);

  const hasMore = displayedCount < logs.length;

  const handleLoadMore = () => {
    setDisplayedCount((prev) => prev + LOGS_PER_PAGE);
  };


  const exportToCSV = () => {
    const headers = ["Timestamp", "Admin ID", "Action", "Resource Type", "Resource ID", "Metadata"];
    const rows = logs.map((log) => {
      const metadata = log.metadata ? JSON.stringify(log.metadata) : "";
      return [
        log.timestamp,
        log.admin_id,
        log.action,
        log.resource_type,
        log.resource_id,
        metadata,
      ];
    });

    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `audit_logs_${new Date().toISOString().split("T")[0]}.csv`);
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
        <Button onClick={exportToCSV} variant="secondary">
          Export CSV
        </Button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <AuditFilters filters={filters} onFiltersChange={setFilters} />

      {logs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600">No audit logs found</p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-[#EEEAE7]/10">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Action
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Admin
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Resource Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Resource ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Details
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {displayedLogs.map((group) => (
                  <React.Fragment key={group.day}>
                    <tr className="bg-gray-50">
                      <td colSpan={6} className="px-6 py-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                          <span>{group.day}</span>
                          <span className="text-xs text-gray-500">
                            ({group.logs.length} {group.logs.length === 1 ? "log" : "logs"})
                          </span>
                        </div>
                      </td>
                    </tr>
                    {group.logs.map((log) => (
                      <AuditLogRow key={log.log_id} log={log} />
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {hasMore && (
            <div className="mt-4 text-center">
              <Button onClick={handleLoadMore} variant="secondary">
                Load More ({logs.length - displayedCount} remaining)
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
