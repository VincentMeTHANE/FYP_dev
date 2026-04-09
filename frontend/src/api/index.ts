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

// 使用相对路径，通过 vite.config.ts 中的代理转发到后端
const API_BASE = '/api';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==================== 报告相关接口 ====================

// 创建报告
export async function createReport(): Promise<string> {
  const response = await apiClient.post<ApiResponse<string>>('/report/create');
  return response.data.data;
}

// 获取报告详情
export async function getReportDetail(reportId: string): Promise<ReportDetail> {
  const response = await apiClient.get<ApiResponse<ReportDetail>>(`/report/detail/${reportId}`);
  return response.data.data;
}

// 获取报告进度
export async function getReportProgress(reportId: string): Promise<StepProgress> {
  const response = await apiClient.get<ApiResponse<{
    report_id: string;
    status: string;
    progress_percentage: number;
    steps: StepProgress;
  }>>(`/report/progress/${reportId}`);
  return response.data.data.steps;
}

// 获取Token统计
export async function getTokenStats(reportId: string): Promise<TokenStats> {
  const response = await apiClient.get<ApiResponse<TokenStats>>(`/report/token-stats/${reportId}`);
  return response.data.data;
}

// ==================== 询问问题相关接口 ====================

// 询问问题 - 流式
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
          // 如果解析失败，可能是纯文本内容
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

    // 返回取消函数
    return () => controller.abort();
  } catch (error) {
    onError(error as Error);
    return () => {};
  }
}

// 更新问题
export async function updateQuestions(reportId: string, message: string): Promise<boolean> {
  const response = await apiClient.put<ApiResponse<boolean>>('/ask_questions/update', {
    report_id: reportId,
    message: message
  });
  return response.data.data;
}

// 获取问题详情
export async function getQuestionsDetail(reportId: string): Promise<string> {
  const response = await apiClient.get<ApiResponse<string>>(`/ask_questions/detail/${reportId}`);
  return response.data.data;
}

// ==================== 大纲相关接口 ====================

// 生成大纲 - 流式
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

// 拆分大纲
export async function splitPlan(reportId: string): Promise<PlanSplitResponse> {
  const response = await apiClient.post<ApiResponse<PlanSplitResponse>>(`/plan/split/${reportId}`);
  return response.data.data;
}

// 获取大纲详情
export async function getPlanDetail(reportId: string): Promise<{ plan: string }> {
  const response = await apiClient.get<ApiResponse<{ plan: string }>>(`/plan/detail/${reportId}`);
  return response.data.data;
}

// 更新大纲
export async function updatePlan(reportId: string, plan: string): Promise<boolean> {
  const response = await apiClient.put<ApiResponse<boolean>>('/plan/update', {
    report_id: reportId,
    plan: plan
  });
  return response.data.data;
}

// ==================== SERP相关接口 ====================

// 生成SERP - 流式
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

// 获取task_id列表
export async function getTaskIds(splitId: string): Promise<SerpTask[]> {
  const response = await apiClient.get<ApiResponse<SerpTask[]>>(`/serp/get_task_id/${splitId}`);
  return response.data.data;
}

// 获取所有章节的SERP任务
export async function getAllSerpTasks(reportId: string): Promise<SerpTask[]> {
  const response = await apiClient.get<ApiResponse<SerpTask[]>>(`/serp/get_task_id/${reportId}`);
  return response.data.data;
}

// ==================== 搜索相关接口 ====================

// 执行搜索
export async function executeSearch(request: SearchRequest): Promise<SearchResponse> {
  const response = await apiClient.post<ApiResponse<SearchResponse>>('/search/search', request);
  return response.data.data;
}

// ==================== 搜索总结相关接口 ====================

// 生成搜索总结 - completion模式（非流式）
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
    const errorMessage = error.response?.data?.message || error.message || '未知错误';
    return { success: false, error: errorMessage };
  }
}

// 生成搜索总结 - 流式（保留原有功能供参考）
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

// ==================== 最终报告相关接口 ====================

// 生成引言
export async function getIntroduction(reportId: string): Promise<string> {
  const response = await apiClient.get<ApiResponse<string>>(`/final/introduction/${reportId}`);
  return response.data.data;
}

// 生成报告正文 - 流式
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

// 生成报告总结 - 流式
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

// 获取最终报告详情
export async function getFinalReportDetail(reportId: string): Promise<FinalReportDetail> {
  const response = await apiClient.get<ApiResponse<FinalReportDetail>>(`/final/final/detail/${reportId}`);
  return response.data.data;
}

// 下载PDF
export function getDownloadPdfUrl(reportId: string): string {
  return `${API_BASE}/final/download/pdf/${reportId}`;
}

// 下载Word
export function getDownloadWordUrl(reportId: string, includeReferences: boolean = false): string {
  return `${API_BASE}/final/download/word/${reportId}?is_include_references=${includeReferences}`;
}

export default apiClient;
