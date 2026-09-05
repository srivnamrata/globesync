import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMediaStore, type TranscriptSegment } from '../store/mediaStore';
import { useProjectStore, type Project } from '../store/projectStore';
import { useTranslationStore, type TranslatedSegment } from '../store/translationStore';

const project = (overrides: Partial<Project> = {}): Project => ({
  id: 'project-1',
  name: 'Launch',
  sourceLanguage: 'en',
  targetLanguage: 'es',
  status: 'draft',
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
  ...overrides,
});

const segment = (overrides: Partial<TranscriptSegment> = {}): TranscriptSegment => ({
  id: 'segment-1',
  sequenceOrder: 1,
  startTimeSeconds: 0,
  endTimeSeconds: 4,
  durationSeconds: 4,
  speakerTag: 'Speaker 1',
  text: 'Hello world',
  confidence: 0.98,
  ...overrides,
});

const translation = (overrides: Partial<TranslatedSegment> = {}): TranslatedSegment => ({
  id: 'translation-1',
  transcriptSegmentId: 'segment-1',
  translatedText: 'Hola mundo',
  originalDurationMs: 4000,
  estimatedDurationMs: 4200,
  durationRatio: 1.05,
  speedAdjustmentFactor: 1.05,
  qualityScore: 0.95,
  status: 'completed',
  ...overrides,
});

describe('project store', () => {
  beforeEach(() => {
    useProjectStore.setState({ currentProject: null, projects: [], isLoading: false, error: null });
  });

  it('selects, inserts, replaces, and clears the current project', () => {
    const first = project();
    useProjectStore.getState().setCurrentProject(first);
    expect(useProjectStore.getState()).toMatchObject({
      currentProject: first,
      projects: [first],
    });

    const renamed = project({ name: 'Renamed' });
    useProjectStore.getState().setCurrentProject(renamed);
    expect(useProjectStore.getState().projects).toEqual([renamed]);

    useProjectStore.getState().setCurrentProject(null);
    expect(useProjectStore.getState().currentProject).toBeNull();
  });

  it('manages project collections, status, loading, and errors', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-04T05:06:07.000Z'));
    const first = project();
    const second = project({ id: 'project-2', name: 'Second' });

    useProjectStore.getState().setProjects([first]);
    useProjectStore.getState().setCurrentProject(first);
    useProjectStore.getState().addProject(second);
    useProjectStore.getState().updateProjectStatus(first.id, 'completed');
    useProjectStore.getState().setLoading(true);
    useProjectStore.getState().setError('Network unavailable');

    expect(useProjectStore.getState().projects).toEqual([
      second,
      expect.objectContaining({
        id: first.id,
        status: 'completed',
        updatedAt: '2026-03-04T05:06:07.000Z',
      }),
    ]);
    expect(useProjectStore.getState().currentProject).toMatchObject({ status: 'completed' });
    expect(useProjectStore.getState()).toMatchObject({
      isLoading: true,
      error: 'Network unavailable',
    });
    vi.useRealTimers();
  });

  it('does not alter the current project for an unrelated status update', () => {
    const first = project();
    useProjectStore.setState({ currentProject: first, projects: [first] });

    useProjectStore.getState().updateProjectStatus('missing', 'failed');

    expect(useProjectStore.getState().currentProject).toBe(first);
    expect(useProjectStore.getState().projects).toEqual([first]);
  });
});

describe('media store', () => {
  beforeEach(() => {
    useMediaStore.setState({ metadata: null, segments: [], isLoading: false });
  });

  it('sorts segments without losing edits and stores metadata/loading', () => {
    const later = segment({ id: 'later', sequenceOrder: 2 });
    const earlier = segment({ id: 'earlier', sequenceOrder: 1 });
    useMediaStore.getState().setSegments([later, earlier]);
    useMediaStore.getState().updateSegmentText('earlier', 'Updated');
    useMediaStore.getState().setMetadata({
      width: 1920,
      height: 1080,
      fps: 30,
      durationSeconds: 4,
      filename: 'video.mp4',
      filesizeBytes: 1024,
    });
    useMediaStore.getState().setLoading(true);

    expect(useMediaStore.getState().segments.map((item) => item.id)).toEqual(['earlier', 'later']);
    expect(useMediaStore.getState().segments[0].text).toBe('Updated');
    expect(useMediaStore.getState()).toMatchObject({
      isLoading: true,
      metadata: { filename: 'video.mp4' },
    });
  });

  it('splits a segment and renumbers following segments', () => {
    useMediaStore.getState().setSegments([
      segment(),
      segment({ id: 'segment-2', sequenceOrder: 2, startTimeSeconds: 4, endTimeSeconds: 6 }),
    ]);

    useMediaStore.getState().splitSegment('segment-1', 1.5, 'Hello', 'world');

    expect(useMediaStore.getState().segments).toEqual([
      expect.objectContaining({
        id: 'segment-1_split1',
        text: 'Hello',
        endTimeSeconds: 1.5,
        durationSeconds: 1.5,
      }),
      expect.objectContaining({
        id: 'segment-1_split2',
        text: 'world',
        startTimeSeconds: 1.5,
        durationSeconds: 2.5,
        sequenceOrder: 2,
      }),
      expect.objectContaining({ id: 'segment-2', sequenceOrder: 3 }),
    ]);
  });

  it('ignores edits and splits for unknown segment ids', () => {
    const original = segment();
    useMediaStore.getState().setSegments([original]);
    useMediaStore.getState().updateSegmentText('missing', 'No change');
    useMediaStore.getState().splitSegment('missing', 1, 'a', 'b');
    expect(useMediaStore.getState().segments).toEqual([original]);
  });
});

describe('translation store', () => {
  beforeEach(() => {
    useTranslationStore.setState({ translations: {}, targetLanguage: 'es', isLoading: false });
  });

  it('indexes translations by transcript segment and updates active text', () => {
    const first = translation();
    const second = translation({ id: 'translation-2', transcriptSegmentId: 'segment-2' });
    useTranslationStore.getState().setTranslations([first, second]);
    useTranslationStore.getState().updateTranslationText('segment-1', 'Texto editado');

    expect(useTranslationStore.getState().translations).toEqual({
      'segment-1': { ...first, translatedText: 'Texto editado' },
      'segment-2': second,
    });
  });

  it('updates language/loading and ignores unknown segments', () => {
    useTranslationStore.getState().setTranslations([translation()]);
    const before = useTranslationStore.getState().translations;
    useTranslationStore.getState().updateTranslationText('missing', 'ignored');
    useTranslationStore.getState().setTargetLanguage('fr');
    useTranslationStore.getState().setLoading(true);

    expect(useTranslationStore.getState()).toMatchObject({
      translations: before,
      targetLanguage: 'fr',
      isLoading: true,
    });
  });
});
