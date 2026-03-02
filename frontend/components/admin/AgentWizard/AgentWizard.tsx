/** Main agent wizard container component. */

"use client";

import React from "react";
import { useAgentWizard } from "@/lib/hooks/useAgentWizard";
import { WizardProgress } from "./WizardProgress";
import { WizardNavigation } from "./WizardNavigation";
import { BasicInfoStep } from "./steps/BasicInfoStep";
import { StyleStep } from "./steps/StyleStep";
import { ExamplesStep } from "./steps/ExamplesStep";
import { RAGStep } from "./steps/RAGStep";
import { EscalationStep } from "./steps/EscalationStep";
import { LLMStep } from "./steps/LLMStep";
import { ReviewStep, type AgentWizardSuccessResult } from "./steps/ReviewStep";

const WIZARD_STEPS = [
  { number: 1, title: "Basic Info" },
  { number: 2, title: "Style" },
  { number: 3, title: "Examples" },
  { number: 4, title: "RAG" },
  { number: 5, title: "Escalation" },
  { number: 6, title: "LLM Settings" },
  { number: 7, title: "Review" },
];

interface AgentWizardProps {
  onSuccess: (result?: AgentWizardSuccessResult) => void;
  onCancel: () => void;
}

export const AgentWizard: React.FC<AgentWizardProps> = ({
  onSuccess,
  onCancel,
}) => {
  const {
    state,
    updateConfig,
    nextStep,
    prevStep,
    reset,
    clearDraft,
    hasDraft,
  } = useAgentWizard();
  
  // Check if we're editing an existing agent and get agent ID
  const { isEditMode, editingAgentId } = React.useMemo(() => {
    if (typeof window === "undefined") return { isEditMode: false, editingAgentId: null as string | null };
    try {
      const draft = localStorage.getItem("agent_wizard_draft");
      if (draft) {
        const parsed = JSON.parse(draft);
        const edit = parsed.isEdit === true && !!parsed.editingAgentId;
        return { isEditMode: edit, editingAgentId: edit ? parsed.editingAgentId : null };
      }
    } catch {
      return { isEditMode: false, editingAgentId: null };
    }
    return { isEditMode: false, editingAgentId: null };
  }, []);

  const handleNext = () => {
    if (nextStep()) {
      // Step validation passed, proceed
    }
  };

  const handleCancel = () => {
    // Draft is already saved automatically, just navigate away
    onCancel();
  };

  const handleStartOver = () => {
    // Ask for confirmation before clearing draft
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(
        "Are you sure you want to start over? This will clear all your current progress and cannot be undone."
      );
      if (confirmed) {
        clearDraft();
        reset();
      }
    } else {
      // On server-side, just clear and reset
      clearDraft();
      reset();
    }
  };

  const handleSuccess = (result?: AgentWizardSuccessResult) => {
    clearDraft();
    reset();
    onSuccess(result);
  };

  const renderStep = () => {
    switch (state.currentStep) {
      case 1:
        return (
          <BasicInfoStep
            config={state.config}
            errors={state.errors}
            onUpdate={updateConfig}
          />
        );
      case 2:
        return (
          <StyleStep
            config={state.config}
            errors={state.errors}
            onUpdate={updateConfig}
          />
        );
      case 3:
        return (
          <ExamplesStep
            config={state.config}
            errors={state.errors}
            onUpdate={updateConfig}
          />
        );
        case 4:
        return (
          <RAGStep
            config={state.config}
            onUpdate={updateConfig}
            agentId={editingAgentId ?? undefined}
          />
        );
      case 5:
        return (
          <EscalationStep
            config={state.config}
            errors={state.errors}
            onUpdate={updateConfig}
          />
        );
      case 6:
        return (
          <LLMStep
            config={state.config}
            errors={state.errors}
            onUpdate={updateConfig}
          />
        );
      case 7:
        return (
          <ReviewStep
            config={state.config}
            isSubmitting={state.isSubmitting}
            onSubmit={async (result) => {
              handleSuccess(result);
            }}
            onStartOver={handleStartOver}
            onBack={prevStep}
            hasDraft={hasDraft()}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-sm shadow-md border border-[#BEBAB7] p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          {isEditMode ? "Edit Agent" : "Create New Agent"}
        </h2>

        <WizardProgress
          currentStep={state.currentStep}
          totalSteps={WIZARD_STEPS.length}
          steps={WIZARD_STEPS}
        />

        <div className="min-h-[400px]">{renderStep()}</div>

        {/* Hide navigation on last step - ReviewStep has its own button */}
        {state.currentStep < WIZARD_STEPS.length && (
          <WizardNavigation
            currentStep={state.currentStep}
            totalSteps={WIZARD_STEPS.length}
            onNext={handleNext}
            onBack={prevStep}
            onCancel={handleCancel}
            onStartOver={handleStartOver}
            hasDraft={hasDraft()}
            isSubmitting={state.isSubmitting}
          />
        )}
      </div>
    </div>
  );
};

