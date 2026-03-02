/** Date range picker component. */

import React, { useState } from "react";
import { Select } from "./Select";

export type DateRangePreset = "today" | "last_7_days" | "last_30_days" | "custom";

export interface DateRange {
  start: string | null;
  end: string | null;
}

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
  className?: string;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({
  value,
  onChange,
  className = "",
}) => {
  const [preset, setPreset] = useState<DateRangePreset>("today");

  const handlePresetChange = (newPreset: DateRangePreset) => {
    setPreset(newPreset);
    const now = new Date();
    let start: Date;
    let end: Date = now;

    if (newPreset === "today") {
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    } else if (newPreset === "last_7_days") {
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    } else if (newPreset === "last_30_days") {
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    } else {
      // Custom - don't change dates
      return;
    }

    onChange({
      start: start.toISOString(),
      end: end.toISOString(),
    });
  };

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPreset("custom");
    onChange({
      ...value,
      start: e.target.value ? new Date(e.target.value).toISOString() : null,
    });
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPreset("custom");
    onChange({
      ...value,
      end: e.target.value ? new Date(e.target.value).toISOString() : null,
    });
  };

  const formatDateForInput = (isoString: string | null): string => {
    if (!isoString) return "";
    const date = new Date(isoString);
    return date.toISOString().split("T")[0];
  };

  return (
    <div className={`space-y-2 ${className}`}>
      <Select
        label="Date Range"
        value={preset}
        onChange={(e) => handlePresetChange(e.target.value as DateRangePreset)}
        options={[
          { value: "today", label: "Today" },
          { value: "last_7_days", label: "Last 7 days" },
          { value: "last_30_days", label: "Last 30 days" },
          { value: "custom", label: "Custom range" },
        ]}
      />
      {preset === "custom" && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Start Date
            </label>
            <input
              type="date"
              value={formatDateForInput(value.start)}
              onChange={handleStartDateChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              End Date
            </label>
            <input
              type="date"
              value={formatDateForInput(value.end)}
              onChange={handleEndDateChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C]"
            />
          </div>
        </div>
      )}
    </div>
  );
};
