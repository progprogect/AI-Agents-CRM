/** Admin layout component with auth guard. */

"use client";

import React, { useEffect, useState } from "react";
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
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto p-6 bg-white">{children}</main>
      </div>
    </div>
  );
}
