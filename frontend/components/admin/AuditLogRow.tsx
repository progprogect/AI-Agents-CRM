/** Audit log row component with expandable details. */

import React, { useState } from "react";
import Link from "next/link";
import { getActionDisplay, getResourceTypeLabel } from "@/lib/utils/auditDisplay";
import { formatRelativeTimeDetailed, formatDateTime } from "@/lib/utils/timeFormat";

export interface AuditLog {
  log_id: string;
  admin_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface AuditLogRowProps {
  log: AuditLog;
}

export const AuditLogRow: React.FC<AuditLogRowProps> = ({ log }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const actionDisplay = getActionDisplay(log.action);
  const hasMetadata = log.metadata && Object.keys(log.metadata).length > 0;

  const getResourceLink = () => {
    if (log.resource_type === "conversation") {
      return `/admin/conversations/${log.resource_id}`;
    }
    return null;
  };

  const resourceLink = getResourceLink();

  return (
    <>
      <tr
        className="hover:bg-[#EEEAE7]/5 transition-colors duration-150 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          <div className="flex items-center gap-2">
            <span className="text-xs">{actionDisplay.icon}</span>
            <span
              className={`px-2 py-1 rounded text-xs font-medium ${actionDisplay.colorClasses}`}
            >
              {actionDisplay.label}
            </span>
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
          {formatRelativeTimeDetailed(log.timestamp)}
          <div className="text-xs text-gray-500 mt-1">
            {formatDateTime(log.timestamp)}
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
          {log.admin_id}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          {getResourceTypeLabel(log.resource_type)}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm">
          {resourceLink ? (
            <Link
              href={resourceLink}
              onClick={(e) => e.stopPropagation()}
              className="text-[#443C3C] hover:text-[#251D1C] hover:underline"
            >
              {log.resource_id.substring(0, 8)}...
            </Link>
          ) : (
            <span className="text-gray-500">
              {log.resource_id.substring(0, 8)}...
            </span>
          )}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
          {hasMetadata && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="text-[#443C3C] hover:text-[#251D1C]"
            >
              {isExpanded ? "▼" : "▶"}
            </button>
          )}
        </td>
      </tr>
      {isExpanded && hasMetadata && (
        <tr>
          <td colSpan={6} className="px-6 py-4 bg-gray-50">
            <div className="text-sm">
              <h4 className="font-medium text-gray-700 mb-2">Metadata</h4>
              <pre className="bg-white p-3 rounded border border-gray-200 overflow-x-auto text-xs">
                {JSON.stringify(log.metadata, null, 2)}
              </pre>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};
