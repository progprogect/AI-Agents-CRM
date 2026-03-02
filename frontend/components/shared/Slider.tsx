/** Reusable slider component. */

import React from "react";

interface SliderProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  error?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  showValue?: boolean;
}

export const Slider: React.FC<SliderProps> = ({
  label,
  error,
  value,
  min,
  max,
  step = 1,
  showValue = true,
  className = "",
  onChange,
  ...props
}) => {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        {label && (
          <label className="block text-sm font-medium text-gray-700">
            {label}
          </label>
        )}
        {showValue && (
          <span className="text-sm font-medium text-[#251D1C]">{value}</span>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
        className={`w-full h-2 bg-gray-200 rounded-sm appearance-none cursor-pointer accent-[#251D1C] ${
          error ? "border-red-500" : ""
        } ${className}`}
        style={{
          background: `linear-gradient(to right, #251D1C 0%, #251D1C ${((value - min) / (max - min)) * 100}%, #E5E7EB ${((value - min) / (max - min)) * 100}%, #E5E7EB 100%)`,
        }}
        {...props}
      />
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
};






