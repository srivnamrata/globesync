 import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import type { TranscriptSegment } from '../store/mediaStore';
import type { Project } from '../store/projectStore';
import type { TranslatedSegment } from '../store/translationStore';
import { storageService, type HeygenXFile } from '../services/storageService';
import { ApiError } from '../services/apiClient';
import {
  getProjectDraftConflictDetail,
  projectService,
  type PipelineOperationStatus,
} from '../services/projectService';
import { mapUserFacingError } from '../services/userFacingErrors';
import {
  buildDraftSaveOptions,
  buildProjectFromDraft,
  enqueueSerialized,
  mergeDraftWithProject,
  sanitizeDraftArtifactReferences,
  saveDraftWithRecovery,
} from '../utils/editorWorkflow';

type UploadState = 'idle' | 'uploading' | 'transcribing' | 'translating';

type ApplyProjectPatchOptions = {
  name?: string;
  sourceLanguage?: string;
  targetLanguage?: string;
  status?: Project['status'];
  transcriptId?: string;
  mediaId?: string;
};

type PersistDraftOptions = {
  projectOverride?: Project | null;
  segmentsOverride?: TranscriptSegment[];
  translationsOverride?: TranslatedSegment[];
  videoFilename?: string;
  durationSeconds?: number;
  transcriptId?: string;
  mediaId?: string;
  baseProjectUpdatedAtOverride?: string | null;
  checkpointReason?: string;
};

type UseEditorProjectDataOptions = {
  projectId: string;
  currentProject: Project | null;
  segments: TranscriptSegment[];
  translations: Record<string, TranslatedSegment>;
  setCurrentProject: (project: Project) => void;
  setSegments: (segments: TranscriptSegment[]) => void;
  setTranslations: (translations: TranslatedSegment[]) => void;
  setOriginalTranslations: (translations: Record<string, string>) => void;
  setDirtySegments: Dispatch<SetStateAction<Set<string>>>;
  setUploadMessage: (message: string | null) => void;
  setUploadState: (state: UploadState) => void;
  onRedirectHome: () => void;
  onReplaceProject: (projectId: string) => void;
};

export function useEditorProjectData({
  projectId,
  currentProject,
  segments,
  translations,
  setCurrentProject,
  setSegments,
  setTranslations,
  setOriginalTranslations,
  setDirtySegments,
  setUploadMessage,
  setUploadState,
  onRedirectHome,
  onReplaceProject,
}: UseEditorProjectDataOptions) {
  const [sourceMediaUrl, setSourceMediaUrl] = useState<string | null>(null);
  const [renderedVideoUrl, setRenderedVideoUrl] = useState<string | null>(null);
  const [hasRemoteDraftConflict, setHasRemoteDraftConflict] = useState(false);
  const [isReloadingProject, setIsReloadingProject] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [pipelineOperation, setPipelineOperation] = useState<PipelineOperationStatus | null>(null);
  const remoteDraftVersionRef = useRef<number | null>(null);
  const remoteDraftConflictRef = useRef(false);
  const draftSaveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const [baseProjectUpdatedAt, setBaseProjectUpdatedAt] = useState<string | null>(null);

  const dismissRemoteDraftConflict = useCallback(() => {
    remoteDraftConflictRef.current = false;
    setHasRemoteDraftConflict(false);
  }, []);

  const ensureCanonicalProjectForWrite = useCallback(async (): Promise<Project | null> => {
    if (!currentProject || !projectService.hasProjectApiScope()) {
      return currentProject;
    }

    try {
      await projectService.bootstrapAuthContext();
      return await projectService.getProject(currentProject.id);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) {
        throw error;
      }

      const localDraft = mergeDraftWithProject(
        {
          version: '1.2.0',
          projectMetadata: {
            id: currentProject.id,
            name: currentProject.name,
            sourceLanguage: currentProject.sourceLanguage,
            targetLanguage: currentProject.targetLanguage,
            createdAt: currentProject.createdAt,
            updatedAt: currentProject.updatedAt,
          },
          mediaReferences: {
            ...(currentProject.mediaFilename ? { videoFilename: currentProject.mediaFilename } : {}),
            durationSeconds: segments.reduce((acc, segment) => Math.max(acc, segment.endTimeSeconds), 0),
            originalTranscriptSegments: segments,
            transcriptId: currentProject.transcriptId,
            mediaId: currentProject.mediaId,
          },
          translations: Object.values(translations),
          timelineState: undefined,
        },
        currentProject,
      );

      const canonicalProject = await projectService.createProjectShell(
        currentProject.name,
        currentProject.sourceLanguage,
        currentProject.targetLanguage,
      );
      const canonicalDraft = mergeDraftWithProject(localDraft, canonicalProject);
      const seededDraft = await projectService.saveProjectDraft(canonicalProject.id, canonicalDraft, {
        version: 1,
        baseProjectUpdatedAt: canonicalProject.updatedAt,
      });
      const hydratedProject = buildProjectFromDraft(canonicalDraft, canonicalProject);

      if (currentProject.transcriptId || currentProject.mediaId) {
        const patchedProject = await projectService.updateProject(canonicalProject.id, {
          ...(currentProject.transcriptId ? { transcriptId: currentProject.transcriptId } : {}),
          ...(currentProject.mediaId ? { mediaId: currentProject.mediaId } : {}),
        });
        hydratedProject.transcriptId = patchedProject.transcriptId;
        hydratedProject.mediaId = patchedProject.mediaId;
        hydratedProject.updatedAt = patchedProject.updatedAt;
      }

      const finalDraft = mergeDraftWithProject(canonicalDraft, hydratedProject);

      setCurrentProject(hydratedProject);
      remoteDraftVersionRef.current = seededDraft.version;
      setBaseProjectUpdatedAt(seededDraft.base_project_updated_at ?? hydratedProject.updatedAt);
      remoteDraftConflictRef.current = false;
      setHasRemoteDraftConflict(false);
      await storageService.saveDraft(finalDraft);
      if (currentProject.id !== canonicalProject.id) {
        await storageService.deleteDraft(currentProject.id);
        onReplaceProject(canonicalProject.id);
      }
      setUploadMessage('This project was restored into your cloud workspace so uploads and transcription can continue.');
      return hydratedProject;
    }
  }, [currentProject, onReplaceProject, segments, setCurrentProject, setUploadMessage, translations]);

  const loadProjectData = useCallback(async () => {
    if (!projectId) {
      return;
    }

    setIsReloadingProject(true);
    setSourceMediaUrl(null);
    setRenderedVideoUrl(null);
    try {
      let draft: HeygenXFile | null = null;
      let backendProject: Project | null = null;
      let nextPipelineOperation: PipelineOperationStatus | null = null;
      let nextBaseProjectUpdatedAt: string | null = null;

      if (projectService.hasProjectApiScope()) {
        try {
          await projectService.bootstrapAuthContext();
          backendProject = await projectService.getProject(projectId);
          nextPipelineOperation = backendProject.currentPipelineOperationId === null
            ? null
            : await projectService.getPipelineOperation(projectId).catch(() => null);
          setPipelineOperation(nextPipelineOperation);
          if (backendProject.mediaId) {
            const media = await projectService.getMedia(backendProject.mediaId);
            backendProject = {
              ...backendProject,
              mediaFilename: media.filename,
              mediaDurationSeconds: media.duration_seconds,
            };
            setSourceMediaUrl(media.media_url ?? null);
          }
          if (backendProject.currentLipsyncJobId) {
            const job = await projectService.getExportStatus(backendProject.currentLipsyncJobId).catch(() => null);
            if (job?.output_video_url) {
              setRenderedVideoUrl(job.output_video_url);
            }
          }
          nextBaseProjectUpdatedAt = backendProject.updatedAt;

          try {
            const remoteDraft = await projectService.getProjectDraft(projectId);
            draft = mergeDraftWithProject(remoteDraft.draft, backendProject);
            remoteDraftVersionRef.current = remoteDraft.version;
            nextBaseProjectUpdatedAt = remoteDraft.baseProjectUpdatedAt ?? backendProject.updatedAt;
          } catch (draftError) {
            draft = projectService.buildLocalDraftFromProject(backendProject);
            remoteDraftVersionRef.current = null;
            nextBaseProjectUpdatedAt = backendProject.updatedAt;
            console.warn('No server-side draft found yet, seeding canonical draft from project metadata:', draftError);

            try {
              const seededDraft = await projectService.seedProjectDraft(backendProject);
              remoteDraftVersionRef.current = seededDraft.version;
              nextBaseProjectUpdatedAt = seededDraft.base_project_updated_at ?? backendProject.updatedAt;
            } catch (seedError) {
              console.warn('Failed to seed canonical backend draft; keeping local fallback cache:', seedError);
            }
          }
        } catch (projectError) {
          console.warn('Failed to load project from backend, falling back to local IndexedDB draft:', projectError);
        }
      }

      if (!draft) {
        draft = await storageService.getDraft(projectId);
      }

      if (!draft) {
        onRedirectHome();
        return;
      }

      draft = sanitizeDraftArtifactReferences(draft);
      await storageService.saveDraft(draft);

      const hydratedProject = buildProjectFromDraft(draft, backendProject);

      setCurrentProject(hydratedProject);
      remoteDraftConflictRef.current = false;
      setHasRemoteDraftConflict(false);
      setUploadMessage(
        nextPipelineOperation && nextPipelineOperation.status !== 'completed'
          ? nextPipelineOperation.error_message || nextPipelineOperation.message
          : null,
      );
      if (nextPipelineOperation?.operation_type === 'transcription' && nextPipelineOperation.status === 'in_progress') {
        setUploadState('transcribing');
      } else if (nextPipelineOperation?.operation_type === 'translation' && nextPipelineOperation.status === 'in_progress') {
        setUploadState('translating');
      } else if (!nextPipelineOperation || nextPipelineOperation.status === 'completed' || nextPipelineOperation.status === 'failed') {
        setUploadState('idle');
      }
      setBaseProjectUpdatedAt(nextBaseProjectUpdatedAt ?? hydratedProject.updatedAt);

      const draftSegments = draft.mediaReferences.originalTranscriptSegments || [];
      const draftTranslations = draft.translations || [];

      setSegments(draftSegments);

      let resolvedTranslations = draftTranslations;

      if (draft.mediaReferences.transcriptId && draftSegments.length > 0) {
        try {
          const fetchedTranslations = await projectService.fetchTranslations(
            draft.mediaReferences.transcriptId,
            hydratedProject.targetLanguage,
          );

          if (fetchedTranslations.length > 0) {
            resolvedTranslations = fetchedTranslations;
            await storageService.saveDraft({
              ...draft,
              translations: fetchedTranslations,
            });
          }
        } catch (translationErr) {
          console.warn('Could not fetch translations from API; using draft copy if available:', translationErr);
        }
      }

      if (resolvedTranslations.length > 0) {
        setTranslations(resolvedTranslations);
        const snapshot: Record<string, string> = {};
        resolvedTranslations.forEach((translation) => {
          snapshot[translation.transcriptSegmentId] = translation.translatedText;
        });
        setOriginalTranslations(snapshot);
      } else {
        setTranslations([]);
        setOriginalTranslations({});
      }
    } catch (err) {
      console.error('Failed to load project draft in editor:', err);
    } finally {
      setIsReloadingProject(false);
    }
  }, [
    onRedirectHome,
    projectId,
    setCurrentProject,
    setOriginalTranslations,
    setSegments,
    setTranslations,
    setUploadMessage,
    setUploadState,
  ]);

  useEffect(() => {
    void loadProjectData();
  }, [loadProjectData]);

  const persistDraft = useCallback(async ({
    projectOverride,
    segmentsOverride,
    translationsOverride,
    videoFilename,
    durationSeconds,
    transcriptId,
    mediaId,
    baseProjectUpdatedAtOverride,
    checkpointReason,
  }: PersistDraftOptions = {}) => {
    const project = projectOverride ?? currentProject;
    if (!project) {
      return;
    }

    const nextDraft: HeygenXFile = {
      version: '1.2.0',
      projectMetadata: {
        id: project.id,
        name: project.name,
        sourceLanguage: project.sourceLanguage,
        targetLanguage: project.targetLanguage,
        createdAt: project.createdAt,
        updatedAt: new Date().toISOString(),
      },
      mediaReferences: {
        ...((videoFilename ?? project.mediaFilename)
          ? { videoFilename: videoFilename ?? project.mediaFilename }
          : {}),
        durationSeconds:
          durationSeconds ??
          (segmentsOverride ?? segments).reduce((acc, segment) => Math.max(acc, segment.endTimeSeconds), 0),
        originalTranscriptSegments: segmentsOverride ?? segments,
        transcriptId: transcriptId ?? project.transcriptId,
        mediaId: mediaId ?? project.mediaId,
      },
      translations: translationsOverride ?? Object.values(translations),
    };

    const saveDraft = async () => {
      const outcome = await saveDraftWithRecovery({
        draft: nextDraft,
        hasProjectApiScope: projectService.hasProjectApiScope(),
        hasActiveConflict: remoteDraftConflictRef.current,
        saveRemote: async () => {
          await projectService.bootstrapAuthContext();
          return projectService.saveProjectDraft(
            project.id,
            nextDraft,
            buildDraftSaveOptions(
              remoteDraftVersionRef.current,
              baseProjectUpdatedAt,
              baseProjectUpdatedAtOverride,
              checkpointReason,
            ),
          );
        },
        saveLocal: (draftToSave) => storageService.saveDraft(draftToSave),
        getConflictDetail: getProjectDraftConflictDetail,
      });

      if (outcome.status === 'remote') {
        remoteDraftVersionRef.current = outcome.version;
        setBaseProjectUpdatedAt(outcome.baseProjectUpdatedAt ?? project.updatedAt);
        remoteDraftConflictRef.current = false;
        setHasRemoteDraftConflict(false);
        setDirtySegments(new Set());
        return;
      }

      if (outcome.status === 'conflict') {
        remoteDraftVersionRef.current = outcome.detail.server_version;
        remoteDraftConflictRef.current = true;
        setHasRemoteDraftConflict(true);
        setUploadMessage('A newer saved draft is available. Autosave is paused. Keep current edits or load the latest saved draft. Saved translated segments are safe.');
        console.warn('Project draft save hit a version conflict; kept the local IndexedDB draft for recovery:', outcome.detail);
        return;
      }

      setDirtySegments(new Set());
      setLastSavedAt(new Date());
    };

    await enqueueSerialized(draftSaveQueueRef, saveDraft);
  }, [baseProjectUpdatedAt, currentProject, segments, setDirtySegments, setUploadMessage, translations]);

  const refreshSourceMediaUrl = useCallback(async () => {
    if (!currentProject?.mediaId) {
      return;
    }

    try {
      const media = await projectService.getMedia(currentProject.mediaId);
      setSourceMediaUrl(media.media_url ?? null);
      if (!media.media_url) {
        setUploadMessage('A fresh source-media preview is not available yet.');
      }
    } catch (error) {
      setSourceMediaUrl(null);
      setUploadMessage(mapUserFacingError(error, 'Unable to refresh the source-media preview. Your project data is unchanged.'));
    }
  }, [currentProject?.mediaId, setUploadMessage]);

  const refreshRenderedVideoUrl = useCallback(async () => {
    if (!currentProject?.currentLipsyncJobId) {
      return;
    }

    try {
      const job = await projectService.getExportStatus(currentProject.currentLipsyncJobId);
      setRenderedVideoUrl(job?.output_video_url ?? null);
      if (!job?.output_video_url) {
        setUploadMessage('A fresh rendered-video preview is not available yet.');
      }
    } catch (error) {
      setRenderedVideoUrl(null);
      setUploadMessage(mapUserFacingError(error, 'Unable to refresh the rendered-video preview. Your project data is unchanged.'));
    }
  }, [currentProject?.currentLipsyncJobId, setUploadMessage]);

  const applyProjectPatch = useCallback(async ({
    name,
    sourceLanguage,
    targetLanguage,
    status,
    transcriptId,
    mediaId,
  }: ApplyProjectPatchOptions) => {
    if (!currentProject) {
      return null;
    }

    if (projectService.hasProjectApiScope()) {
      if (hasRemoteDraftConflict) {
        throw new Error('Reload the latest backend draft before updating project metadata.');
      }

      await projectService.bootstrapAuthContext();
      const updatedProject = await projectService.updateProject(currentProject.id, {
        ...(name !== undefined ? { name } : {}),
        ...(status !== undefined ? { status } : {}),
        ...(sourceLanguage !== undefined ? { sourceLanguage } : {}),
        ...(targetLanguage !== undefined
          ? {
              targetLanguage,
              activeTranslationLanguage: targetLanguage,
            }
          : {}),
        ...(mediaId !== undefined ? { mediaId } : {}),
        ...(transcriptId !== undefined ? { transcriptId } : {}),
      });

      const hydratedProject: Project = updatedProject;
      setCurrentProject(hydratedProject);
      setBaseProjectUpdatedAt(updatedProject.updatedAt);
      return hydratedProject;
    }

    const hydratedProject: Project = {
      ...currentProject,
      ...(name !== undefined ? { name } : {}),
      ...(sourceLanguage !== undefined ? { sourceLanguage } : {}),
      ...(targetLanguage !== undefined ? { targetLanguage } : {}),
      ...(status !== undefined ? { status } : {}),
      ...(transcriptId !== undefined ? { transcriptId } : {}),
      ...(mediaId !== undefined ? { mediaId } : {}),
      updatedAt: new Date().toISOString(),
    };

    setCurrentProject(hydratedProject);
    setBaseProjectUpdatedAt(hydratedProject.updatedAt);
    return hydratedProject;
  }, [currentProject, hasRemoteDraftConflict, setCurrentProject]);

  const applyProjectStatus = useCallback((status: Project['status']) => {
    return applyProjectPatch({ status });
  }, [applyProjectPatch]);

  return {
    applyProjectPatch,
    applyProjectStatus,
    dismissRemoteDraftConflict,
    ensureCanonicalProjectForWrite,
    hasRemoteDraftConflict,
    isReloadingProject,
    lastSavedAt,
    loadProjectData,
    persistDraft,
    pipelineOperation,
    refreshRenderedVideoUrl,
    refreshSourceMediaUrl,
    renderedVideoUrl,
    setPipelineOperation,
    setRenderedVideoUrl,
    setSourceMediaUrl,
    sourceMediaUrl,
  };
}
