/** Admin login page — Email + OTP two-step authentication. */

"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { isAuthenticated, setAdminToken } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

// In production (non-localhost) the browser uses relative URLs so nginx routes /api/* to backend.
// In local dev, fall back to localhost:8000.
const getApiUrl = (): string => {
  if (typeof window !== "undefined") {
    const host = window.location.host;
    if (!host.startsWith("localhost")) return "";
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
};

type Step = "email" | "otp";

export default function LoginPage() {
  const router = useRouter();
  const t = useTranslations("Login");

  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  const otpInputRef = useRef<HTMLInputElement>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated()) {
      router.replace("/admin/agents");
    }
  }, [router]);

  // Resend countdown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  // Auto-focus OTP input when step changes
  useEffect(() => {
    if (step === "otp") {
      setTimeout(() => otpInputRef.current?.focus(), 100);
    }
  }, [step]);

  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${getApiUrl()}/api/v1/admin/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });

      if (res.status === 429) {
        setError(t("tooManyRequests"));
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail ?? t("somethingWentWrong"));
        return;
      }

      setStep("otp");
      setResendCooldown(60);
    } catch {
      setError(t("unableToConnect"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.trim().length !== 6) {
      setError(t("enter6DigitCode"));
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${getApiUrl()}/api/v1/admin/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), code: code.trim() }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(data?.detail ?? t("invalidOrExpiredCode"));
        setCode("");
        return;
      }

      setAdminToken(data.access_token);
      router.replace("/admin/agents");
    } catch {
      setError(t("unableToConnect"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setCode("");
    setError(null);
    setResendCooldown(60);
    setIsLoading(true);

    try {
      await fetch(`${getApiUrl()}/api/v1/admin/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
    } catch {
      // Silently ignore — user will see the cooldown
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#EEEAE7] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <Image src="/logo.svg" alt="CAworks" width={140} height={38} priority />
        </div>

        <div className="bg-white rounded-sm shadow-sm border border-[#BEBAB7] p-8">
          {step === "email" ? (
            <>
              <h1 className="text-xl font-semibold text-gray-900 mb-1">{t("title")}</h1>
              <p className="text-sm text-gray-500 mb-6">
                {t("subtitle")}
              </p>

              <form onSubmit={handleRequestOTP} noValidate>
                <div className="mb-4">
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    {t("emailLabel")}
                  </label>
                  <input
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t("emailPlaceholder")}
                    className="w-full px-3 py-2 border border-gray-300 rounded-sm bg-white text-sm focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C] transition-colors"
                    disabled={isLoading}
                  />
                </div>

                {error && (
                  <p className="text-sm text-red-600 mb-4">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={isLoading || !email.trim()}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#251D1C] text-white text-sm font-medium rounded-sm hover:bg-[#443C3C] disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                >
                  {isLoading ? <LoadingSpinner size="sm" /> : null}
                  {t("sendCode")}
                </button>
              </form>
            </>
          ) : (
            <>
              <h1 className="text-xl font-semibold text-gray-900 mb-1">{t("checkEmail")}</h1>
              <p className="text-sm text-gray-500 mb-1">
                {t("codeSentTo")}
              </p>
              <p className="text-sm font-medium text-gray-900 mb-6 truncate">{email}</p>

              <form onSubmit={handleVerifyOTP} noValidate>
                <div className="mb-4">
                  <label
                    htmlFor="code"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    {t("loginCodeLabel")}
                  </label>
                  <input
                    id="code"
                    ref={otpInputRef}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    autoComplete="one-time-code"
                    maxLength={6}
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                    placeholder={t("codePlaceholder")}
                    className="w-full px-3 py-2 border border-gray-300 rounded-sm bg-white text-sm text-center tracking-[0.4em] font-mono focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C] transition-colors"
                    disabled={isLoading}
                  />
                </div>

                {error && (
                  <p className="text-sm text-red-600 mb-4">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={isLoading || code.length !== 6}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#251D1C] text-white text-sm font-medium rounded-sm hover:bg-[#443C3C] disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                >
                  {isLoading ? <LoadingSpinner size="sm" /> : null}
                  {t("verify")}
                </button>
              </form>

              <div className="mt-4 flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={() => { setStep("email"); setError(null); setCode(""); }}
                  className="text-gray-500 hover:text-gray-700 transition-colors"
                >
                  {t("changeEmail")}
                </button>
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendCooldown > 0 || isLoading}
                  className="text-[#251D1C] hover:text-[#443C3C] disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                  {resendCooldown > 0 ? t("resendIn", { seconds: resendCooldown }) : t("resendCode")}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
