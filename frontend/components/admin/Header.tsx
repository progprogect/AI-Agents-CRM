/** Header component for admin panel. */

"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Menu } from "lucide-react";
import { removeAdminToken, getCurrentUserEmail } from "@/lib/auth";

interface HeaderProps {
  onSidebarToggle: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onSidebarToggle }) => {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setEmail(getCurrentUserEmail());
  }, []);

  const handleLogout = () => {
    removeAdminToken();
    router.push("/admin/login");
  };

  return (
    <header className="flex items-center h-[72px] bg-white border-b border-[#BEBAB7] px-4 md:px-6" role="banner">
      <div className="flex flex-1 items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Hamburger — mobile only */}
          <button
            onClick={onSidebarToggle}
            className="md:hidden p-2 -ml-1 rounded-sm hover:bg-[#EEEAE7] text-[#251D1C] transition-colors"
            aria-label="Toggle navigation menu"
          >
            <Menu size={20} />
          </button>
          <h2 className="text-lg font-semibold text-gray-900">Admin Dashboard</h2>
        </div>

        <div className="flex items-center gap-3 md:gap-4">
          {email && (
            <span
              className="text-sm text-gray-500 hidden sm:block truncate max-w-[160px] md:max-w-[200px]"
              title={email}
            >
              {email}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="text-sm text-[#251D1C] px-3 py-1.5 rounded-sm border border-[#BEBAB7] hover:bg-[#EEEAE7] hover:border-[#251D1C] active:bg-[#D0CBC8] transition-all duration-150 cursor-pointer whitespace-nowrap"
            aria-label="Logout from admin panel"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
};
