import axios, { AxiosInstance } from 'axios';
import type {
  ApiResponse,
  ReportCreateResponse,
  ReportDetail,
  PlanSplitResponse,
  SerpTask,
  SearchRequest,
  SearchResponse,
  FinalReportDetail,
  StepProgress,
  TokenStats
} from '@/types';

// Use relative path, forwarded to backend via vite.config.ts proxy
const API_BASE = '/api';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==================== Report API ====================

// Create report
export async function createReport(): Promise<string> {
  const response = await apiClient.post<ApiResponse<string>>('/report/create');
  return response.data.data;
}

// Get report details
export async function getReportDetail(reportId: string): Promise<ReportDetail> {
  const response = await apiClient.get<ApiResponse<ReportDetail>>(`/report/detail/${reportId}`);
  return response.data.data;
}

// Get report progress
export async function getReportProgress(reportId: string): Promise<StepProgress> {
  const response = await apiClient.get<ApiResponse<{
    report_id: string;
    status: string;
    progress_percentage: number;
    steps: StepProgress;
  }>>(`/report/progress/${reportId}`);
  return response.data.data.steps;
}

// Get token statistics
export async function getTokenStats(reportId: string): Promise<TokenStats> {
  const response = await apiClient.get<ApiResponse<TokenStats>>(`/report/token-stats/${reportId}`);
  return response.data.data;
}

// ==================== Ask Questions API ====================

// Ask questions - stream
export async function fetchAskQuestionsStream(
  reportId: string,
  message: string,
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void,
  templateId?: string
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/ask_questions/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        message: message,
        template_id: templateId || null
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// Update questions
export async function updateQuestions(reportId: string, message: string): Promise<boolean> {
  const response = await apiClient.put<ApiResponse<boolean>>('/ask_questions/update', {
    report_id: reportId,
    message: message
  });
  return response.data.data;
}

// Get questions details
export async function getQuestionsDetail(reportId: string): Promise<string> {
  const response = await apiClient.get<ApiResponse<string>>(`/ask_questions/detail/${reportId}`);
  return response.data.data;
}

// ==================== Plan API ====================

// Generate plan - stream
export async function fetchPlanStream(
  reportId: string,
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/plan/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        message: ''
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// Split plan
export async function splitPlan(reportId: string): Promise<PlanSplitResponse> {
  const response = await apiClient.post<ApiResponse<PlanSplitResponse>>(`/plan/split/${reportId}`);
  return response.data.data;
}

// Get plan details
export async function getPlanDetail(reportId: string): Promise<{ plan: string }> {
  const response = await apiClient.get<ApiResponse<{ plan: string }>>(`/plan/detail/${reportId}`);
  return response.data.data;
}

// Update plan
export async function updatePlan(reportId: string, plan: string): Promise<boolean> {
  const response = await apiClient.put<ApiResponse<boolean>>('/plan/update', {
    report_id: reportId,
    plan: plan
  });
  return response.data.data;
}

// ==================== SERP API ====================

// Generate SERP - stream
export async function fetchSerpStream(
  reportId: string,
  splitId: string,
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/serp/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        split_id: splitId
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// Get task_id list
export async function getTaskIds(splitId: string): Promise<SerpTask[]> {
  const response = await apiClient.get<ApiResponse<SerpTask[]>>(`/serp/get_task_id/${splitId}`);
  return response.data.data;
}

// Get all SERP tasks for report
export async function getAllSerpTasks(reportId: string): Promise<SerpTask[]> {
  const response = await apiClient.get<ApiResponse<SerpTask[]>>(`/serp/get_task_id/${reportId}`);
  return response.data.data;
}

// ==================== Search API ====================

// Execute search
export async function executeSearch(request: SearchRequest): Promise<SearchResponse> {
  const response = await apiClient.post<ApiResponse<SearchResponse>>('/search/search', request);
  return response.data.data;
}

// ==================== Search Summary API ====================

// Generate search summary - completion mode (non-streaming)
export async function fetchSummaryCompletion(
  reportId: string,
  taskId: string,
  searchId: string
): Promise<{ success: boolean; data?: any; error?: string }> {
  try {
    const response = await apiClient.post<ApiResponse<any>>('/summary/completion', {
      report_id: reportId,
      task_id: taskId,
      search_id: searchId
    });
    return { success: true, data: response.data.data };
  } catch (error: any) {
    const errorMessage = error.response?.data?.message || error.message || 'Unknown error';
    return { success: false, error: errorMessage };
  }
}

// Generate search summary - streaming
export async function fetchSummaryStream(
  reportId: string,
  taskId: string,
  searchId: string,
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/summary/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        task_id: taskId,
        search_id: searchId
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// ==================== Final Report API ====================

// Generate introduction
export async function getIntroduction(reportId: string): Promise<string> {
  const response = await apiClient.get<ApiResponse<string>>(`/final/introduction/${reportId}`);
  return response.data.data;
}

// Generate report body - streaming
export async function fetchFinalReportStream(
  reportId: string,
  splitId: string,
  requirement: string = '',
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/final/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        split_id: splitId,
        requirement: requirement
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// Generate report summary - streaming
export async function fetchSummaryReportStream(
  reportId: string,
  onData: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: Error) => void
): Promise<() => void> {
  const controller = new AbortController();

  try {
    const response = await fetch(`${API_BASE}/final/summary/${reportId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    const processLine = (line: string) => {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.choices && parsed.choices[0]?.delta?.content) {
            const content = parsed.choices[0].delta.content;
            fullContent += content;
            onData(fullContent);
          }
        } catch {
          onData(data);
        }
      }
    };

    const read = async () => {
      try {
        const { done, value } = await reader.read();
        if (done) {
          onComplete();
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }

        read();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError(error as Error);
        }
      }
    };

    read();

    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// Get final report details
export async function getFinalReportDetail(reportId: string): Promise<FinalReportDetail> {
  const response = await apiClient.get<ApiResponse<FinalReportDetail>>(`/final/final/detail/${reportId}`);
  return response.data.data;
}

// Download PDF
export function getDownloadPdfUrl(reportId: string): string {
  return `${API_BASE}/final/download/pdf/${reportId}`;
}

// Download Word
export function getDownloadWordUrl(reportId: string, includeReferences: boolean = false): string {
  return `${API_BASE}/final/download/word/${reportId}?is_include_references=${includeReferences}`;
}

export default apiClient;
