/** Loading spinner component. */

import React from "react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  className = "",
}) => {
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-8 w-8",
    lg: "h-12 w-12",
  };

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <svg
        className={`animate-spin ${sizeClasses[size]} text-[#251D1C]`}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12c0-1.357.538-2.586 1.414-3.462L6 8.586A7.962 7.962 0 0112 4c1.357 0 2.586.538 3.462 1.414L17.414 6A7.962 7.962 0 0120 12c0 1.357-.538 2.586-1.414 3.462L17.414 17A7.962 7.962 0 0112 20c-1.357 0-2.586-.538-3.462-1.414L6 17.414z"
        />
      </svg>
    </div>
  );
};



