/** Header component for admin panel. */

"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { removeAdminToken } from "@/lib/auth";

export const Header: React.FC = () => {
  const router = useRouter();

  const handleLogout = () => {
    removeAdminToken();
    router.push("/admin/login");
  };

  return (
    <header className="flex items-center h-[72px] bg-white border-b border-[#BEBAB7] px-6" role="banner">
      <div className="flex flex-1 items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Admin Dashboard</h2>
        <div className="flex items-center gap-4">
          <button
            onClick={handleLogout}
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
