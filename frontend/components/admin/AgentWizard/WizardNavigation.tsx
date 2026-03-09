/** Wizard navigation buttons component. */

import React from "react";
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
      {nextLabel || "Create Agent"}
    </Button>
  ) : (
    <Button
      variant="primary"
      onClick={onNext}
      disabled={isNextDisabled || isSubmitting}
      className="w-full sm:w-auto"
    >
      Next
    </Button>
  );

  return (
    <div className="pt-6 border-t border-gray-200">
      {/* Mobile: primary button on top, secondary row below.
          Desktop: secondary actions left, primary right (justify-between). */}
      <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {!isFirstStep && (
            <Button variant="secondary" onClick={onBack} disabled={isSubmitting}>
              Back
            </Button>
          )}
          {(hasDraft || !isFirstStep) && onStartOver && (
            <Button
              variant="ghost"
              onClick={onStartOver}
              disabled={isSubmitting}
              className="text-gray-600 hover:text-gray-900"
            >
              Start Over
            </Button>
          )}
          <Button variant="ghost" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        </div>
        {primaryButton}
      </div>
    </div>
  );
};


