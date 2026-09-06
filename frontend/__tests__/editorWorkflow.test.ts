import { describe, expect, it, vi } from 'vitest';
import type { ProjectDraftConflictErrorDetail } from '../services/projectService';
import {
  buildDraftSaveOptions,
  buildProjectFromDraft,
  enqueueSerialized,
  formatTranslationCompletionMessage,
  mergeDraftWithProject,
  pollForTranslations,
  sanitizeDraftArtifactReferences,
  saveDraftWithRecovery,
  toPersistableFilename,
} from '../utils/editorWorkflow';
import { draftFixture, projectFixture } from '../test/fixtures';
import type { TranslatedSegment } from '../store/translationStore';

const translation = (id: string): TranslatedSegment => ({
  id: `translation-${id}`,
  transcriptSegmentId: id,
  translatedText: `Translated ${id}`,
  originalDurationMs: 1000,
  estimatedDurationMs: 1000,
  durationRatio: 1,
  speedAdjustmentFactor: 1,
  qualityScore: 1,
  status: 'completed',
});

const conflict: ProjectDraftConflictErrorDetail = {
  code: 'DRAFT_VERSION_CONFLICT',
  message: 'A newer draft exists.',
  project_id: projectFixture.id,
  client_version: 2,
  server_version: 3,
  server_updated_at: '2026-02-01T00:00:00.000Z',
  last_saved_by_user_id: 'user-2',
};

describe('editor draft mapping', () => {
  it('merges canonical project fields without losing draft contents', () => {
    const merged = mergeDraftWithProject(draftFixture, {
      ...projectFixture,
      id: 'canonical-project',
      name: 'Canonical name',
      mediaId: 'canonical-media',
    });

    expect(merged).toEqual(expect.objectContaining({
      version: draftFixture.version,
      translations: draftFixture.translations,
      projectMetadata: expect.objectContaining({
        id: 'canonical-project',
        name: 'Canonical name',
      }),
      mediaReferences: expect.objectContaining({
        mediaId: 'canonical-media',
        transcriptId: projectFixture.transcriptId,
      }),
    }));
    expect(mergeDraftWithProject(draftFixture)).toEqual(draftFixture);
  });

  it('hydrates projects from a draft with optional canonical overrides', () => {
    expect(buildProjectFromDraft(draftFixture)).toEqual(expect.objectContaining({
      id: projectFixture.id,
      status: 'draft',
      mediaFilename: 'launch.mp4',
    }));
    expect(buildProjectFromDraft(draftFixture, {
      ...projectFixture,
      status: 'processing',
      currentLipsyncJobId: 'job-1',
    })).toEqual(expect.objectContaining({
      status: 'processing',
      currentLipsyncJobId: 'job-1',
    }));
  });

  it('keeps only persistable artifact filenames', () => {
    expect(toPersistableFilename()).toBe('source_video.mp4');
    expect(toPersistableFilename('plain.mp4')).toBe('plain.mp4');
    expect(toPersistableFilename('https://storage.test/folder/video.mp4?token=secret'))
      .toBe('video.mp4');
    expect(toPersistableFilename('https://storage.test/')).toBe('source_video.mp4');
    expect(sanitizeDraftArtifactReferences({
      ...draftFixture,
      mediaReferences: {
        ...draftFixture.mediaReferences,
        videoFilename: 'https://storage.test/private/clip.webm?signed=true',
      },
    }).mediaReferences.videoFilename).toBe('clip.webm');
  });

  it('uses the freshly persisted project timestamp for first-translation saves', () => {
    expect(buildDraftSaveOptions(
      null,
      '2026-01-01T00:00:00.000Z',
      '2026-01-02T00:00:00.000Z',
      'translation-complete',
    )).toEqual({
      version: 1,
      baseProjectUpdatedAt: '2026-01-02T00:00:00.000Z',
      checkpointReason: 'translation-complete',
    });
    expect(buildDraftSaveOptions(4, '2026-01-01T00:00:00.000Z')).toEqual({
      version: 4,
      baseProjectUpdatedAt: '2026-01-01T00:00:00.000Z',
    });
  });
});

describe('draft persistence outcomes', () => {
  it('persists remotely then locally and returns the next version', async () => {
    const order: string[] = [];
    const saveRemote = vi.fn(async () => {
      order.push('remote');
      return { version: 4, base_project_updated_at: '2026-02-01T00:00:00.000Z' };
    });
    const saveLocal = vi.fn(async () => {
      order.push('local');
    });

    await expect(saveDraftWithRecovery({
      draft: draftFixture,
      hasProjectApiScope: true,
      hasActiveConflict: false,
      saveRemote,
      saveLocal,
      getConflictDetail: () => null,
    })).resolves.toEqual({
      status: 'remote',
      version: 4,
      baseProjectUpdatedAt: '2026-02-01T00:00:00.000Z',
    });
    expect(order).toEqual(['remote', 'local']);
  });

  it('preserves editor edits locally after a genuine version conflict', async () => {
    const error = new Error('conflict');
    const saveLocal = vi.fn().mockResolvedValue(undefined);

    await expect(saveDraftWithRecovery({
      draft: draftFixture,
      hasProjectApiScope: true,
      hasActiveConflict: false,
      saveRemote: vi.fn().mockRejectedValue(error),
      saveLocal,
      getConflictDetail: (candidate) => candidate === error ? conflict : null,
    })).resolves.toEqual({ status: 'conflict', detail: conflict });
    expect(saveLocal).toHaveBeenCalledWith(draftFixture);
  });

  it('falls back locally on non-conflict remote errors without hiding the failure', async () => {
    const error = new Error('network unavailable');
    const onRemoteError = vi.fn();
    const saveLocal = vi.fn().mockResolvedValue(undefined);

    await expect(saveDraftWithRecovery({
      draft: draftFixture,
      hasProjectApiScope: true,
      hasActiveConflict: false,
      saveRemote: vi.fn().mockRejectedValue(error),
      saveLocal,
      getConflictDetail: () => null,
      onRemoteError,
    })).resolves.toEqual({ status: 'local' });
    expect(onRemoteError).toHaveBeenCalledWith(error);
    expect(saveLocal).toHaveBeenCalled();
  });

  it('pauses remote saves while a conflict is active', async () => {
    const saveRemote = vi.fn();
    const saveLocal = vi.fn().mockResolvedValue(undefined);

    await expect(saveDraftWithRecovery({
      draft: draftFixture,
      hasProjectApiScope: true,
      hasActiveConflict: true,
      saveRemote,
      saveLocal,
      getConflictDetail: () => null,
    })).resolves.toEqual({ status: 'local' });
    expect(saveRemote).not.toHaveBeenCalled();
  });

  it('serializes autosaves even when an earlier save fails', async () => {
    const queue = { current: Promise.resolve() };
    const execution: string[] = [];
    let releaseFirst!: () => void;
    const first = enqueueSerialized(queue, () => new Promise<void>((_resolve, reject) => {
      execution.push('first-start');
      releaseFirst = () => {
        execution.push('first-end');
        reject(new Error('first failed'));
      };
    }));
    const second = enqueueSerialized(queue, async () => {
      execution.push('second');
    });

    await vi.waitFor(() => expect(execution).toEqual(['first-start']));
    releaseFirst();
    await expect(first).rejects.toThrow('first failed');
    await expect(second).resolves.toBeUndefined();
    expect(execution).toEqual(['first-start', 'first-end', 'second']);
  });
});

describe('translation polling', () => {
  it('returns immediately when all expected translations arrive', async () => {
    const fetchTranslations = vi.fn().mockResolvedValue([
      translation('segment-1'),
      translation('segment-2'),
    ]);
    const delay = vi.fn();

    await expect(pollForTranslations({
      transcriptId: 'transcript-1',
      targetLanguage: 'es',
      expectedCount: 2,
      fetchTranslations,
      delay,
    })).resolves.toHaveLength(2);
    expect(delay).not.toHaveBeenCalled();
  });

  it('continues through transient errors and returns the latest partial result', async () => {
    const fetchTranslations = vi.fn()
      .mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValueOnce([translation('segment-1')])
      .mockResolvedValueOnce([]);
    const delay = vi.fn().mockResolvedValue(undefined);
    const onAttemptError = vi.fn();

    await expect(pollForTranslations({
      transcriptId: 'transcript-1',
      targetLanguage: 'es',
      expectedCount: 2,
      fetchTranslations,
      delay,
      maxAttempts: 3,
      intervalMs: 5,
      onAttemptError,
    })).resolves.toEqual([translation('segment-1')]);
    expect(onAttemptError).toHaveBeenCalledWith(expect.any(Error));
    expect(delay).toHaveBeenCalledTimes(2);
    expect(delay).toHaveBeenCalledWith(5);
  });

  it('returns an empty result after bounded polling', async () => {
    await expect(pollForTranslations({
      transcriptId: 'transcript-1',
      targetLanguage: 'fr',
      expectedCount: 1,
      fetchTranslations: vi.fn().mockResolvedValue([]),
      delay: vi.fn().mockResolvedValue(undefined),
      maxAttempts: 2,
    })).resolves.toEqual([]);
  });

  it('describes complete, partial, and unavailable translation results', () => {
    expect(formatTranslationCompletionMessage(2, 2))
      .toBe('Translation complete — 2 segments loaded.');
    expect(formatTranslationCompletionMessage(1, 2))
      .toBe('Translation is still running — 1 of 2 segments are available.');
    expect(formatTranslationCompletionMessage(0, 2))
      .toContain('no translated segments');
  });
});
