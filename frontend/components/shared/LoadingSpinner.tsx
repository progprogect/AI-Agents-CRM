/** Loading spinner — three animated bars (CAworks style). */

import React from "react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  className = "",
}) => {
  const widths = { sm: 18, md: 30, lg: 45 };
  const width = widths[size];

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div
        className="caworks-loader"
        style={{ width }}
        role="status"
        aria-label="Loading"
      />
    </div>
  );
};
