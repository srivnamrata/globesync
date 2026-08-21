export type ProcessingType = 'transcription' | 'translation' | 'tts' | 'lipsync';

export interface ProgressUpdate {
  project_id?: string;
  job_id?: string;
  status: 'queued' | 'in_progress' | 'completed' | 'failed';
  progress_percent: number;
  message: string;
  eta_seconds?: number;
  timestamp: number;
}

export class SSEConnectionManager {
  private eventSources: Record<string, EventSource> = {};
  private reconnectIntervals: Record<string, number> = {};
  private activeProjectIds: Record<string, string> = {};

  connect(
    projectId: string,
    type: ProcessingType,
    onUpdate: (data: ProgressUpdate) => void,
    onError?: (err: Event) => void
  ) {
    const streamKey = `${projectId}_${type}`;
    if (this.eventSources[streamKey]) {
      return; // Already connected
    }

    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';
    // Map types to corresponding endpoints
    let url = `${baseUrl}/${type}/${projectId}/stream`;
    if (type === 'lipsync') {
      url = `${baseUrl}/lipsync/job/${projectId}/stream`;
    }

    const eventSource = new EventSource(url);
    this.eventSources[streamKey] = eventSource;
    this.activeProjectIds[streamKey] = projectId;

    eventSource.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        onUpdate(parsed as ProgressUpdate);
      } catch (err) {
        console.error('Failed to parse SSE progress update payload:', err);
      }
    };

    eventSource.addEventListener('progress', (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        onUpdate(parsed as ProgressUpdate);
      } catch (err) {
        console.error('Failed to parse progress event:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.error(`SSE stream connection failed for: ${streamKey}`, err);
      if (onError) onError(err);

      // Attempt exponential backoff auto-reconnect
      this.reconnect(projectId, type, onUpdate, onError);
    };
  }

  private reconnect(
    projectId: string,
    type: ProcessingType,
    onUpdate: (data: ProgressUpdate) => void,
    onError?: (err: Event) => void
  ) {
    const streamKey = `${projectId}_${type}`;
    this.disconnect(projectId, type);

    const currentDelay = this.reconnectIntervals[streamKey] || 1000;
    const nextDelay = Math.min(30000, currentDelay * 2);
    this.reconnectIntervals[streamKey] = nextDelay;

    console.log(`Scheduling SSE auto-reconnect in ${currentDelay}ms...`);
    setTimeout(() => {
      this.connect(projectId, type, onUpdate, onError);
    }, currentDelay);
  }

  disconnect(projectId: string, type: ProcessingType) {
    const streamKey = `${projectId}_${type}`;
    const eventSource = this.eventSources[streamKey];
    if (eventSource) {
      eventSource.close();
      delete this.eventSources[streamKey];
      console.log(`SSE Connection terminated: ${streamKey}`);
    }
  }

  disconnectAll() {
    Object.keys(this.eventSources).forEach((key) => {
      this.eventSources[key].close();
    });
    this.eventSources = {};
    this.reconnectIntervals = {};
    console.log('All SSE stream links disconnected.');
  }
}

export const sseManager = new SSEConnectionManager();
