/** Language switcher — toggles between EN and RU, persists locale in cookie. */

"use client";

import React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { Globe } from "lucide-react";
import type { Locale } from "@/i18n/request";

const COOKIE_NAME = "NEXT_LOCALE";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

function setLocaleCookie(locale: Locale) {
  document.cookie = `${COOKIE_NAME}=${locale};path=/;max-age=${COOKIE_MAX_AGE};SameSite=Lax`;
}

export function LanguageSwitcher() {
  const locale = useLocale() as Locale;
  const t = useTranslations("Locale");
  const router = useRouter();

  const nextLocale: Locale = locale === "en" ? "ru" : "en";
  const nextLabel = locale === "en" ? t("ru") : t("en");

  const handleSwitch = () => {
    setLocaleCookie(nextLocale);
    router.refresh();
  };

  return (
    <button
      type="button"
      onClick={handleSwitch}
      className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-[#443C3C] px-2 sm:px-3 py-1.5 rounded-sm border border-[#BEBAB7] hover:bg-[#EEEAE7] hover:border-[#251D1C] transition-colors"
      aria-label={t("switchTo", { lang: nextLabel })}
      title={t("switchTo", { lang: nextLabel })}
    >
      <Globe size={14} className="sm:w-4 sm:h-4 shrink-0" aria-hidden />
      <span className="font-medium">{locale.toUpperCase()}</span>
      <span className="text-[#9A9590] text-xs hidden sm:inline">→</span>
      <span className="text-xs">{nextLabel}</span>
    </button>
  );
}
