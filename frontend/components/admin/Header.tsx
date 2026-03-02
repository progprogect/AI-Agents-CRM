/** Header component for admin panel. */

"use client";

import React from "react";

export const Header: React.FC = () => {
  return (
    <header className="bg-white border-b border-[#251D1C]/20 px-6 py-4" role="banner">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Admin Dashboard</h2>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600" aria-label="Current user">Admin User</span>
          <button
            className="text-sm text-[#251D1C] hover:text-[#443C3C] transition-colors duration-200"
            aria-label="Logout from admin panel"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
};



