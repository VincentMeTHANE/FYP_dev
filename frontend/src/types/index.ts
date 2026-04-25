// API response base types
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

// Report-related types
export interface ReportCreateResponse {
  report_id: string;
}

export interface ReportDetail {
  _id: string;
  title: string;
  message: string;
  status: string;
  progress_percentage: number;
  template?: string;
  is_replace?: boolean;
}

export interface ChapterInfo {
  split_id: string;
  content: string;
  sectionTitle: string;
}

export interface PlanSplitResponse {
  split_id: string;
  chapters_count: number;
  response: ChapterInfo[];
  execution_time: number;
}

// SERP-related types
export interface SerpQuery {
  query: string;
  researchGoal: string;
  task_id?: string;
}

export interface SerpTask {
  query: string;
  researchGoal: string;
  task_id: string;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
}

// Search-related types
export interface SearchRequest {
  task_id: string;
  max_results?: number;
  include_images?: boolean;
  use_rag?: boolean;
}

export interface SearchResponse {
  task_id: string;
  query: string;
  response_time: number;
  images: Array<{ url: string; description: string }>;
  sources: Array<{
    title: string;
    url: string;
    content: string;
    score?: number;
  }>;
  knowledge_count: number;
  web_count: number;
}

// Final report types
export interface FinalReportRequest {
  report_id: string;
  split_id: string;
  requirement?: string;
}

export interface FinalReportDetail {
  report_title: string;
  report_content: string | Record<string, string>;
  results: Array<{
    title: string;
    url: string;
    result_index: number;
  }>;
  report_introduction: string;
  report_summary: string;
}

// Step progress types
export interface StepProgress {
  ask_questions: StepStatus;
  plan: StepStatus;
  serp: StepStatus;
  search: StepStatus;
  search_summary: StepStatus;
}

export interface StepStatus {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  completed: boolean;
}

// Step statistics types
export interface StepStats {
  execution_time?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

// Token statistics types
export interface TokenStats {
  report_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  step_stats: Array<{
    collection: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    execution_time?: number;
  }>;
}

// Cumulative statistics (for frontend display)
export interface CumulativeStats {
  total_execution_time: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  step_times: Record<string, number>;
}

// Streaming callback types
export type StreamCallback = (data: string, isComplete: boolean) => void;

// Page navigation parameters
export interface ReportFlowParams {
  report_id: string;
  title: string;
  chapters?: ChapterInfo[];
  taskIds?: string[];
}
