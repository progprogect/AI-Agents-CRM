/** Generic badge component for displaying status indicators. */

import React from "react";

export type BadgeVariant = "default" | "success" | "warning" | "error" | "info";

interface BadgeProps {
  variant?: BadgeVariant;
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-[#EEEAE7] text-[#443C3C] border-[#BEBAB7]",
  success: "bg-green-100 text-green-800 border-green-200",
  warning: "bg-[#F59E0B]/20 text-[#D97706] border-[#F59E0B]/30",
  error: "bg-red-100 text-red-800 border-red-200",
  info: "bg-[#3B82F6]/20 text-[#2563EB] border-[#3B82F6]/30",
};

const sizeClasses = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2 py-1 text-xs",
  lg: "px-3 py-1.5 text-sm",
};

export const Badge: React.FC<BadgeProps> = ({
  variant = "default",
  size = "md",
  children,
  className = "",
}) => {
  return (
    <span
      className={`inline-flex items-center leading-5 font-semibold rounded-sm border ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {children}
    </span>
  );
};
