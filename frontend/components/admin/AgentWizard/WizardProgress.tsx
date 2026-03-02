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
    <div className="w-full mb-8 overflow-x-auto pb-2 -mx-1 px-1">
      <div className="flex items-start min-w-max">
        {steps.map((step, index) => {
          const isActive = step.number === currentStep;
          const isCompleted = step.number < currentStep;
          const isLast = index === steps.length - 1;

          return (
            <React.Fragment key={step.number}>
              <div className="flex flex-col items-center w-14 sm:w-16">
                <div
                  className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-medium text-xs sm:text-sm transition-all duration-200 flex-shrink-0 ${
                    isActive
                      ? "bg-[#251D1C] text-white border-2 border-[#251D1C]"
                      : isCompleted
                      ? "bg-[#251D1C] text-white border-2 border-[#251D1C]"
                      : "bg-gray-200 text-gray-600 border-2 border-gray-300"
                  }`}
                >
                  {isCompleted ? (
                    <svg
                      className="w-4 h-4 sm:w-5 sm:h-5"
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
                  className={`mt-1.5 text-xs font-medium text-center leading-tight max-w-[52px] sm:max-w-[64px] ${
                    isActive ? "text-[#251D1C]" : "text-gray-500"
                  }`}
                >
                  {step.title}
                </span>
              </div>
              {!isLast && (
                <div
                  className={`flex-shrink-0 w-6 sm:w-8 h-0.5 mt-4 sm:mt-5 transition-all duration-200 ${
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
