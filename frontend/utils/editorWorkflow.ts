import type { ProjectDraftConflictErrorDetail } from '../services/projectService';
import type { HeygenXFile } from '../services/storageService';
import type { Project } from '../store/projectStore';
import type { TranslatedSegment } from '../store/translationStore';

export const mergeDraftWithProject = (
  draft: HeygenXFile,
  project?: Project | null,
): HeygenXFile => ({
  ...draft,
  projectMetadata: {
    ...draft.projectMetadata,
    id: project?.id ?? draft.projectMetadata.id,
    name: project?.name ?? draft.projectMetadata.name,
    sourceLanguage: project?.sourceLanguage ?? draft.projectMetadata.sourceLanguage,
    targetLanguage: project?.targetLanguage ?? draft.projectMetadata.targetLanguage,
    createdAt: project?.createdAt ?? draft.projectMetadata.createdAt,
    updatedAt: project?.updatedAt ?? draft.projectMetadata.updatedAt,
  },
  mediaReferences: {
    ...draft.mediaReferences,
    transcriptId: project?.transcriptId ?? draft.mediaReferences.transcriptId,
    mediaId: project?.mediaId ?? draft.mediaReferences.mediaId,
    videoFilename: project?.mediaFilename ?? draft.mediaReferences.videoFilename,
  },
});

export function buildProjectFromDraft(
  draft: HeygenXFile,
  project?: Project | null,
): Project {
  return {
    id: project?.id ?? draft.projectMetadata.id,
    name: project?.name ?? draft.projectMetadata.name,
    sourceLanguage: project?.sourceLanguage ?? draft.projectMetadata.sourceLanguage,
    targetLanguage: project?.targetLanguage ?? draft.projectMetadata.targetLanguage,
    status: project?.status ?? 'draft',
    createdAt: project?.createdAt ?? draft.projectMetadata.createdAt,
    updatedAt: project?.updatedAt ?? draft.projectMetadata.updatedAt,
    transcriptId: project?.transcriptId ?? draft.mediaReferences.transcriptId,
    mediaId: project?.mediaId ?? draft.mediaReferences.mediaId,
    mediaFilename: project?.mediaFilename ?? draft.mediaReferences.videoFilename,
    currentLipsyncJobId: project?.currentLipsyncJobId,
    lastRenderedVideoPath: project?.lastRenderedVideoPath,
  };
}

export function toPersistableFilename(value?: string): string {
  if (!value) return 'source_video.mp4';
  try {
    const url = new URL(value);
    const filename = url.pathname.split('/').filter(Boolean).pop();
    return filename || 'source_video.mp4';
  } catch {
    return value;
  }
}

export function sanitizeDraftArtifactReferences(draft: HeygenXFile): HeygenXFile {
  return {
    ...draft,
    mediaReferences: {
      ...draft.mediaReferences,
      videoFilename: toPersistableFilename(draft.mediaReferences.videoFilename),
    },
  };
}

export function buildDraftSaveOptions(
  version: number | null,
  baseProjectUpdatedAt: string | null,
  baseProjectUpdatedAtOverride?: string | null,
  checkpointReason?: string,
) {
  return {
    version: version ?? 1,
    baseProjectUpdatedAt: baseProjectUpdatedAtOverride ?? baseProjectUpdatedAt,
    ...(checkpointReason ? { checkpointReason } : {}),
  };
}

type DraftSaveResult = {
  version: number;
  base_project_updated_at?: string | null;
};

export type DraftSaveOutcome =
  | { status: 'remote'; version: number; baseProjectUpdatedAt: string | null }
  | { status: 'conflict'; detail: ProjectDraftConflictErrorDetail }
  | { status: 'local' };

export async function saveDraftWithRecovery({
  draft,
  hasProjectApiScope,
  hasActiveConflict,
  saveRemote,
  saveLocal,
  getConflictDetail,
  onRemoteError = (error) => console.warn(
    'Failed to persist project draft to backend; kept local IndexedDB draft as fallback:',
    error,
  ),
}: {
  draft: HeygenXFile;
  hasProjectApiScope: boolean;
  hasActiveConflict: boolean;
  saveRemote: () => Promise<DraftSaveResult>;
  saveLocal: (draft: HeygenXFile) => Promise<void>;
  getConflictDetail: (error: unknown) => ProjectDraftConflictErrorDetail | null;
  onRemoteError?: (error: unknown) => void;
}): Promise<DraftSaveOutcome> {
  if (hasProjectApiScope && !hasActiveConflict) {
    try {
      const remoteDraft = await saveRemote();
      await saveLocal(draft);
      return {
        status: 'remote',
        version: remoteDraft.version,
        baseProjectUpdatedAt: remoteDraft.base_project_updated_at ?? null,
      };
    } catch (error) {
      const detail = getConflictDetail(error);
      if (detail) {
        await saveLocal(draft);
        return { status: 'conflict', detail };
      }
      onRemoteError(error);
    }
  }

  await saveLocal(draft);
  return { status: 'local' };
}

export async function enqueueSerialized(
  queue: { current: Promise<void> },
  task: () => Promise<void>,
): Promise<void> {
  const queuedTask = queue.current.then(task, task);
  queue.current = queuedTask.then(
    () => undefined,
    () => undefined,
  );
  await queuedTask;
}

export async function pollForTranslations({
  transcriptId,
  targetLanguage,
  expectedCount,
  fetchTranslations,
  delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
  maxAttempts = 40,
  intervalMs = 3000,
  onAttemptError = (error) => console.warn('Translation polling attempt failed:', error),
}: {
  transcriptId: string;
  targetLanguage: string;
  expectedCount: number;
  fetchTranslations: (transcriptId: string, targetLanguage: string) => Promise<TranslatedSegment[]>;
  delay?: (milliseconds: number) => Promise<void>;
  maxAttempts?: number;
  intervalMs?: number;
  onAttemptError?: (error: unknown) => void;
}): Promise<TranslatedSegment[]> {
  let latestTranslations: TranslatedSegment[] = [];

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const fetchedTranslations = await fetchTranslations(transcriptId, targetLanguage);
      if (fetchedTranslations.length > 0) {
        latestTranslations = fetchedTranslations;
      }
      if (fetchedTranslations.length >= expectedCount) {
        return fetchedTranslations;
      }
    } catch (error) {
      onAttemptError(error);
    }

    if (attempt < maxAttempts - 1) {
      await delay(intervalMs);
    }
  }

  return latestTranslations;
}

export function formatTranslationCompletionMessage(
  fetchedCount: number,
  expectedCount: number,
): string {
  if (fetchedCount === 0) {
    return 'Translation was queued, but no translated segments were available yet. Please retry in a few moments.';
  }
  if (fetchedCount >= expectedCount) {
    return `Translation complete — ${fetchedCount} segments loaded.`;
  }
  return `Translation is still running — ${fetchedCount} of ${expectedCount} segments are available.`;
}
