import { useState, useCallback, useRef } from 'react';

interface StreamState<T> {
  data: T;
  loading: boolean;
  error: Error | null;
  isComplete: boolean;
}

interface StreamOptions {
  onData?: (data: string) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

export function useStreamFetch<T = string>(
  fetchFn: (options: StreamOptions) => () => void
) {
  const [state, setState] = useState<StreamState<T>>({
    data: '' as unknown as T,
    loading: false,
    error: null,
    isComplete: false,
  });

  const cancelRef = useRef<(() => void) | null>(null);

  const start = useCallback(
    (initialData?: T) => {
      if (cancelRef.current) {
        cancelRef.current();
      }

      setState({
        data: initialData || ('' as unknown as T),
        loading: true,
        error: null,
        isComplete: false,
      });

      const handleData = (chunk: string) => {
        setState((prev) => ({ ...prev, data: chunk as unknown as T }));
      };

      const handleComplete = () => {
        setState((prev) => ({ ...prev, loading: false, isComplete: true }));
      };

      const handleError = (error: Error) => {
        setState((prev) => ({ ...prev, loading: false, error, isComplete: true }));
      };

      cancelRef.current = fetchFn({
        onData: handleData,
        onComplete: handleComplete,
        onError: handleError,
      });
    },
    [fetchFn]
  );

  const cancel = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      setState((prev) => ({ ...prev, loading: false, isComplete: true }));
    }
  }, []);

  const reset = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
    }
    setState({ data: '' as unknown as T, loading: false, error: null, isComplete: false });
  }, []);

  return { ...state, start, cancel, reset };
}

export function useMarkdownStream(
  fetchFn: (options: StreamOptions) => () => void
) {
  const [markdown, setMarkdown] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);

  const start = useCallback(() => {
    if (cancelRef.current) cancelRef.current();
    setLoading(true);
    setError(null);
    setIsComplete(false);

    cancelRef.current = fetchFn({
      onData: (chunk) => setMarkdown(chunk),
      onComplete: () => { setLoading(false); setIsComplete(true); },
      onError: (err) => { setError(err); setLoading(false); setIsComplete(true); },
    });
  }, [fetchFn]);

  const cancel = useCallback(() => {
    if (cancelRef.current) { cancelRef.current(); setLoading(false); setIsComplete(true); }
  }, []);

  const reset = useCallback(() => {
    if (cancelRef.current) cancelRef.current();
    setMarkdown('');
    setLoading(false);
    setError(null);
    setIsComplete(false);
  }, []);

  return { markdown, loading, error, isComplete, start, cancel, reset };
}
