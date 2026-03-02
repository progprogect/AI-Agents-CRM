/** Reusable textarea component. */

import React from "react";

interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  helperText,
  className = "",
  ...props
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
        </label>
      )}
      <textarea
        className={`w-full px-3 py-2 border rounded-sm bg-white transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C] ${
          error ? "border-red-500 focus:ring-red-500" : "border-gray-300"
        } ${className}`}
        {...props}
      />
      {helperText && !error && (
        <p className="mt-1 text-xs text-gray-500">{helperText}</p>
      )}
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
};


