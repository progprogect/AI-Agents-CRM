/** Types for the questionnaire feature (admin UI). */

export interface QuestionnaireField {
  key: string;
  label: string;
  question: string;
  required: boolean;
  quick_replies: string[];
  order: number;
}

export interface QuestionnaireTemplate {
  agent_id: string;
  welcome_message: string;
  completion_message: string;
  fields: QuestionnaireField[];
  updated_at: string | null;
}

export interface QuestionnaireResponsePayload {
  template: QuestionnaireTemplate;
  submissions_count: number;
}

export type QuestionnaireSubmissionStatus = "in_progress" | "completed" | "cancelled";
export type QuestionnaireSubmissionSource = "fill" | "edit";

/** Must match backend ``list_questionnaire_submissions`` ``sort`` query. */
export type QuestionnaireSubmissionSort =
  | "started_at_desc"
  | "started_at_asc"
  | "completed_at_desc"
  | "completed_at_asc";

export interface QuestionnaireSubmission {
  submission_id: string;
  agent_id: string;
  external_user_id: string;
  channel: string;
  conversation_id: string | null;
  status: QuestionnaireSubmissionStatus;
  source: QuestionnaireSubmissionSource;
  started_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface QuestionnaireResponseItem {
  response_id: string;
  submission_id: string;
  agent_id: string;
  external_user_id: string;
  field_key: string;
  value: string;
  created_at: string;
}

export interface QuestionnaireSubmissionListItem {
  submission: QuestionnaireSubmission;
  answers_count: number;
  /** Present when ``include_field_snapshot`` was true on list request. */
  field_snapshot?: Record<string, string>;
}

export interface QuestionnaireSubmissionDetail {
  submission: QuestionnaireSubmission;
  responses: QuestionnaireResponseItem[];
}

export interface UserQuestionnaireDetail {
  external_user_id: string;
  latest_values: Record<string, string>;
  history: QuestionnaireResponseItem[];
}

export interface UpsertQuestionnaireRequest {
  welcome_message: string;
  completion_message: string;
  fields: QuestionnaireField[];
}
