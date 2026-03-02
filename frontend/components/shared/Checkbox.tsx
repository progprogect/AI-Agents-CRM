/** Reusable checkbox component. */

import React from "react";

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  error?: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  checked,
  onChange,
  disabled = false,
  error,
}) => {
  return (
    <div className="flex items-start gap-2">
      <input
        type="checkbox"
        id={`checkbox-${label}`}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className={`mt-1 h-4 w-4 rounded border-gray-300 text-[#251D1C] focus:ring-2 focus:ring-[#251D1C] focus:ring-offset-0 transition-colors duration-200 ${
          error ? "border-red-500" : ""
        } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
      />
      <label
        htmlFor={`checkbox-${label}`}
        className={`text-sm text-gray-700 ${
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
        }`}
      >
        {label}
      </label>
    </div>
  );
};





