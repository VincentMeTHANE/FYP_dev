import { useState, useCallback } from 'react';
import type { ReportFlowParams, ChapterInfo } from '@/types';

interface ReportFlowState {
  reportId: string | null;
  title: string;
  chapters: ChapterInfo[];
  currentStep: number;
}

const initialState: ReportFlowState = {
  reportId: null,
  title: '',
  chapters: [],
  currentStep: 1,
};

export function useReportFlow() {
  const [state, setState] = useState<ReportFlowState>(initialState);

  const setReportId = useCallback((reportId: string) => {
    setState((prev) => ({ ...prev, reportId }));
  }, []);

  const setTitle = useCallback((title: string) => {
    setState((prev) => ({ ...prev, title }));
  }, []);

  const setChapters = useCallback((chapters: ChapterInfo[]) => {
    setState((prev) => ({ ...prev, chapters }));
  }, []);

  const setCurrentStep = useCallback((step: number) => {
    setState((prev) => ({ ...prev, currentStep: step }));
  }, []);

  const nextStep = useCallback(() => {
    setState((prev) => ({ ...prev, currentStep: prev.currentStep + 1 }));
  }, []);

  const prevStep = useCallback(() => {
    setState((prev) => ({ ...prev, currentStep: Math.max(1, prev.currentStep - 1) }));
  }, []);

  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  const initializeFromParams = useCallback((params: ReportFlowParams) => {
    setState((prev) => ({
      ...prev,
      reportId: params.report_id,
      title: params.title,
      chapters: params.chapters || [],
    }));
  }, []);

  return {
    ...state,
    setReportId,
    setTitle,
    setChapters,
    setCurrentStep,
    nextStep,
    prevStep,
    reset,
    initializeFromParams,
  };
}

export type ReportFlowStateType = ReturnType<typeof useReportFlow>;
