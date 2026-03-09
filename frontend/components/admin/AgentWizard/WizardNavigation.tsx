/** Wizard navigation buttons component. */

"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/shared/Button";

interface WizardNavigationProps {
  currentStep: number;
  totalSteps: number;
  onNext: () => void;
  onBack: () => void;
  onCancel: () => void;
  onStartOver?: () => void;
  hasDraft?: boolean;
  isNextDisabled?: boolean;
  isSubmitting?: boolean;
  nextLabel?: string;
}

export const WizardNavigation: React.FC<WizardNavigationProps> = ({
  currentStep,
  totalSteps,
  onNext,
  onBack,
  onCancel,
  onStartOver,
  hasDraft = false,
  isNextDisabled = false,
  isSubmitting = false,
  nextLabel,
}) => {
  const t = useTranslations("Wizard");
  const isFirstStep = currentStep === 1;
  const isLastStep = currentStep === totalSteps;

  const primaryButton = isLastStep ? (
    <Button
      variant="primary"
      onClick={onNext}
      disabled={isNextDisabled || isSubmitting}
      isLoading={isSubmitting}
      className="w-full sm:w-auto"
    >
      {nextLabel || t("createAgent")}
    </Button>
  ) : (
    <Button
      variant="primary"
      onClick={onNext}
      disabled={isNextDisabled || isSubmitting}
      className="w-full sm:w-auto"
    >
      {t("next")}
    </Button>
  );

  return (
    <div className="sticky bottom-0 bg-white pt-4 sm:pt-6 pb-2 sm:pb-0 border-t border-gray-200">
      {/* Mobile: primary button on top (flex-col-reverse), secondary row below.
          Desktop: secondary actions left, primary right (justify-between). */}
      <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {!isFirstStep && (
            <Button variant="secondary" onClick={onBack} disabled={isSubmitting}>
              {t("back")}
            </Button>
          )}
          {(hasDraft || !isFirstStep) && onStartOver && (
            <Button
              variant="ghost"
              onClick={onStartOver}
              disabled={isSubmitting}
              className="text-gray-600 hover:text-gray-900"
            >
              {t("startOver")}
            </Button>
          )}
          <Button variant="ghost" onClick={onCancel} disabled={isSubmitting}>
            {t("cancel")}
          </Button>
        </div>
        {primaryButton}
      </div>
    </div>
  );
};


