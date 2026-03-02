/** Reusable button component with icon support. */

import React from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  icon?: React.ReactNode;
  iconPosition?: "left" | "right";
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled,
  className = "",
  icon,
  iconPosition = "left",
  ...props
}) => {
  const baseStyles =
    "inline-flex items-center justify-center font-medium rounded-sm transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed";

  const variantStyles = {
    primary:
      "bg-[#251D1C] text-white hover:bg-[#443C3C] focus:ring-[#251D1C] shadow-sm hover:shadow-md",
    secondary:
      "bg-white text-gray-900 border border-[#251D1C] hover:bg-[#EEEAE7] hover:border-[#443C3C] focus:ring-[#251D1C]",
    danger:
      "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 shadow-sm hover:shadow-md",
    ghost:
      "bg-transparent text-[#251D1C] hover:bg-[#EEEAE7] focus:ring-[#251D1C]",
  };

  const sizeStyles = {
    sm: "px-3 py-1.5 text-sm gap-1.5",
    md: "px-4 py-2 text-base gap-2",
    lg: "px-6 py-3 text-lg gap-2.5",
  };

  const iconSizeClasses = {
    sm: "h-3.5 w-3.5",
    md: "h-4 w-4",
    lg: "h-5 w-5",
  };

  const renderContent = () => {
    if (isLoading) {
      return (
        <>
          <svg
            className={`animate-spin ${iconSizeClasses[size]}`}
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
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
          <span>Loading...</span>
        </>
      );
    }

    if (!icon) {
      return children;
    }

    const iconElement = (
      <span className={`flex-shrink-0 ${iconSizeClasses[size]}`} aria-hidden="true">
        {icon}
      </span>
    );

    if (iconPosition === "right") {
      return (
        <>
          {children}
          {iconElement}
        </>
      );
    }

    return (
      <>
        {iconElement}
        {children}
      </>
    );
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      {...props}
    >
      {renderContent()}
    </button>
  );
};



