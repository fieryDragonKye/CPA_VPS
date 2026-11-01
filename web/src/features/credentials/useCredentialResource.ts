import { useEffect, useRef, useState } from 'react';
import { apiClient } from '@/services/api/client';

/** Abort replaced requests and never render data belonging to another query/session. */
export function useCredentialResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  enabled: boolean,
  reload: number
) {
  const [state, setState] = useState<{
    key: string;
    data: T | null;
    busy: boolean;
    error: boolean;
  }>({
    key: '',
    data: null,
    busy: false,
    error: false,
  });
  const sequence = useRef(0);
  useEffect(() => {
    if (!enabled) return;
    const request = ++sequence.current;
    const revision = apiClient.getConnectionRevision();
    const controller = new AbortController();
    const current = () =>
      !controller.signal.aborted &&
      request === sequence.current &&
      revision === apiClient.getConnectionRevision();
    setState((previous) => ({
      key,
      data: previous.key === key ? previous.data : null,
      busy: true,
      error: false,
    }));
    void load(controller.signal)
      .then((data) => {
        if (current()) setState({ key, data, busy: false, error: false });
      })
      .catch(() => {
        if (current()) setState({ key, data: null, busy: false, error: true });
      });
    return () => controller.abort();
  }, [key, load, enabled, reload]);
  return {
    data: state.key === key ? state.data : null,
    busy: enabled && (state.key !== key || state.busy),
    error: enabled && state.key === key && state.error,
  };
}
