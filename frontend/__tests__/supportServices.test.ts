import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/apiClient';
import { SSEConnectionManager } from '../services/webSocketManager';
import {
  mapAuthError,
  mapLanguageLoadError,
  mapProjectCreateError,
  mapProjectLoadError,
  mapUserFacingError,
} from '../services/userFacingErrors';
import { estimateTranslationSpeechDuration } from '../utils/durationEstimation';
import { estimateExportCostUSD, EXPORT_PRESETS } from '../utils/exportPresets';
import { formatDate, formatDateTime } from '../utils/formatDateTime';
import { getTextDirection } from '../utils/textDirection';

class EventSourceMock {
  static instances: EventSourceMock[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  listeners = new Map<string, (event: MessageEvent) => void>();
  close = vi.fn();

  constructor(public readonly url: string) {
    EventSourceMock.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners.set(type, listener as (event: MessageEvent) => void);
  }
}

describe('user-facing error mapping', () => {
  it.each([
    [new ApiError('denied', 401, {}), 'session expired'],
    [new ApiError('denied', 403, {}), 'session expired'],
    [new ApiError('missing', 404, {}), 'could not be found'],
    [new ApiError('stale', 409, {}), 'newer version'],
    [new ApiError('busy', 429, {}), 'busy right now'],
    [new ApiError('busy', 503, {}), 'busy right now'],
    [new ApiError('server', 500, {}), 'could not complete'],
    [new Error('Missing bearer token'), 'Sign in to continue'],
    [new Error('auth bootstrap is not configured'), 'Sign-in is temporarily unavailable'],
    [new Error('Google Identity Services failed'), 'Google sign-in is not available'],
    [new Error('Project API scope is not configured'), 'workspace is still being prepared'],
    [new Error('Failed to fetch'), 'could not reach the service'],
  ])('maps operational failures to actionable copy', (error, expected) => {
    expect(mapUserFacingError(error, 'fallback')).toContain(expected);
  });

  it('uses supplied fallbacks for unknown errors', () => {
    expect(mapUserFacingError({ reason: 'unknown' }, 'Friendly fallback')).toBe('Friendly fallback');
    expect(mapAuthError(null)).toContain('open GlobeSync sign-in');
    expect(mapProjectLoadError(null)).toContain('load your GlobeSync workspace');
    expect(mapProjectCreateError(null)).toContain('create your project');
    expect(mapLanguageLoadError(null)).toContain('default options');
  });
});

describe('SSEConnectionManager', () => {
  afterEach(() => {
    vi.useRealTimers();
    EventSourceMock.instances = [];
  });

  it('connects once, parses default and named progress events, and disconnects', () => {
    vi.stubGlobal('EventSource', EventSourceMock);
    const manager = new SSEConnectionManager();
    const onUpdate = vi.fn();
    manager.connect('project-1', 'translation', onUpdate);
    manager.connect('project-1', 'translation', onUpdate);

    expect(EventSourceMock.instances).toHaveLength(1);
    expect(EventSourceMock.instances[0].url)
      .toBe('http://localhost:8000/v1/translation/project-1/stream');
    EventSourceMock.instances[0].onmessage?.(
      new MessageEvent('message', { data: JSON.stringify({ status: 'completed' }) }),
    );
    EventSourceMock.instances[0].listeners.get('progress')?.(
      new MessageEvent('progress', { data: JSON.stringify({ status: 'in_progress' }) }),
    );
    expect(onUpdate).toHaveBeenCalledTimes(2);

    manager.disconnect('project-1', 'translation');
    expect(EventSourceMock.instances[0].close).toHaveBeenCalled();
  });

  it('uses the job endpoint for lip-sync and reconnects after errors', () => {
    vi.useFakeTimers();
    vi.stubGlobal('EventSource', EventSourceMock);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const manager = new SSEConnectionManager();
    const onError = vi.fn();
    manager.connect('job-1', 'lipsync', vi.fn(), onError);

    expect(EventSourceMock.instances[0].url)
      .toBe('http://localhost:8000/v1/lipsync/job/job-1/stream');
    EventSourceMock.instances[0].onerror?.(new Event('error'));
    expect(onError).toHaveBeenCalled();
    expect(EventSourceMock.instances[0].close).toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(EventSourceMock.instances).toHaveLength(2);
    manager.disconnectAll();
    expect(EventSourceMock.instances[1].close).toHaveBeenCalled();
  });

  it('contains malformed event payloads', () => {
    vi.stubGlobal('EventSource', EventSourceMock);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const manager = new SSEConnectionManager();
    const onUpdate = vi.fn();
    manager.connect('project-1', 'transcription', onUpdate);
    EventSourceMock.instances[0].onmessage?.(new MessageEvent('message', { data: '{bad' }));
    EventSourceMock.instances[0].listeners.get('progress')?.(
      new MessageEvent('progress', { data: '{bad' }),
    );
    expect(onUpdate).not.toHaveBeenCalled();
  });
});

describe('formatting and estimation utilities', () => {
  it('calculates language-aware speech durations', () => {
    expect(estimateTranslationSpeechDuration('one two', 'de')).toBe(1);
    expect(estimateTranslationSpeechDuration('one two', 'fr')).toBe(0.89);
    expect(estimateTranslationSpeechDuration('日本語', 'ja')).toBe(0.75);
    expect(estimateTranslationSpeechDuration('one two', 'unknown')).toBe(0.86);
  });

  it('calculates export costs across resolutions and quality', () => {
    expect(estimateExportCostUSD(100, '1080p', 'normal')).toBe(0.2);
    expect(estimateExportCostUSD(100, '2k', 'normal')).toBe(0.4);
    expect(estimateExportCostUSD(100, '4k', 'high')).toBe(1.2);
    expect(EXPORT_PRESETS.web_standard.codec).toBe('h264');
  });

  it('formats valid and invalid dates and text direction', () => {
    expect(formatDate('not-a-date')).toBe('Date unavailable');
    expect(formatDateTime('not-a-date')).toBe('Date unavailable');
    expect(formatDate('2026-01-01T00:00:00.000Z')).not.toBe('Date unavailable');
    expect(formatDateTime('2026-01-01T00:00:00.000Z')).not.toBe('Date unavailable');
    expect(getTextDirection('ar')).toBe('rtl');
    expect(getTextDirection('HE')).toBe('rtl');
    expect(getTextDirection('en')).toBe('ltr');
  });
});
