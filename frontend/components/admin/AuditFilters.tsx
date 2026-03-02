/** Audit filters component. */

import React from "react";
import { Select } from "@/components/shared/Select";
import { Input } from "@/components/shared/Input";
import { DateRangePicker, DateRange } from "@/components/shared/DateRangePicker";

export interface AuditFiltersState {
  action?: string;
  resourceType?: string;
  dateRange: DateRange;
  search?: string;
}

interface AuditFiltersProps {
  filters: AuditFiltersState;
  onFiltersChange: (filters: AuditFiltersState) => void;
}

export const AuditFilters: React.FC<AuditFiltersProps> = ({
  filters,
  onFiltersChange,
}) => {
  const handleActionChange = (action: string) => {
    onFiltersChange({
      ...filters,
      action: action === "all" ? undefined : action,
    });
  };

  const handleResourceTypeChange = (resourceType: string) => {
    onFiltersChange({
      ...filters,
      resourceType: resourceType === "all" ? undefined : resourceType,
    });
  };

  const handleDateRangeChange = (dateRange: DateRange) => {
    onFiltersChange({
      ...filters,
      dateRange,
    });
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onFiltersChange({
      ...filters,
      search: e.target.value || undefined,
    });
  };

  return (
    <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-4 mb-6">
      <h2 className="text-sm font-medium text-gray-700 mb-4">Filters</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Select
          label="Action"
          value={filters.action || "all"}
          onChange={(e) => handleActionChange(e.target.value)}
          options={[
            { value: "all", label: "All Actions" },
            { value: "handoff", label: "Handoff to Human" },
            { value: "return_to_ai", label: "Return to AI" },
            { value: "send_message", label: "Send Message" },
            { value: "update_marketing_status", label: "Update Marketing Status" },
            { value: "create_conversation", label: "Create Conversation" },
            { value: "update_conversation", label: "Update Conversation" },
          ]}
        />
        <Select
          label="Resource Type"
          value={filters.resourceType || "all"}
          onChange={(e) => handleResourceTypeChange(e.target.value)}
          options={[
            { value: "all", label: "All Types" },
            { value: "conversation", label: "Conversation" },
            { value: "agent", label: "Agent" },
          ]}
        />
        <DateRangePicker
          value={filters.dateRange}
          onChange={handleDateRangeChange}
        />
        <Input
          label="Search"
          placeholder="Resource ID or Admin ID"
          value={filters.search || ""}
          onChange={handleSearchChange}
        />
      </div>
    </div>
  );
};
