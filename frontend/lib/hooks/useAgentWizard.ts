/** Hook for managing agent wizard state. */

import { useReducer, useCallback, useEffect } from "react";
import type { AgentConfigFormData } from "../utils/agentConfig";
import { generateDefaultConfig } from "../utils/agentConfig";
import { validateAgentConfig, type ValidationError } from "../utils/validation";

const DRAFT_STORAGE_KEY = "agent_wizard_draft";

export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;

interface WizardState {
  currentStep: WizardStep;
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  isSubmitting: boolean;
}

type WizardAction =
  | { type: "SET_STEP"; step: WizardStep }
  | { type: "UPDATE_CONFIG"; config: Partial<AgentConfigFormData> }
  | { type: "SET_ERRORS"; errors: ValidationError[] }
  | { type: "SET_SUBMITTING"; isSubmitting: boolean }
  | { type: "RESET" };

// Load draft from localStorage if available
const loadDraft = (): Partial<WizardState> => {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const draft = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (draft) {
      const parsed = JSON.parse(draft);
      return {
        currentStep: parsed.currentStep || 1,
        config: parsed.config || generateDefaultConfig(),
      };
    }
  } catch (e) {
    console.error("Failed to load draft:", e);
  }
  return {};
};

// Create initial state function to avoid SSR issues
const createInitialState = (): WizardState => {
  const draftData = loadDraft();
  return {
    currentStep: (draftData.currentStep as WizardStep) || 1,
    config: draftData.config || generateDefaultConfig(),
    errors: [],
    isSubmitting: false,
  };
};

const initialState: WizardState = {
  currentStep: 1,
  config: generateDefaultConfig(),
  errors: [],
  isSubmitting: false,
};

function wizardReducer(
  state: WizardState,
  action: WizardAction
): WizardState {
  switch (action.type) {
    case "SET_STEP":
      return { ...state, currentStep: action.step };
    case "UPDATE_CONFIG":
      return {
        ...state,
        config: { ...state.config, ...action.config },
        errors: [], // Clear errors when config updates
      };
    case "SET_ERRORS":
      return { ...state, errors: action.errors };
    case "SET_SUBMITTING":
      return { ...state, isSubmitting: action.isSubmitting };
    case "RESET":
      // Return clean initial state without draft
      return {
        currentStep: 1,
        config: generateDefaultConfig(),
        errors: [],
        isSubmitting: false,
      };
    default:
      return state;
  }
}

export function useAgentWizard() {
  // Initialize with draft if available (client-side only)
  const [state, dispatch] = useReducer(wizardReducer, initialState, () => {
    // Use lazy initialization to load draft on client-side only
    if (typeof window !== "undefined") {
      return createInitialState();
    }
    return initialState;
  });

  // Auto-save draft to localStorage
  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      // Load existing draft to preserve edit/clone flags
      const existingDraft = localStorage.getItem(DRAFT_STORAGE_KEY);
      let draftData: any = {
        currentStep: state.currentStep,
        config: state.config,
        timestamp: Date.now(),
      };

      // Preserve isEdit, editingAgentId, isClone, sourceAgentId if they exist
      if (existingDraft) {
        try {
          const parsed = JSON.parse(existingDraft);
          if (parsed.isEdit) {
            draftData.isEdit = true;
            draftData.editingAgentId = parsed.editingAgentId;
          }
          if (parsed.isClone) {
            draftData.isClone = true;
            draftData.sourceAgentId = parsed.sourceAgentId;
          }
        } catch (e) {
          // Ignore parse errors, use new draft
        }
      }

      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draftData));
    } catch (e) {
      console.error("Failed to save draft:", e);
    }
  }, [state.currentStep, state.config]);

  const setStep = useCallback((step: WizardStep) => {
    dispatch({ type: "SET_STEP", step });
  }, []);

  const updateConfig = useCallback((config: Partial<AgentConfigFormData>) => {
    dispatch({ type: "UPDATE_CONFIG", config });
  }, []);

  const validateCurrentStep = useCallback((): boolean => {
    const errors = validateAgentConfig(state.config);
    dispatch({ type: "SET_ERRORS", errors });

    // Filter errors for current step
    const stepFields: Record<WizardStep, string[]> = {
      1: ["agent_id", "agent_display_name", "clinic_display_name", "languages"],
      2: ["tone", "formality", "empathy_level", "depth_level", "message_length", "persuasion"],
      3: ["examples"],
      4: ["rag_enabled", "rag_embeddings_provider", "rag_vision_provider"],
      5: ["escalation_rules"],
      6: ["llm_provider", "llm_model", "llm_temperature", "llm_max_tokens"],
      7: [],
    };

    const stepErrors = errors.filter((error) =>
      stepFields[state.currentStep].some((field) =>
        error.field.startsWith(field)
      )
    );

    return stepErrors.length === 0;
  }, [state.config, state.currentStep]);

  const nextStep = useCallback(() => {
    if (validateCurrentStep()) {
      const next = Math.min(state.currentStep + 1, 7) as WizardStep;
      dispatch({ type: "SET_STEP", step: next });
      return true;
    }
    return false;
  }, [state.currentStep, validateCurrentStep]);

  const prevStep = useCallback(() => {
    const prev = Math.max(state.currentStep - 1, 1) as WizardStep;
    dispatch({ type: "SET_STEP", step: prev });
  }, [state.currentStep]);

  const reset = useCallback(() => {
    dispatch({ type: "RESET" });
    // Clear draft from localStorage
    if (typeof window !== "undefined") {
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  }, []);

  const clearDraft = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  }, []);

  const hasDraft = useCallback((): boolean => {
    if (typeof window === "undefined") return false;
    try {
      const draft = localStorage.getItem(DRAFT_STORAGE_KEY);
      return !!draft && !!JSON.parse(draft);
    } catch {
      return false;
    }
  }, []);

  const setSubmitting = useCallback((isSubmitting: boolean) => {
    dispatch({ type: "SET_SUBMITTING", isSubmitting });
  }, []);

  return {
    state,
    setStep,
    updateConfig,
    validateCurrentStep,
    nextStep,
    prevStep,
    reset,
    setSubmitting,
    clearDraft,
    hasDraft,
  };
}

