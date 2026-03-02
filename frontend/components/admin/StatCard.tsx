/** Stat card component with change indicator. */

import React from "react";
import { formatChange } from "@/lib/utils/statsHelpers";

interface StatCardProps {
  label: string;
  value: number;
  change?: number;
  icon?: string;
  colorClass?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  change,
  icon,
  colorClass = "bg-[#EEEAE7]/10 text-[#443C3C] border-[#251D1C]/30",
}) => {
  const changeDisplay = change !== undefined ? formatChange(change) : null;

  return (
    <div
      className={`p-6 rounded-sm border border-[#251D1C]/20 bg-white shadow-sm hover:shadow-md transition-all duration-200 ${colorClass}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium mb-2">{label}</p>
          <p className="text-3xl font-bold">{value.toLocaleString()}</p>
          {changeDisplay && (
            <p className={`text-xs font-medium mt-2 ${changeDisplay.colorClass}`}>
              {changeDisplay.text}
            </p>
          )}
        </div>
        {icon && (
          <div className="text-2xl opacity-50" aria-hidden="true">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
};
