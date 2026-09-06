import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useHistory } from '../hooks/useHistory';
import { usePlayback } from '../hooks/usePlayback';
import { useProcessingStatus } from '../hooks/useProcessingStatus';
import { useProjectAutoSave } from '../hooks/useProject';
import { useReTranslation } from '../hooks/useReTranslation';
import { useSegmentManipulation } from '../hooks/useSegmentManipulation';
import { useTimeline } from '../hooks/useTimeline';
import { useTranscriptEditor } from '../hooks/useTranscriptEditor';
import { useWordTiming } from '../hooks/useWordTiming';
import { useExportStore } from '../store/exportStore';
import { useHistoryStore, type Action } from '../store/historyStore';
import { useMediaStore } from '../store/mediaStore';
import { useProjectStore } from '../store/projectStore';
import { useTimelineStore } from '../store/timelineStore';
import { useTranscriptStore, type TranscriptSegment } from '../store/transcriptStore';
import { useTranslationStore } from '../store/translationStore';
import { useUIStore } from '../store/uiStore';
import { projectFixture } from '../test/fixtures';

const storage = vi.hoisted(() => ({ saveDraft: vi.fn() }));
const sse = vi.hoisted(() => ({ connect: vi.fn(), disconnect: vi.fn() }));

vi.mock('../services/storageService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/storageService')>();
  return { ...actual, storageService: storage };
});
vi.mock('../services/webSocketManager', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/webSocketManager')>();
  return { ...actual, sseManager: sse };
});

const transcriptSegment = (overrides: Partial<TranscriptSegment> = {}): TranscriptSegment => ({
  id: 'segment-1',
  original_text: 'Hello world',
  translated_text: 'Hola mundo',
  start_time: 0,
  end_time: 2,
  speaker: 'Speaker 1',
  confidence: 0.9,
  words: [
    { text: 'Hello', start_time: 0, end_time: 0.8, confidence: 0.9 },
    { text: 'world', start_time: 1, end_time: 2, confidence: 0.9 },
  ],
  locked: false,
  edited: false,
  ...overrides,
});

describe('supporting Zustand stores', () => {
  beforeEach(() => {
    useExportStore.setState({ jobs: [], currentJob: null });
    useHistoryStore.setState({ undoStack: [], redoStack: [] });
    useTimelineStore.setState({
      currentTimeSeconds: 0,
      isPlaying: false,
      zoomLevel: 100,
      selectedSegmentId: null,
    });
    useTranscriptStore.setState({ segments: [], selectedSegmentId: null });
    useUIStore.setState({
      activeTab: 'transcript',
      isExportDialogOpen: false,
      notifications: [],
      theme: 'dark',
    });
  });

  it('manages export queue progress and the selected job', () => {
    const job = {
      id: 'job-1',
      projectId: 'project-1',
      targetLanguage: 'es',
      burnInSubtitles: false,
      status: 'queued' as const,
      progressPercent: 0,
      createdAt: '2026-01-01T00:00:00.000Z',
    };
    const other = { ...job, id: 'job-2' };
    useExportStore.getState().setJobs([other]);
    useExportStore.getState().addJob(job);
    useExportStore.getState().updateJobProgress('job-1', 45, 'processing');

    expect(useExportStore.getState().jobs[0]).toMatchObject({
      id: 'job-1',
      progressPercent: 45,
      status: 'processing',
    });
    expect(useExportStore.getState().currentJob).toMatchObject({ id: 'job-1', progressPercent: 45 });

    useExportStore.getState().setCurrentJob(null);
    useExportStore.getState().updateJobProgress('missing', 10);
    expect(useExportStore.getState().currentJob).toBeNull();
  });

  it('moves actions between bounded undo and redo stacks', () => {
    const action: Action = {
      type: 'edit_transcript',
      targetId: 'segment-1',
      before: 'Before',
      after: 'After',
      description: 'Edit',
    };
    for (let index = 0; index < 101; index += 1) {
      useHistoryStore.getState().pushAction({ ...action, targetId: `segment-${index}` });
    }
    expect(useHistoryStore.getState().undoStack).toHaveLength(100);
    expect(useHistoryStore.getState().undo()?.targetId).toBe('segment-100');
    expect(useHistoryStore.getState().redo()?.targetId).toBe('segment-100');
    useHistoryStore.getState().clearHistory();
    expect(useHistoryStore.getState().undo()).toBeNull();
    expect(useHistoryStore.getState().redo()).toBeNull();
  });

  it('clamps timeline values and updates selection/playback', () => {
    useTimelineStore.getState().setCurrentTimeSeconds(-5);
    useTimelineStore.getState().setZoomLevel(2);
    expect(useTimelineStore.getState()).toMatchObject({ currentTimeSeconds: 0, zoomLevel: 10 });
    useTimelineStore.getState().setZoomLevel(5000);
    useTimelineStore.getState().setPlaying(true);
    useTimelineStore.getState().setSelectedSegmentId('segment-1');
    expect(useTimelineStore.getState()).toMatchObject({
      zoomLevel: 1000,
      isPlaying: true,
      selectedSegmentId: 'segment-1',
    });
  });

  it('edits, times, splits, merges, duplicates, locks, and deletes transcript segments', () => {
    const first = transcriptSegment();
    const second = transcriptSegment({
      id: 'segment-2',
      original_text: 'Again',
      translated_text: 'Otra vez',
      start_time: 2,
      end_time: 3,
      words: [{ text: 'Again', start_time: 2, end_time: 3, confidence: 0.8 }],
    });
    useTranscriptStore.getState().setSegments([first, second]);
    useTranscriptStore.getState().setSelectedSegmentId(first.id);
    useTranscriptStore.getState().updateSegmentText(first.id, 'original', 'Edited source');
    useTranscriptStore.getState().updateSegmentText(first.id, 'translated', 'Texto');
    useTranscriptStore.getState().updateWordTiming(first.id, 0, 0.2, 0.9);
    useTranscriptStore.getState().setSegmentLock(first.id, true);
    expect(useTranscriptStore.getState().segments[0]).toMatchObject({
      original_text: 'Edited source',
      translated_text: 'Texto',
      start_time: 0.2,
      end_time: 2,
      locked: true,
      edited: true,
    });

    useTranscriptStore.getState().splitSegment(first.id, 1);
    expect(useTranscriptStore.getState().segments.map((item) => item.id))
      .toEqual(['segment-1_s1', 'segment-1_s2', 'segment-2']);
    useTranscriptStore.getState().mergeSegments('segment-1_s1', 'segment-1_s2');
    expect(useTranscriptStore.getState().segments[0]).toMatchObject({
      id: 'segment-1_s1_merged',
      original_text: 'Hello world',
      translated_text: ' ',
    });

    vi.spyOn(Math, 'random').mockReturnValue(0.123456);
    useTranscriptStore.getState().duplicateSegment('segment-2');
    expect(useTranscriptStore.getState().segments).toHaveLength(3);
    useTranscriptStore.getState().deleteSegment('segment-2');
    expect(useTranscriptStore.getState().segments).toHaveLength(2);
  });

  it('ignores invalid transcript operations', () => {
    useTranscriptStore.getState().setSegments([transcriptSegment()]);
    const before = useTranscriptStore.getState().segments;
    useTranscriptStore.getState().splitSegment('missing', 1);
    useTranscriptStore.getState().splitSegment('segment-1', 0);
    useTranscriptStore.getState().mergeSegments('missing', 'segment-1');
    useTranscriptStore.getState().duplicateSegment('missing');
    useTranscriptStore.getState().updateSegmentText('missing', 'original', 'No');
    useTranscriptStore.getState().updateWordTiming('missing', 0, 0, 1);
    expect(useTranscriptStore.getState().segments).toEqual(before);
  });

  it('manages UI tabs, dialogs, notifications, and theme', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.25);
    useUIStore.getState().setActiveTab('translation');
    useUIStore.getState().setExportDialogOpen(true);
    useUIStore.getState().addNotification({ type: 'success', message: 'Saved' });
    const notification = useUIStore.getState().notifications[0];
    expect(notification).toMatchObject({ type: 'success', message: 'Saved' });
    useUIStore.getState().toggleTheme();
    expect(useUIStore.getState().theme).toBe('light');
    useUIStore.getState().toggleTheme();
    useUIStore.getState().removeNotification(notification.id);
    expect(useUIStore.getState()).toMatchObject({
      activeTab: 'translation',
      isExportDialogOpen: true,
      notifications: [],
      theme: 'dark',
    });
  });
});

describe('editor hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMediaStore.setState({ metadata: null, segments: [], isLoading: false });
    useProjectStore.setState({ currentProject: null, projects: [], isLoading: false, error: null });
    useTranslationStore.setState({ translations: {}, targetLanguage: 'es', isLoading: false });
    useTimelineStore.setState({
      currentTimeSeconds: 0,
      isPlaying: false,
      zoomLevel: 100,
      selectedSegmentId: null,
    });
    useTranscriptStore.setState({ segments: [], selectedSegmentId: null });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('serializes project autosaves to IndexedDB', async () => {
    vi.useFakeTimers();
    useProjectStore.setState({ currentProject: projectFixture });
    useMediaStore.setState({
      segments: [{
        id: 'segment-1',
        sequenceOrder: 1,
        startTimeSeconds: 2,
        endTimeSeconds: 7,
        durationSeconds: 5,
        speakerTag: 'Speaker 1',
        text: 'Hello',
        confidence: 1,
      }],
    });
    useTranslationStore.getState().setTranslations([{
      id: 'translation-1',
      transcriptSegmentId: 'segment-1',
      translatedText: 'Hola',
      originalDurationMs: 5000,
      estimatedDurationMs: 5000,
      durationRatio: 1,
      speedAdjustmentFactor: 1,
      qualityScore: 1,
      status: 'completed',
    }]);
    storage.saveDraft.mockResolvedValue(undefined);
    const { unmount } = renderHook(() => useProjectAutoSave());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(storage.saveDraft).toHaveBeenCalledWith(expect.objectContaining({
      projectMetadata: expect.objectContaining({ id: projectFixture.id }),
      mediaReferences: expect.objectContaining({
        durationSeconds: 7,
        videoFilename: 'launch.mp4',
      }),
      translations: [expect.objectContaining({ translatedText: 'Hola' })],
    }));
    unmount();
  });

  it('prefers the canonical sync callback and contains autosave failures', async () => {
    vi.useFakeTimers();
    useProjectStore.setState({ currentProject: projectFixture });
    const syncDraft = vi.fn().mockRejectedValue(new Error('sync failed'));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderHook(() => useProjectAutoSave(syncDraft));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(syncDraft).toHaveBeenCalled();
    expect(storage.saveDraft).not.toHaveBeenCalled();
  });

  it('does not schedule autosave without a current project', () => {
    vi.useFakeTimers();
    renderHook(() => useProjectAutoSave());
    vi.advanceTimersByTime(60_000);
    expect(storage.saveDraft).not.toHaveBeenCalled();
  });

  it('connects processing status updates and disconnects on cleanup', () => {
    let onUpdate!: (value: { status: string; progress_percent: number }) => void;
    let onError!: (error: Event) => void;
    sse.connect.mockImplementation((_id, _type, update, error) => {
      onUpdate = update;
      onError = error;
    });
    const { result, unmount } = renderHook(() => useProcessingStatus('project-1', 'lipsync'));

    act(() => onUpdate({ status: 'processing', progress_percent: 50 }));
    expect(result.current).toEqual({
      status: { status: 'processing', progress_percent: 50 },
      error: null,
    });
    act(() => onError(new Event('error')));
    expect(result.current.error).toContain('auto-reconnect');
    unmount();
    expect(sse.disconnect).toHaveBeenCalledWith('project-1', 'lipsync');
  });

  it('does not connect processing streams without an id', () => {
    renderHook(() => useProcessingStatus(undefined, 'tts'));
    expect(sse.connect).not.toHaveBeenCalled();
  });

  it('moves and resizes timeline segments on a deterministic grid', () => {
    useMediaStore.getState().setSegments([{
      id: 'segment-1',
      sequenceOrder: 1,
      startTimeSeconds: 1,
      endTimeSeconds: 3,
      durationSeconds: 2,
      speakerTag: 'Speaker',
      text: 'Text',
      confidence: 1,
    }]);
    const { result } = renderHook(() => useSegmentManipulation());
    act(() => result.current.selectSegment('segment-1'));
    act(() => result.current.moveSegment('segment-1', 2.13));
    expect(useMediaStore.getState().segments[0]).toMatchObject({
      startTimeSeconds: 2.15,
      endTimeSeconds: 4.15,
    });

    act(() => result.current.resizeSegment('segment-1', 'start', 10));
    expect(useMediaStore.getState().segments[0].durationSeconds).toBeCloseTo(0.2);
    act(() => result.current.resizeSegment('segment-1', 'end', 0));
    expect(useMediaStore.getState().segments[0].durationSeconds).toBeCloseTo(0.2);
  });

  it('exposes timeline conversions and formatting', () => {
    useTimelineStore.setState({ zoomLevel: 200, currentTimeSeconds: 3, selectedSegmentId: 'segment-1' });
    const { result } = renderHook(() => useTimeline());
    expect(result.current.secondsToPixels(2.5)).toBe(500);
    expect(result.current.pixelsToSeconds(500)).toBe(2.5);
    expect(result.current.formatTimecode(3661.25)).toBe('01:01:01.25');
    act(() => result.current.setPlaying(true));
    expect(useTimelineStore.getState().isPlaying).toBe(true);
  });

  it('calculates speaker statistics and batch-renames speakers', () => {
    useTranscriptStore.getState().setSegments([
      transcriptSegment(),
      transcriptSegment({ id: 'segment-2', start_time: 2, end_time: 5 }),
    ]);
    const { result } = renderHook(() => useTranscriptEditor());
    expect(result.current.getSpeakerStatistics()).toEqual({
      'Speaker 1': { lineCount: 2, totalDurationSec: 5 },
    });
    act(() => result.current.renameSpeakerBatch('Speaker 1', 'Host'));
    expect(useTranscriptStore.getState().segments.every((item) => item.speaker === 'Host')).toBe(true);
  });

  it('keeps word timings valid at both boundaries', () => {
    useTranscriptStore.getState().setSegments([transcriptSegment()]);
    const { result } = renderHook(() => useWordTiming());
    act(() => result.current.adjustTimingPrecision('segment-1', 0, 'start_time', 5));
    expect(useTranscriptStore.getState().segments[0].words[0].start_time).toBe(0.79);
    act(() => result.current.adjustTimingPrecision('segment-1', 0, 'end_time', -5));
    expect(useTranscriptStore.getState().segments[0].words[0].end_time).toBe(0.8);
    act(() => result.current.adjustTimingPrecision('missing', 0, 'start_time', 1));
    act(() => result.current.adjustTimingPrecision('segment-1', 99, 'start_time', 1));
  });

  it('undoes and redoes transcript and translation edits', () => {
    useMediaStore.getState().setSegments([{
      id: 'segment-1',
      sequenceOrder: 1,
      startTimeSeconds: 0,
      endTimeSeconds: 1,
      durationSeconds: 1,
      speakerTag: 'Speaker',
      text: 'After',
      confidence: 1,
    }]);
    useTranslationStore.getState().setTranslations([{
      id: 'translation-1',
      transcriptSegmentId: 'segment-1',
      translatedText: 'Después',
      originalDurationMs: 1000,
      estimatedDurationMs: 1000,
      durationRatio: 1,
      speedAdjustmentFactor: 1,
      qualityScore: 1,
      status: 'completed',
    }]);
    const { result, rerender } = renderHook(() => useHistory());
    act(() => result.current.pushHistory({
      type: 'edit_transcript',
      targetId: 'segment-1',
      before: 'Before',
      after: 'After',
      description: 'Edit source',
    }));
    rerender();
    act(() => result.current.undo());
    expect(useMediaStore.getState().segments[0].text).toBe('Before');
    rerender();
    act(() => result.current.redo());
    expect(useMediaStore.getState().segments[0].text).toBe('After');

    act(() => result.current.pushHistory({
      type: 'edit_translation',
      targetId: 'segment-1',
      before: 'Antes',
      after: 'Después',
      description: 'Edit translation',
    }));
    rerender();
    act(() => result.current.undo());
    expect(useTranslationStore.getState().translations['segment-1'].translatedText).toBe('Antes');
  });

  it('queues and confirms a manual translation override', () => {
    useTranscriptStore.getState().setSegments([transcriptSegment()]);
    const { result } = renderHook(() => useReTranslation());
    act(() => result.current.queueManualOverride('segment-1', 'Manual text'));
    expect(result.current.showOverrideConfirm).toBe(true);
    act(() => result.current.confirmOverride());
    expect(useTranscriptStore.getState().segments[0].translated_text).toBe('Manual text');
    expect(result.current.showOverrideConfirm).toBe(false);
  });

  it('simulates retranslation and clears its loading state', async () => {
    vi.useFakeTimers();
    useTranscriptStore.getState().setSegments([transcriptSegment()]);
    const { result } = renderHook(() => useReTranslation());
    let request!: Promise<void>;
    act(() => {
      request = result.current.requestReTranslation('segment-1', 'Hello world', 'es');
    });
    expect(result.current.isTranslating).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
      await request;
    });
    expect(useTranscriptStore.getState().segments[0].translated_text).toBe('[Translated] Hello world');
    expect(result.current.isTranslating).toBe(false);
  });

  it('toggles playback and steps within media bounds', () => {
    useTimelineStore.setState({ currentTimeSeconds: 0.02, isPlaying: false });
    const { result, rerender } = renderHook(() => usePlayback(1));
    act(() => result.current.stepFrames('backward'));
    expect(useTimelineStore.getState().currentTimeSeconds).toBe(0);
    act(() => result.current.stepFrames('forward', 5));
    expect(useTimelineStore.getState().currentTimeSeconds).toBe(1);
    act(() => result.current.togglePlay());
    rerender();
    expect(result.current.isPlaying).toBe(true);

    const input = document.createElement('input');
    input.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }));
    expect(useTimelineStore.getState().isPlaying).toBe(true);
  });
});
