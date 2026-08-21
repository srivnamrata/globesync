import { useEffect, useState } from 'react';
import { sseManager, ProgressUpdate, ProcessingType } from '../services/webSocketManager';

export function useProcessingStatus(
  projectId: string | undefined,
  type: ProcessingType
) {
  const [status, setStatus] = useState<ProgressUpdate | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;

    sseManager.connect(
      projectId,
      type,
      (update) => {
        setStatus(update);
        setError(null);
      },
      (err) => {
        setError('Stream disconnected. Attempting auto-reconnect...');
      }
    );

    return () => {
      sseManager.disconnect(projectId, type);
    };
  }, [projectId, type]);

  return { status, error };
}
