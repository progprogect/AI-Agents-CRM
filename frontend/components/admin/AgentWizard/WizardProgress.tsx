/** Wizard progress bar component. */

import React from "react";

interface WizardProgressProps {
  currentStep: number;
  totalSteps: number;
  steps: Array<{ number: number; title: string }>;
}

export const WizardProgress: React.FC<WizardProgressProps> = ({
  currentStep,
  steps,
}) => {
  return (
    <div className="w-full mb-8">
      <div className="flex items-center justify-between">
        {steps.map((step, index) => {
          const isActive = step.number === currentStep;
          const isCompleted = step.number < currentStep;
          const isLast = index === steps.length - 1;

          return (
            <React.Fragment key={step.number}>
              <div className="flex flex-col items-center flex-1">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-medium text-sm transition-all duration-200 ${
                    isActive
                      ? "bg-[#251D1C] text-white border-2 border-[#251D1C]"
                      : isCompleted
                      ? "bg-[#251D1C] text-white border-2 border-[#251D1C]"
                      : "bg-gray-200 text-gray-600 border-2 border-gray-300"
                  }`}
                >
                  {isCompleted ? (
                    <svg
                      className="w-6 h-6"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    step.number
                  )}
                </div>
                <span
                  className={`mt-2 text-xs font-medium text-center ${
                    isActive ? "text-[#251D1C]" : "text-gray-600"
                  }`}
                >
                  {step.title}
                </span>
              </div>
              {!isLast && (
                <div
                  className={`flex-1 h-0.5 mx-2 transition-all duration-200 ${
                    isCompleted ? "bg-[#251D1C]" : "bg-gray-300"
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

