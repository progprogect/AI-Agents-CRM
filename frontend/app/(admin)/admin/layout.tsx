/** Admin layout component with auth guard and responsive sidebar. */

"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "@/components/admin/Sidebar";
import { Header } from "@/components/admin/Header";
import { isAuthenticated } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    // Skip auth check for the login page itself
    if (pathname === "/admin/login") {
      setChecked(true);
      return;
    }

    if (!isAuthenticated()) {
      router.replace("/admin/login");
    } else {
      setChecked(true);
    }
  }, [pathname, router]);

  // Close sidebar on route change (mobile navigation)
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  const handleToggle = useCallback(() => setSidebarOpen((o) => !o), []);
  const handleClose = useCallback(() => setSidebarOpen(false), []);

  // Show nothing until auth check completes (avoids flash of admin content)
  if (!checked) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#EEEAE7]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  // Login page has its own full-page layout — don't wrap with sidebar/header
  if (pathname === "/admin/login") {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen bg-[#FAFAFA] overflow-hidden">
      {/* Mobile backdrop — closes sidebar when tapping outside */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden"
          onClick={handleClose}
          aria-hidden="true"
        />
      )}

      <Sidebar isOpen={sidebarOpen} onClose={handleClose} />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header onSidebarToggle={handleToggle} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6 bg-white">
          {children}
        </main>
      </div>
    </div>
  );
}
