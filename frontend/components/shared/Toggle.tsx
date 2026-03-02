/** Reusable toggle/switch component. */

import React from "react";

interface ToggleProps {
  label?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  error?: string;
  description?: string;
}

export const Toggle: React.FC<ToggleProps> = ({
  label,
  checked,
  onChange,
  disabled = false,
  error,
  description,
}) => {
  return (
    <div className="w-full">
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={disabled}
          onClick={() => !disabled && onChange(!checked)}
          className={`relative inline-flex h-6 w-11 items-center rounded-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:ring-offset-2 ${
            checked ? "bg-[#251D1C]" : "bg-gray-300"
          } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-sm bg-white transition-transform duration-200 ${
              checked ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <div className="flex-1">
          {label && (
            <label className="block text-sm font-medium text-gray-700">
              {label}
            </label>
          )}
          {description && (
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          )}
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    </div>
  );
};






