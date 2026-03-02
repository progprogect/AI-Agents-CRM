/** User avatar component with fallback to initials or default icon. */

import React, { useState } from "react";

interface UserAvatarProps {
  src?: string | null;
  name?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const getInitials = (name: string | null | undefined): string => {
  if (!name || name.trim().length === 0) {
    return "?";
  }

  const words = name.trim().split(/\s+/);
  if (words.length === 0) {
    return "?";
  }

  if (words.length === 1) {
    return words[0].charAt(0).toUpperCase();
  }

  // Take first letter of first two words
  return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
};

const sizeClasses = {
  sm: "w-8 h-8 text-xs",
  md: "w-10 h-10 text-sm",
  lg: "w-12 h-12 text-base",
};

export const UserAvatar: React.FC<UserAvatarProps> = ({
  src,
  name,
  size = "md",
  className = "",
}) => {
  const [imageError, setImageError] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);

  const handleImageError = () => {
    setImageError(true);
    setImageLoaded(false);
  };

  const handleImageLoad = () => {
    setImageLoaded(true);
    setImageError(false);
  };

  const initials = getInitials(name);
  const showImage = src && !imageError;
  const showInitials = !showImage && name;

  return (
    <div
      className={`flex-shrink-0 rounded-full flex items-center justify-center font-medium bg-[#EEEAE7] text-[#443C3C] ${sizeClasses[size]} relative ${className}`}
      role="img"
      aria-label={name ? `Avatar for ${name}` : "User avatar"}
    >
      {showImage ? (
        <>
          {!imageLoaded && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#EEEAE7] text-[#443C3C] rounded-full">
              {initials}
            </div>
          )}
          <img
            src={src}
            alt={name || "User avatar"}
            className={`rounded-full ${sizeClasses[size]} object-cover ${
              imageLoaded ? "opacity-100" : "opacity-0"
            } transition-opacity duration-200`}
            onError={handleImageError}
            onLoad={handleImageLoad}
          />
        </>
      ) : showInitials ? (
        <span>{initials}</span>
      ) : (
        <span className="text-lg" aria-hidden="true">
          👤
        </span>
      )}
    </div>
  );
};
