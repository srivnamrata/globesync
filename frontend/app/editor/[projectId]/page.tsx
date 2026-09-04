'use client';

import React, { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useProjectStore, type Project } from '../../../store/projectStore';
import { useMediaStore, type TranscriptSegment } from '../../../store/mediaStore';
import { useTranslationStore, type TranslatedSegment } from '../../../store/translationStore';
import { storageService, type HeygenXFile } from '../../../services/storageService';
import { useProjectAutoSave } from '../../../hooks/useProject';
import { useTimeline } from '../../../hooks/useTimeline';
import { useHistory } from '../../../hooks/useHistory';
import { ApiError } from '../../../services/apiClient';
import { getProjectDraftConflictDetail, projectService, type PipelineOperationStatus, type ProjectVersionSummary } from '../../../services/projectService';
import { mapUserFacingError } from '../../../services/userFacingErrors';
import WaveformCanvas from '../../../components/WaveformRenderer/WaveformCanvas';
import type { WaveformData } from '../../../utils/waveformProcessing';
import { Button, StatePanel, StatusBadge } from '../../../components/ui';
import ExportHistory from '../../../components/ExportHub/ExportHistory';
import { ExportReadiness } from '../../../components/ExportHub/ExportReadiness';
import { PipelineStatus } from '../../../components/ExportHub/PipelineStatus';

function getTextDirection(languageCode?: string): 'ltr' | 'rtl' {
  const baseLanguage = (languageCode || '').toLowerCase().split(/[-_]/)[0];
  return ['ar', 'he', 'ur'].includes(baseLanguage) ? 'rtl' : 'ltr';
}

type ActiveBuildJob = {
  job_id: string;
  render_mode?: 'dub_only' | 'dub_and_lipsync';
  status: string;
  progress_percent: number;
  current_stage: string;
  last_successful_stage?: string | null;
  error_message?: string | null;
};

const mergeDraftWithProject = (draft: HeygenXFile, project?: Project | null): HeygenXFile => ({
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

const buildProjectFromDraft = (draft: HeygenXFile, project?: Project | null): Project => ({
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
});

function toPersistableFilename(value?: string): string {
  if (!value) return 'source_video.mp4';
  try {
    const url = new URL(value);
    const filename = url.pathname.split('/').filter(Boolean).pop();
    return filename || 'source_video.mp4';
  } catch {
    return value;
  }
}

function sanitizeDraftArtifactReferences(draft: HeygenXFile): HeygenXFile {
  return {
    ...draft,
    mediaReferences: {
      ...draft.mediaReferences,
      videoFilename: toPersistableFilename(draft.mediaReferences.videoFilename),
    },
  };
}

export default function TranslationEditor() {
  const params = useParams();
  const router = useRouter();
  const projectId = params?.projectId as string;

  const { currentProject, setCurrentProject } = useProjectStore();
  const { segments, setSegments, updateSegmentText } = useMediaStore();
  const { translations, setTranslations, updateTranslationText } = useTranslationStore();
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'transcribing' | 'translating'>('idle');
  const [uploadProgressPercent, setUploadProgressPercent] = useState(0);
  const [buildState, setBuildState] = useState<'idle' | 'syncing' | 'building'>('idle');
  const [buildMode, setBuildMode] = useState<'dub_only' | 'dub_and_lipsync' | null>(null);
  const [activeBuildJob, setActiveBuildJob] = useState<ActiveBuildJob | null>(null);
  const [pipelineOperation, setPipelineOperation] = useState<PipelineOperationStatus | null>(null);
  const [isRetryingPipelineOperation, setIsRetryingPipelineOperation] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [sourceMediaUrl, setSourceMediaUrl] = useState<string | null>(null);
  const [renderedVideoUrl, setRenderedVideoUrl] = useState<string | null>(null);
  const [remoteDraftVersion, setRemoteDraftVersion] = useState<number | null>(null);
  const [baseProjectUpdatedAt, setBaseProjectUpdatedAt] = useState<string | null>(null);
  const [hasRemoteDraftConflict, setHasRemoteDraftConflict] = useState(false);
  const [isReloadingProject, setIsReloadingProject] = useState(false);
  const [dirtySegments, setDirtySegments] = useState<Set<string>>(new Set());
  const [activeActionMenu, setActiveActionMenu] = useState<string | null>(null);
  const [segmentBusy, setSegmentBusy] = useState<Record<string, 'retranslating' | 'synthesizing'>>({});
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [originalTranslations, setOriginalTranslations] = useState<Record<string, string>>({});
  const [loopSegmentId, setLoopSegmentId] = useState<string | null>(null);
  const [waveformData, setWaveformData] = useState<WaveformData | null>(null);
  const [lipSyncStatuses, setLipSyncStatuses] = useState<Record<string, string>>({});
  const [comparisonMode, setComparisonMode] = useState<'original' | 'dubbed'>('dubbed');
  const [projectVersions, setProjectVersions] = useState<ProjectVersionSummary[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isExportHistoryOpen, setIsExportHistoryOpen] = useState(false);
  const [isExportReadinessOpen, setIsExportReadinessOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const isScrubbingRef = useRef(false);
  const comparisonAudioRef = useRef<HTMLAudioElement | null>(null);
  const dialogFocusOriginRef = useRef<HTMLElement | null>(null);
  const transcriptContainerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const timeline = useTimeline();
  const history = useHistory();

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
            videoFilename: currentProject.mediaFilename ?? 'source_video.mp4',
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

      setCurrentProject(hydratedProject);
      setRemoteDraftVersion(seededDraft.version);
      setBaseProjectUpdatedAt(seededDraft.base_project_updated_at ?? hydratedProject.updatedAt);
      setHasRemoteDraftConflict(false);
      await storageService.saveDraft(canonicalDraft);
      if (currentProject.id !== canonicalProject.id) {
        await storageService.deleteDraft(currentProject.id);
        router.replace(`/editor/${canonicalProject.id}`);
      }
      setUploadMessage('This project was restored into your cloud workspace so uploads and transcription can continue.');
      return hydratedProject;
    }
  }, [currentProject, router, segments, setCurrentProject, translations]);

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
      let pipelineOperation: PipelineOperationStatus | null = null;
      let nextBaseProjectUpdatedAt: string | null = null;

      if (projectService.hasProjectApiScope()) {
        try {
          await projectService.bootstrapAuthContext();
          backendProject = await projectService.getProject(projectId);
          pipelineOperation = backendProject.currentPipelineOperationId === null
            ? null
            : await projectService.getPipelineOperation(projectId).catch(() => null);
          setPipelineOperation(pipelineOperation);
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
            setRemoteDraftVersion(remoteDraft.version);
            nextBaseProjectUpdatedAt = remoteDraft.baseProjectUpdatedAt ?? backendProject.updatedAt;
          } catch (draftError) {
            draft = projectService.buildLocalDraftFromProject(backendProject);
            setRemoteDraftVersion(null);
            nextBaseProjectUpdatedAt = backendProject.updatedAt;
            console.warn('No server-side draft found yet, seeding canonical draft from project metadata:', draftError);

            try {
              const seededDraft = await projectService.seedProjectDraft(backendProject);
              setRemoteDraftVersion(seededDraft.version);
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
        router.push('/');
        return;
      }

      draft = sanitizeDraftArtifactReferences(draft);
      await storageService.saveDraft(draft);

      const hydratedProject = buildProjectFromDraft(draft, backendProject);

      setCurrentProject(hydratedProject);
      // Clear conflict state and stale upload message together before
      // updating segments/translations so the banner disappears atomically.
      setHasRemoteDraftConflict(false);
      setUploadMessage(
        pipelineOperation && pipelineOperation.status !== 'completed'
          ? pipelineOperation.error_message || pipelineOperation.message
          : null,
      );
      if (pipelineOperation?.operation_type === 'transcription' && pipelineOperation.status === 'in_progress') {
        setUploadState('transcribing');
      } else if (pipelineOperation?.operation_type === 'translation' && pipelineOperation.status === 'in_progress') {
        setUploadState('translating');
      } else if (!pipelineOperation || pipelineOperation.status === 'completed' || pipelineOperation.status === 'failed') {
        setUploadState('idle');
      }
      setBaseProjectUpdatedAt(nextBaseProjectUpdatedAt ?? hydratedProject.updatedAt);

      const draftSegments = draft.mediaReferences.originalTranscriptSegments || [];
      const draftTranslations = draft.translations || [];

      setSegments(draftSegments);

      // Resolve the best available translations before updating UI so the
      // translation pane never flashes blank during a reload.
      // Priority: backend API fetch > draft blob > keep whatever is already in store.
      let resolvedTranslations = draftTranslations;

      if (
        draft.mediaReferences.transcriptId &&
        draftSegments.length > 0
      ) {
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

      // Only call setTranslations once, with the fully resolved set.
      // If nothing was found anywhere, keep the existing store state rather
      // than replacing it with an empty array.
      if (resolvedTranslations.length > 0) {
        setTranslations(resolvedTranslations);
        // Snapshot original translations for "Reset to original" action.
        const snapshot: Record<string, string> = {};
        resolvedTranslations.forEach((t) => { snapshot[t.transcriptSegmentId] = t.translatedText; });
        setOriginalTranslations(snapshot);
      } else {
        // No translations found from API or draft (e.g. fresh upload with new segment IDs).
        // Wipe the translation store so stale translations from a previous
        // transcript don't linger against the new segments.
        setTranslations([]);
        setOriginalTranslations({});
      }
    } catch (err) {
      console.error('Failed to load project draft in editor:', err);
    } finally {
      setIsReloadingProject(false);
    }
  }, [projectId, router, setCurrentProject, setSegments, setTranslations]);

  useEffect(() => {
    void loadProjectData();
  }, [loadProjectData]);

  const retryFailedTranslation = async () => {
    if (!pipelineOperation || pipelineOperation.operation_type !== 'translation' || pipelineOperation.status !== 'failed') {
      return;
    }

    setIsRetryingPipelineOperation(true);
    try {
      const retry = await projectService.retryPipelineOperation(pipelineOperation.id);
      const queuedOperation: PipelineOperationStatus = {
        ...pipelineOperation,
        id: retry.operation_id,
        status: retry.status,
        progress_percent: 0,
        current_stage: 'queued',
        last_successful_stage: null,
        message: retry.message,
        error_message: null,
        updated_at: new Date().toISOString(),
      };
      setPipelineOperation(queuedOperation);
      setUploadState('translating');
      setUploadMessage(retry.message);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'Translation retry could not be queued.');
    } finally {
      setIsRetryingPipelineOperation(false);
    }
  };

  const retryFailedTranscription = async () => {
    if (!pipelineOperation || pipelineOperation.operation_type !== 'transcription' || pipelineOperation.status !== 'failed') {
      return;
    }

    setIsRetryingPipelineOperation(true);
    try {
      const retry = await projectService.retryTranscriptionOperation(pipelineOperation.id);
      setPipelineOperation({
        ...pipelineOperation,
        id: retry.operation_id,
        status: retry.status,
        progress_percent: 0,
        current_stage: 'queued',
        last_successful_stage: null,
        message: retry.message,
        error_message: null,
        updated_at: new Date().toISOString(),
      });
      setUploadState('transcribing');
      setUploadMessage(retry.message);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'Transcription retry could not be queued.');
    } finally {
      setIsRetryingPipelineOperation(false);
    }
  };

  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement) {
      return;
    }

    const syncTime = () => {
      const currentTime = videoElement.currentTime;
      timeline.setCurrentTimeSeconds(currentTime);

      const activeSegment = segments.find(
        (segment) => currentTime >= segment.startTimeSeconds && currentTime < segment.endTimeSeconds,
      );
      if (activeSegment && timeline.selectedSegmentId !== activeSegment.id) {
        timeline.setSelectedSegmentId(activeSegment.id);
      }

      if (!loopSegmentId || videoElement.paused) {
        return;
      }

      const loopSegment = segments.find((segment) => segment.id === loopSegmentId);
      if (loopSegment && videoElement.currentTime >= loopSegment.endTimeSeconds) {
        videoElement.currentTime = loopSegment.startTimeSeconds;
      }
    };
    const syncPlaying = () => timeline.setPlaying(!videoElement.paused);

    videoElement.addEventListener('timeupdate', syncTime);
    videoElement.addEventListener('play', syncPlaying);
    videoElement.addEventListener('pause', syncPlaying);
    videoElement.addEventListener('loadedmetadata', syncTime);

    return () => {
      videoElement.removeEventListener('timeupdate', syncTime);
      videoElement.removeEventListener('play', syncPlaying);
      videoElement.removeEventListener('pause', syncPlaying);
      videoElement.removeEventListener('loadedmetadata', syncTime);
    };
  }, [loopSegmentId, renderedVideoUrl, segments, timeline]);

  useEffect(() => {
    if (!currentProject?.mediaId || typeof AudioContext === 'undefined') {
      setWaveformData(null);
      return;
    }

    let isMounted = true;
    let audioContext: AudioContext | null = null;
    async function decodeWaveform() {
      try {
        const audioDetails = await projectService.getMediaAudio(currentProject.mediaId!);
        if (!isMounted) return;
        audioContext = new AudioContext();
        const response = await fetch(audioDetails.audio_url);
        const audioBuffer = await audioContext.decodeAudioData(await response.arrayBuffer());
        if (!isMounted) return;

        const channels = Array.from({ length: audioBuffer.numberOfChannels }, (_, index) => (
          new Float32Array(audioBuffer.getChannelData(index))
        ));
        setWaveformData({
          channels,
          sampleRate: audioBuffer.sampleRate,
          duration: audioBuffer.duration,
        });
      } catch (error) {
        console.warn('Could not decode preview audio for waveform:', error);
        if (isMounted) setWaveformData(null);
      } finally {
        await audioContext?.close();
      }
    }

    void decodeWaveform();
    return () => {
      isMounted = false;
    };
  }, [currentProject?.mediaId]);

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
  }: {
    projectOverride?: typeof currentProject;
    segmentsOverride?: TranscriptSegment[];
    translationsOverride?: TranslatedSegment[];
    videoFilename?: string;
    durationSeconds?: number;
    transcriptId?: string;
    mediaId?: string;
    baseProjectUpdatedAtOverride?: string | null;
    checkpointReason?: string;
  } = {}) => {
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
        videoFilename: toPersistableFilename(videoFilename ?? project.mediaFilename),
        durationSeconds:
          durationSeconds ??
          (segmentsOverride ?? segments).reduce((acc, segment) => Math.max(acc, segment.endTimeSeconds), 0),
        originalTranscriptSegments: segmentsOverride ?? segments,
        transcriptId: transcriptId ?? project.transcriptId,
        mediaId: mediaId ?? project.mediaId,
      },
      translations: translationsOverride ?? Object.values(translations),
    };

    if (projectService.hasProjectApiScope() && !hasRemoteDraftConflict) {
      try {
        await projectService.bootstrapAuthContext();
        const remoteDraft = await projectService.saveProjectDraft(project.id, nextDraft, {
          version: remoteDraftVersion ?? 1,
          baseProjectUpdatedAt: baseProjectUpdatedAtOverride ?? baseProjectUpdatedAt,
          ...(checkpointReason ? { checkpointReason } : {}),
        });
        setRemoteDraftVersion(remoteDraft.version);
        setBaseProjectUpdatedAt(remoteDraft.base_project_updated_at ?? project.updatedAt);
        setHasRemoteDraftConflict(false);
        await storageService.saveDraft(nextDraft);
        setDirtySegments(new Set());
        return;
      } catch (error) {
        const conflictDetail = getProjectDraftConflictDetail(error);
        if (conflictDetail) {
          setHasRemoteDraftConflict(true);
          setUploadMessage('A newer backend draft exists for this project. Backend autosave is paused until you reload the latest shared draft. Your browser edits are still cached locally for recovery.');
          await storageService.saveDraft(nextDraft);
          console.warn('Project draft save hit a version conflict; kept the local IndexedDB draft for recovery:', conflictDetail);
          return;
        }

        console.warn('Failed to persist project draft to backend; kept local IndexedDB draft as fallback:', error);
      }
    }

    await storageService.saveDraft(nextDraft);
    setDirtySegments(new Set());
    setLastSavedAt(new Date());
  }, [currentProject, segments, translations, hasRemoteDraftConflict, remoteDraftVersion, baseProjectUpdatedAt]);

  const selectedSegment = segments.find((segment) => segment.id === timeline.selectedSegmentId) ?? null;
  const comparisonUrl = comparisonMode === 'original'
    ? sourceMediaUrl
    : renderedVideoUrl;
  const hasComparisonUrl = Boolean(comparisonUrl?.startsWith('http'));
  const totalDurationSeconds = useMemo(
    () => segments.reduce((acc, segment) => Math.max(acc, segment.endTimeSeconds), 0),
    [segments],
  );

  const refreshSourceMediaUrl = useCallback(async () => {
    if (!currentProject?.mediaId) return;
    try {
      const media = await projectService.getMedia(currentProject.mediaId);
      setSourceMediaUrl(media.media_url ?? null);
      if (!media.media_url) setUploadMessage('A fresh source-media preview is not available yet.');
    } catch (error) {
      setSourceMediaUrl(null);
      setUploadMessage(mapUserFacingError(error, 'Unable to refresh the source-media preview. Your project data is unchanged.'));
    }
  }, [currentProject?.mediaId]);

  const refreshRenderedVideoUrl = useCallback(async () => {
    if (!currentProject?.currentLipsyncJobId) return;
    try {
      const job = await projectService.getExportStatus(currentProject.currentLipsyncJobId);
      setRenderedVideoUrl(job?.output_video_url ?? null);
      if (!job?.output_video_url) setUploadMessage('A fresh rendered-video preview is not available yet.');
    } catch (error) {
      setRenderedVideoUrl(null);
      setUploadMessage(mapUserFacingError(error, 'Unable to refresh the rendered-video preview. Your project data is unchanged.'));
    }
  }, [currentProject?.currentLipsyncJobId]);

  const seekToTime = useCallback((seconds: number, segmentId?: string) => {
    timeline.setCurrentTimeSeconds(seconds);
    if (segmentId) {
      timeline.setSelectedSegmentId(segmentId);
    }

    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
    }
  }, [timeline]);

  const seekFromTrackPointer = useCallback((clientX: number, element: HTMLElement) => {
    const bounds = element.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width));
    seekToTime(ratio * totalDurationSeconds);
  }, [seekToTime, totalDurationSeconds]);

  const playComparisonSegment = useCallback(() => {
    if (!selectedSegment || !hasComparisonUrl || !comparisonAudioRef.current) {
      return;
    }

    comparisonAudioRef.current.currentTime = selectedSegment.startTimeSeconds;
    void comparisonAudioRef.current.play();
  }, [hasComparisonUrl, selectedSegment]);

  const handleOpenVersionHistory = useCallback(async () => {
    if (!currentProject) return;
    setIsHistoryOpen((isOpen) => !isOpen);
    setIsExportHistoryOpen(false);
    setIsExportReadinessOpen(false);
    if (projectVersions.length > 0 || isLoadingHistory) return;

    setIsLoadingHistory(true);
    try {
      setProjectVersions(await projectService.getProjectVersions(currentProject.id));
    } catch (error) {
      setUploadMessage(mapUserFacingError(error, 'Unable to load project version history.'));
    } finally {
      setIsLoadingHistory(false);
    }
  }, [currentProject, isLoadingHistory, projectVersions.length]);

  useEffect(() => {
    if (!isHistoryOpen) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsHistoryOpen(false);
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isHistoryOpen]);

  useEffect(() => {
    if (!isExportHistoryOpen && !isExportReadinessOpen) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setIsExportHistoryOpen(false);
      setIsExportReadinessOpen(false);
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isExportHistoryOpen, isExportReadinessOpen]);

  useEffect(() => {
    const isDialogOpen = isHistoryOpen || isExportHistoryOpen || isExportReadinessOpen;
    if (isDialogOpen && !dialogFocusOriginRef.current && document.activeElement instanceof HTMLElement) {
      dialogFocusOriginRef.current = document.activeElement;
    }
    if (!isDialogOpen && dialogFocusOriginRef.current) {
      dialogFocusOriginRef.current.focus();
      dialogFocusOriginRef.current = null;
    }
  }, [isHistoryOpen, isExportHistoryOpen, isExportReadinessOpen]);

  useEffect(() => {
    if (!isHistoryOpen && !isExportHistoryOpen && !isExportReadinessOpen) return;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) return;
    const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const handleTab = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener('keydown', handleTab);
    return () => dialog.removeEventListener('keydown', handleTab);
  }, [isHistoryOpen, isExportHistoryOpen, isExportReadinessOpen]);

  const applyProjectPatch = useCallback(async ({
    name,
    sourceLanguage,
    targetLanguage,
    status,
    transcriptId,
    mediaId,
  }: {
    name?: string;
    sourceLanguage?: string;
    targetLanguage?: string;
    status?: Project['status'];
    transcriptId?: string;
    mediaId?: string;
  }): Promise<Project | null> => {
    if (!currentProject) {
      return null;
    }

    if (projectService.hasProjectApiScope()) {
      if (hasRemoteDraftConflict) {
        throw new Error('Reload the latest backend draft before updating project metadata.');
      }

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

  const handleSwapProjectLanguages = useCallback(async () => {
    if (!currentProject) {
      return;
    }

    const hasDownstreamWork = Boolean(
      currentProject.mediaId ||
      currentProject.transcriptId ||
      segments.length > 0 ||
      Object.keys(translations).length > 0,
    );

    if (hasDownstreamWork) {
      const shouldCreateProject = window.confirm(
        'This project already has downstream work. Create a new project with the languages swapped and leave this project unchanged?',
      );
      if (!shouldCreateProject) {
        return;
      }

      if (!projectService.hasProjectApiScope()) {
        setUploadMessage('Create a new project from the workspace home to use a different language pair.');
        return;
      }

      const clonedProjectName = window.prompt(
        'Name the new project:',
        `${currentProject.name} - ${currentProject.targetLanguage.toUpperCase()}`,
      );
      if (!clonedProjectName?.trim()) {
        return;
      }

      try {
        const clonedProject = await projectService.createProjectShellWithDraft(
          clonedProjectName.trim(),
          currentProject.targetLanguage,
          currentProject.sourceLanguage,
        );
        router.push(`/editor/${clonedProject.id}`);
      } catch (error) {
        setUploadMessage(mapUserFacingError(error, 'Unable to create the new language-pair project.'));
      }
      return;
    }

    try {
      const updatedProject = await applyProjectPatch({
        sourceLanguage: currentProject.targetLanguage,
        targetLanguage: currentProject.sourceLanguage,
      });
      if (updatedProject) {
        await persistDraft({ projectOverride: updatedProject });
      }
      setUploadMessage('Language pair swapped.');
    } catch (error) {
      setUploadMessage(mapUserFacingError(error, 'Unable to swap the project language pair.'));
    }
  }, [applyProjectPatch, currentProject, persistDraft, segments.length, translations]);

  const handleRetranslateSegment = useCallback(async (segId: string) => {
    if (!currentProject) return;
    const seg = segments.find((s) => s.id === segId);
    if (!seg) return;
    setSegmentBusy((prev) => ({ ...prev, [segId]: 'retranslating' }));
    setActiveActionMenu(null);
    try {
      const idx = segments.indexOf(seg);
      const result = await projectService.retranslateSegment({
        segmentId: seg.id,
        sourceText: seg.text,
        originalDurationMs: Math.round(seg.durationSeconds * 1000),
        sourceLanguage: currentProject.sourceLanguage,
        targetLanguage: currentProject.targetLanguage,
        speakerTag: seg.speakerTag,
        previousContext: idx > 0 ? segments[idx - 1].text : undefined,
        nextContext: idx < segments.length - 1 ? segments[idx + 1].text : undefined,
      });
      setTranslations(Object.values({
        ...translations,
        [segId]: { ...result, generatedAudioStatus: undefined },
      }));
      setDirtySegments((prev) => new Set(prev).add(segId));
      setUploadMessage('Segment retranslated. Regenerate its audio before export.');
    } catch (err) {
      console.error('Retranslate failed:', err);
      setUploadMessage(mapUserFacingError(err, 'Unable to retranslate this segment.'));
    } finally {
      setSegmentBusy((prev) => { const n = { ...prev }; delete n[segId]; return n; });
    }
  }, [currentProject, segments, setTranslations, translations]);

  const handleSynthesizeSegment = useCallback(async (segId: string) => {
    const trans = translations[segId];
    if (!trans?.id) return;
    setSegmentBusy((prev) => ({ ...prev, [segId]: 'synthesizing' }));
    setActiveActionMenu(null);
    try {
      await projectService.synthesizeSegment(trans.id);
      setTranslations(Object.values({
        ...translations,
        [segId]: { ...trans, generatedAudioStatus: 'ready' },
      }));
      setUploadMessage('Segment audio regenerated successfully.');
    } catch (err) {
      console.error('Synthesize segment failed:', err);
      setUploadMessage(mapUserFacingError(err, 'Unable to regenerate audio for this segment.'));
    } finally {
      setSegmentBusy((prev) => { const n = { ...prev }; delete n[segId]; return n; });
    }
  }, [setTranslations, translations]);

  const handleResetTranslation = useCallback((segId: string) => {
    const original = originalTranslations[segId];
    if (original !== undefined) {
      updateTranslationText(segId, original);
      setDirtySegments((prev) => { const n = new Set(prev); n.delete(segId); return n; });
    }
    setActiveActionMenu(null);
  }, [originalTranslations, updateTranslationText]);

  const handleManualSave = useCallback(async () => {
    await persistDraft({ checkpointReason: 'manual_save' });
  }, [persistDraft]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isTextEntry = e.target instanceof HTMLElement && ['TEXTAREA', 'INPUT', 'SELECT'].includes(e.target.tagName);

      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        void handleManualSave();
      }
      if (!isTextEntry && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault();
        const currentIndex = segments.findIndex((segment) => segment.id === timeline.selectedSegmentId);
        const nextIndex = e.key === 'ArrowDown'
          ? Math.min(segments.length - 1, currentIndex + 1)
          : Math.max(0, currentIndex <= 0 ? 0 : currentIndex - 1);
        const nextSegment = segments[nextIndex];
        if (nextSegment) {
          seekToTime(nextSegment.startTimeSeconds, nextSegment.id);
        }
      }
      if (e.key === ' ' && !isTextEntry) {
        e.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) void videoRef.current.play();
          else videoRef.current.pause();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleManualSave, seekToTime, segments, timeline.selectedSegmentId]);

  useEffect(() => {
    if (timeline.selectedSegmentId && transcriptContainerRef.current) {
      const activeEl = transcriptContainerRef.current.querySelector(`[data-segment-id="${timeline.selectedSegmentId}"]`);
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [timeline.selectedSegmentId]);

  // Keep the existing local cache, but also push draft changes to the backend when scope is configured.
  useProjectAutoSave(persistDraft);

  const pollForTranslations = async (
    transcriptId: string,
    targetLanguage: string,
    expectedCount: number,
  ): Promise<TranslatedSegment[]> => {
    let latestTranslations: TranslatedSegment[] = [];

    for (let attempt = 0; attempt < 40; attempt += 1) {
      try {
        const fetchedTranslations = await projectService.fetchTranslations(transcriptId, targetLanguage);
        if (fetchedTranslations.length > 0) {
          latestTranslations = fetchedTranslations;
        }
        if (fetchedTranslations.length >= expectedCount) {
          return fetchedTranslations;
        }
      } catch (error) {
        console.warn('Translation polling attempt failed:', error);
      }

      await new Promise((resolve) => setTimeout(resolve, 3000));
    }

    return latestTranslations;
  };

  const syncTranslationsBeforeBuild = async (): Promise<TranslatedSegment[]> => {
    const localTranslations = Object.values(translations).filter(
      (translation) => translation.id && translation.translatedText.trim().length > 0,
    );

    const persistedTranslations = await Promise.all(
      localTranslations.map((translation) =>
        projectService.updateTranslationSegment(translation.id, translation.translatedText),
      ),
    );

    setTranslations(persistedTranslations);
    await persistDraft({ translationsOverride: persistedTranslations, checkpointReason: 'pre_build' });
    return persistedTranslations;
  };

  const pollForLipSyncCompletion = async (jobId: string, withLipSync: boolean) => {
    const buildLabel = withLipSync ? 'Dub & Lip-Sync' : 'Dub only';
    let latestStatus: any = null;

    for (let attempt = 0; attempt < 180; attempt += 1) {
      latestStatus = await projectService.getExportStatus(jobId);
      setActiveBuildJob(latestStatus as ActiveBuildJob);

      if (latestStatus?.status === 'failed') {
        throw new Error(latestStatus?.error_message || `${buildLabel} failed. Check the backend logs for details.`);
      }

      if (latestStatus?.status === 'completed') {
        return latestStatus;
      }

      setUploadMessage(
        `${buildLabel} ${String(latestStatus?.status || 'in progress').replace('_', ' ')}…`,
      );
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }

    return latestStatus;
  };

  const runBuildPipeline = async (withLipSync: boolean) => {
    if (!currentProject?.id || !currentProject.mediaId || !currentProject.transcriptId) {
      setUploadMessage('Upload and transcribe media before building.');
      return;
    }
    if (segments.length === 0) {
      setUploadMessage('Transcript segments are required before building.');
      return;
    }
    if (Object.keys(translations).length < segments.length) {
      setUploadMessage('Wait until all translated segments are available before building.');
      return;
    }

    try {
      setBuildMode(withLipSync ? 'dub_and_lipsync' : 'dub_only');
      setBuildState('syncing');
      setLipSyncStatuses({});
      setUploadMessage('Saving translated segment edits…');
      const persistedTranslations = await syncTranslationsBeforeBuild();

      if (persistedTranslations.length < segments.length) {
        throw new Error('Not all translated segments are ready yet.');
      }

      const projectForBuild = (await applyProjectPatch({ status: 'processing' })) ?? currentProject;

      setBuildState('building');
      setUploadMessage(withLipSync ? 'Queuing dub and lip-sync pipeline…' : 'Queuing dub-only pipeline…');

      const trigger = withLipSync ? projectService.triggerLipSync : projectService.triggerDubOnly;
      const job = await trigger.call(
        projectService,
        projectForBuild.mediaId!,
        projectForBuild.transcriptId!,
        projectForBuild.targetLanguage,
        projectForBuild.id,
      );
      setActiveBuildJob({
        job_id: job.job_id,
        render_mode: withLipSync ? 'dub_and_lipsync' : 'dub_only',
        status: 'queued',
        progress_percent: 0,
        current_stage: 'queued',
      });

      setUploadMessage(withLipSync ? 'Building dubbed audio and syncing lip motion…' : 'Building dubbed audio…');
      const completedJob = await pollForLipSyncCompletion(job.job_id, withLipSync);
      if (withLipSync && Array.isArray(completedJob?.segments_metadata)) {
        setLipSyncStatuses(
          Object.fromEntries(
            completedJob.segments_metadata
              .filter((metadata: { segment_id?: string; render_status?: string }) => metadata.segment_id && metadata.render_status)
              .map((metadata: { segment_id: string; render_status: string }) => [metadata.segment_id, metadata.render_status]),
          ),
        );
      }

      if (completedJob?.output_video_url) {
        setRenderedVideoUrl(completedJob.output_video_url);
        const refreshedProject = await projectService.getProject(projectForBuild.id).catch(() => null);
        if (refreshedProject) {
          setCurrentProject(refreshedProject);
        } else {
          await applyProjectPatch({ status: 'completed' });
        }

        if (!withLipSync) {
          setUploadMessage('Dub complete. Preview is ready — download the dubbed video below.');
        } else {
          const skippedSegments = Array.isArray(completedJob?.segments_metadata)
            ? completedJob.segments_metadata.filter((s: { render_status?: string }) => s.render_status && s.render_status !== 'completed')
            : [];
          if (skippedSegments.length === 0) {
            setUploadMessage('Dub & Lip-Sync complete. Preview is ready, and you can download the finished video below.');
          } else if (skippedSegments.length === segments.length) {
            setUploadMessage('Dub completed, but lip-sync could not be applied because no usable face was detected in the source footage. You can still preview and download the dubbed video below.');
          } else {
            setUploadMessage(`Dub completed. Lip-sync was skipped for ${skippedSegments.length} segment${skippedSegments.length === 1 ? '' : 's'}, so parts of the video may keep the original facial motion.`);
          }
        }
      } else {
        await applyProjectPatch({ status: 'completed' });
        setUploadMessage('Build completed successfully, but the preview link is not available yet. Reload the project in a few moments to fetch the latest export.');
      }
    } catch (error) {
      setUploadMessage(mapUserFacingError(error, withLipSync ? 'Unable to build dub and lip-sync output.' : 'Unable to build dubbed output.'));
    } finally {
      setBuildState('idle');
      setBuildMode(null);
    }
  };

  const handleBuildDubOnly = () => runBuildPipeline(false);
  const handleBuildDubAndLipSync = () => runBuildPipeline(true);

  const handleTextChange = (segId: string, text: string) => {
    const oldText = segments.find((s) => s.id === segId)?.text || '';
    history.pushHistory({
      type: 'edit_transcript',
      targetId: segId,
      before: oldText,
      after: text,
      description: `Edit transcript segment text`,
    });
    updateSegmentText(segId, text);
    setDirtySegments((prev) => new Set(prev).add(segId));
  };

  const handleTranslationChange = (segId: string, text: string) => {
    const oldText = translations[segId]?.translatedText || '';
    history.pushHistory({
      type: 'edit_translation',
      targetId: segId,
      before: oldText,
      after: text,
      description: `Edit translation text`,
    });
    updateTranslationText(segId, text);
    setDirtySegments((prev) => new Set(prev).add(segId));
  };

  const handleMediaSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !currentProject) return;

    if (!file.type.startsWith('video/') && !file.type.startsWith('audio/')) {
      setUploadMessage('Choose an audio or video file.');
      return;
    }
    try {
      const projectForUpload = await ensureCanonicalProjectForWrite();
      if (!projectForUpload) {
        throw new Error('Project context is unavailable. Reload the project and try again.');
      }

      setUploadState('uploading');
      setUploadProgressPercent(0);
      setUploadMessage(`Uploading ${file.name}…`);
      const media = file.size > 100 * 1024 * 1024
        ? await projectService.uploadMediaResumable(
          file,
          projectForUpload.id,
          (progressPercent) => {
            setUploadProgressPercent(progressPercent);
            setUploadMessage(`Uploading ${file.name}… ${progressPercent}%`);
          },
        )
        : await projectService.uploadMedia(file);
      setUploadState('transcribing');
      setUploadMessage('Upload complete. Starting transcription…');
      const job = await projectService.startTranscription(media.media_id, projectForUpload.sourceLanguage);

      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const transcript = await projectService.getTranscription(job.transcript_id);
        if (transcript.status === 'failed') {
          throw new Error('Transcription failed. Check the backend and Celery worker logs.');
        }
        if (transcript.status !== 'completed') {
          setUploadMessage(`Transcription ${transcript.status.replace('_', ' ')}…`);
          continue;
        }

        const loadedSegments = transcript.segments.map((segment, index) => ({
          id: segment.id || `segment-${index}`,
          sequenceOrder: segment.sequence_order,
          startTimeSeconds: segment.start_time,
          endTimeSeconds: segment.end_time,
          durationSeconds: segment.duration,
          speakerTag: segment.speaker,
          text: segment.text,
          confidence: segment.confidence ?? 0,
        }));
        const persistedProject = (await applyProjectPatch({
          status: 'processing',
          transcriptId: job.transcript_id,
          mediaId: media.media_id,
        })) ?? currentProject;
        const updatedProject: Project = {
          ...persistedProject,
          mediaFilename: media.filename,
          mediaDurationSeconds: media.duration_seconds,
        };
        setCurrentProject(updatedProject);
        setSourceMediaUrl(media.media_url ?? null);

        setSegments(loadedSegments);
        await persistDraft({
          projectOverride: updatedProject,
          segmentsOverride: loadedSegments,
          translationsOverride: Object.values(translations),
          videoFilename: media.filename,
          durationSeconds: media.duration_seconds,
          transcriptId: job.transcript_id,
          mediaId: media.media_id,
          baseProjectUpdatedAtOverride: updatedProject.updatedAt,
        });

        setUploadState('translating');
        setUploadMessage('Transcription complete. Starting translation…');

        const translationJob = await projectService.triggerProjectTranslation(
          job.transcript_id,
          updatedProject.sourceLanguage,
          updatedProject.targetLanguage,
        );
        setUploadMessage(translationJob.message || 'Translation queued. Waiting for translated segments…');

        const fetchedTranslations = await pollForTranslations(
          job.transcript_id,
          updatedProject.targetLanguage,
          loadedSegments.length,
        );

        if (fetchedTranslations.length > 0) {
          setTranslations(fetchedTranslations);
          await persistDraft({
            projectOverride: updatedProject,
            segmentsOverride: loadedSegments,
            translationsOverride: fetchedTranslations,
            videoFilename: media.filename,
            durationSeconds: media.duration_seconds,
            transcriptId: job.transcript_id,
            mediaId: media.media_id,
            baseProjectUpdatedAtOverride: updatedProject.updatedAt,
          });
          setUploadMessage(
            fetchedTranslations.length >= loadedSegments.length
              ? `Translation complete — ${fetchedTranslations.length} segments loaded.`
              : `Translation is still running — ${fetchedTranslations.length} of ${loadedSegments.length} segments are available.`
          );
        } else {
          setUploadMessage('Translation was queued, but no translated segments were available yet. Please retry in a few moments.');
        }
        break;
      }
    } catch (error) {
      setUploadMessage(mapUserFacingError(error, 'Unable to upload and transcribe the media.'));
    } finally {
      setUploadState('idle');
    }
  };

  if (!currentProject) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950 text-slate-400">
        Loading translation project resources...
      </div>
    );
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-slate-950 text-white">
      {/* Editor Header Bar */}
      <header className="gs-editor-header flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <Button variant="quiet" size="sm" onClick={() => router.push('/')} className="px-1 text-slate-400">
            &larr; Projects
          </Button>
          <span className="hidden text-slate-700 sm:inline" aria-hidden="true">/</span>
          <h1 className="max-w-[13rem] truncate text-base font-bold tracking-tight text-white sm:max-w-xs">{currentProject.name}</h1>
          <StatusBadge tone="neutral" className="font-mono uppercase">
            {currentProject.sourceLanguage} &rarr; {currentProject.targetLanguage}
          </StatusBadge>
          <Button
            onClick={() => void handleSwapProjectLanguages()}
            variant="secondary"
            size="sm"
            className="min-h-7 px-2 py-0.5 text-slate-400"
            aria-label="Swap project languages"
            title="Swap project languages before downstream work exists"
          >
            &#8646;
          </Button>
        </div>

        {/* History & Mux Export Triggers */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            onClick={() => void handleOpenVersionHistory()}
            variant="secondary"
            size="sm"
          >
            History
          </Button>
          <Button
            onClick={() => {
              setIsExportHistoryOpen((open) => !open);
              setIsHistoryOpen(false);
              setIsExportReadinessOpen(false);
            }}
            variant="secondary"
            size="sm"
            aria-expanded={isExportHistoryOpen}
            aria-controls="project-export-history"
          >
            Exports
          </Button>
          <Button
            onClick={() => {
              setIsExportReadinessOpen((open) => !open);
              setIsHistoryOpen(false);
              setIsExportHistoryOpen(false);
            }}
            variant="secondary"
            size="sm"
            aria-expanded={isExportReadinessOpen}
            aria-controls="project-export-readiness"
          >
            Readiness
          </Button>
          <Button
            onClick={history.undo}
            disabled={!history.canUndo}
            variant="secondary"
            size="sm"
          >
            Undo
          </Button>
          <Button
            onClick={history.redo}
            disabled={!history.canRedo}
            variant="secondary"
            size="sm"
          >
            Redo
          </Button>
          <div className="w-px h-6 bg-slate-800 mx-2" />
          <div className="flex items-center gap-2">
            <Button
              onClick={handleManualSave}
              variant="secondary"
              size="sm"
              className={`${
                dirtySegments.size > 0
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-200 hover:bg-amber-500/20'
                  : 'text-slate-400'
              }`}
              title="Save changes (Ctrl+S)"
            >
              {dirtySegments.size > 0 ? `Save (${dirtySegments.size})` : 'Saved'}
            </Button>
            {lastSavedAt && dirtySegments.size === 0 && (
              <span className="text-xs text-slate-600" title="Last saved">
                · {lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
          <div className="w-px h-6 bg-slate-800 mx-2" />
          <Button
            onClick={handleBuildDubOnly}
            disabled={buildState !== 'idle' || uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject}
            variant="secondary"
            size="sm"
            className="border-indigo-500 text-indigo-300 hover:bg-indigo-500/10"
            title="Replace audio with dubbed voice — no facial animation"
          >
            {buildMode === 'dub_only'
              ? buildState === 'syncing' ? 'Saving…' : 'Building…'
              : 'Dub only'}
          </Button>
          <Button
            onClick={handleBuildDubAndLipSync}
            disabled={buildState !== 'idle' || uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject}
            size="sm"
            title="Replace audio and animate lip movement to match translated speech"
          >
            {buildMode === 'dub_and_lipsync' && buildState === 'syncing'
              ? 'Saving…'
              : buildMode === 'dub_and_lipsync' && buildState === 'building'
                ? 'Building…'
                : 'Dub + Lip-Sync'}
          </Button>
        </div>
      </header>

      {(uploadState !== 'idle' || pipelineOperation) && (
        <div className="border-b border-slate-800 bg-slate-950/80 px-4 py-3 sm:px-6">
          <PipelineStatus
            mode="upstream"
            status={pipelineOperation?.status ?? 'in_progress'}
            progressPercent={uploadState === 'uploading' ? uploadProgressPercent : pipelineOperation?.progress_percent ?? 0}
            currentStage={uploadState === 'uploading'
              ? 'upload'
              : uploadState === 'transcribing'
                ? 'transcribe'
                : uploadState === 'translating'
                  ? 'translate'
                  : pipelineOperation?.current_stage ?? 'queued'}
            lastSuccessfulStage={pipelineOperation?.last_successful_stage}
            errorMessage={pipelineOperation?.error_message}
            hasMedia={Boolean(currentProject.mediaId)}
            hasTranscript={Boolean(currentProject.transcriptId)}
            translationCount={Object.keys(translations).length}
            segmentCount={segments.length}
          />
        </div>
      )}

      {isHistoryOpen && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-slate-950/60 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setIsHistoryOpen(false)}
        >
        <aside
          className="flex h-full w-full max-w-md flex-col overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="version-history-heading"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between">
            <h2 id="version-history-heading" className="text-sm font-bold text-white">Version history</h2>
            <Button
              onClick={() => setIsHistoryOpen(false)}
              variant="quiet"
              size="sm"
              className="min-h-7 px-2 text-slate-400"
              aria-label="Close version history"
              autoFocus
            >
              Close
            </Button>
          </div>
          {isLoadingHistory ? (
            <p className="mt-4 text-sm text-slate-400">Loading versions...</p>
          ) : projectVersions.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">No saved versions yet.</p>
          ) : (
            <ul className="mt-4 max-h-72 space-y-2 overflow-y-auto">
              {projectVersions.map((version) => (
                <li key={version.version} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="flex items-center justify-between text-sm text-slate-200">
                    <span>Version {version.version}</span>
                    <span className="text-xs text-slate-500">
                      {new Date(version.created_at).toLocaleString()}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
        </div>
      )}

      {isExportHistoryOpen && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-slate-950/60 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setIsExportHistoryOpen(false)}
        >
          <aside
            id="project-export-history"
            className="h-full w-full max-w-md overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label="Project outputs"
            onClick={(event) => event.stopPropagation()}
          >
          <div className="mb-2 flex justify-end">
            <Button
              onClick={() => setIsExportHistoryOpen(false)}
              variant="secondary"
              size="sm"
              autoFocus
            >
              Close exports
            </Button>
          </div>
          <ExportHistory projectId={currentProject.id} />
          </aside>
        </div>
      )}

      {isExportReadinessOpen && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-slate-950/60 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setIsExportReadinessOpen(false)}
        >
          <aside
            id="project-export-readiness"
            className="h-full w-full max-w-md overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label="Export readiness"
            onClick={(event) => event.stopPropagation()}
          >
          <div className="mb-2 flex justify-end">
            <Button
              onClick={() => setIsExportReadinessOpen(false)}
              variant="secondary"
              size="sm"
              autoFocus
            >
              Close readiness
            </Button>
          </div>
          <ExportReadiness
            hasDraftConflict={hasRemoteDraftConflict}
            hasMedia={Boolean(currentProject.mediaId)}
            hasTranscript={Boolean(currentProject.transcriptId)}
            dirtySegmentCount={dirtySegments.size}
            segments={segments}
            translations={translations}
          />
          </aside>
        </div>
      )}

      {hasRemoteDraftConflict && (
        <div className="border-b border-amber-700/40 bg-amber-950/40 px-6 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-amber-100">
              A newer draft was saved in another session. Autosave is paused to protect that work. Loading the server draft replaces this editor’s local edits only after the newer saved draft is fully loaded; already persisted translations remain safe.
            </p>
            <div className="flex shrink-0 gap-2">
              <Button
                onClick={() => {
                  // "Keep my edits": Accept the remote version number so autosave resumes
                  // from this point forward, without discarding local edits.
                  setHasRemoteDraftConflict(false);
                }}
                variant="secondary"
                size="sm"
              >
                Keep my edits
              </Button>
              <Button
                onClick={() => void loadProjectData()}
                disabled={isReloadingProject}
                variant="secondary"
                size="sm"
                className="shrink-0 border-amber-500/60 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20"
              >
                {isReloadingProject ? 'Reloading…' : 'Load server draft'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {activeBuildJob && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-6 py-3">
          <PipelineStatus
            mode={activeBuildJob.render_mode ?? buildMode ?? 'dub_only'}
            status={activeBuildJob.status}
            progressPercent={activeBuildJob.progress_percent}
            currentStage={activeBuildJob.current_stage}
            lastSuccessfulStage={activeBuildJob.last_successful_stage}
            errorMessage={activeBuildJob.error_message}
            hasMedia={Boolean(currentProject.mediaId)}
            hasTranscript={Boolean(currentProject.transcriptId)}
            translationCount={Object.keys(translations).length}
            segmentCount={segments.length}
          />
        </div>
      )}

      {!activeBuildJob && pipelineOperation?.operation_type === 'translation' && pipelineOperation.status === 'failed' && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-6 py-3" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-rose-400/30 bg-rose-400/10 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-rose-100">Translation needs attention</p>
              <p className="mt-1 text-xs text-rose-100/80">
                {pipelineOperation.error_message || 'The batch translation did not complete.'} Saved translations remain unchanged.
              </p>
            </div>
            <Button
              onClick={() => void retryFailedTranslation()}
              disabled={isRetryingPipelineOperation}
              variant="secondary"
              size="sm"
              className="shrink-0 border-rose-300/40 bg-rose-300/10 text-rose-50 hover:bg-rose-300/20"
            >
              {isRetryingPipelineOperation ? 'Retrying…' : 'Retry translation'}
            </Button>
          </div>
        </div>
      )}

      {!activeBuildJob && pipelineOperation?.operation_type === 'transcription' && pipelineOperation.status === 'failed' && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-6 py-3" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-rose-400/30 bg-rose-400/10 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-rose-100">Transcription needs attention</p>
              <p className="mt-1 text-xs text-rose-100/80">
                {pipelineOperation.error_message || 'The transcription did not complete.'} Saved project data remains unchanged.
              </p>
            </div>
            <Button
              onClick={() => void retryFailedTranscription()}
              disabled={isRetryingPipelineOperation}
              variant="secondary"
              size="sm"
              className="shrink-0 border-rose-300/40 bg-rose-300/10 text-rose-50 hover:bg-rose-300/20"
            >
              {isRetryingPipelineOperation ? 'Retrying…' : 'Retry transcription'}
            </Button>
          </div>
        </div>
      )}

      {/* Main Workspace Layout Grid */}
      <div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-3">
        {/* Left Grid: Transcript & Translation Edit Workspace */}
        <div className="order-last flex flex-col overflow-hidden border-r border-slate-800 md:order-first md:col-span-2">
          <div className="p-4 border-b border-slate-800 bg-slate-900/20 flex justify-between items-center">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">Dialogue Segments Script</h2>
            <div className="flex items-center gap-3">
              <label className={`cursor-pointer rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 focus-within:ring-2 focus-within:ring-indigo-300 focus-within:ring-offset-2 focus-within:ring-offset-slate-950 ${uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject ? 'pointer-events-none opacity-50' : ''}`}>
                {uploadState === 'uploading'
                  ? 'Uploading…'
                  : uploadState === 'transcribing'
                    ? 'Transcribing…'
                    : uploadState === 'translating'
                      ? 'Translating…'
                      : 'Upload & Transcribe'}
                <input aria-label="Upload audio or video and start transcription" type="file" accept="video/*,audio/*" className="hidden" onChange={handleMediaSelected} disabled={uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject} />
              </label>
              <span className="text-xs text-slate-500">{segments.length} segments loaded</span>
            </div>
          </div>

          <div ref={transcriptContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4">
            {segments.length === 0 ? (
              <div className="text-center text-slate-600 py-12">
                <p>No transcript segments available.</p>
                <p className="mt-2 text-sm">Upload an audio or video file to generate a transcript.</p>
              </div>
            ) : (
              segments.map((seg) => {
                const trans = translations[seg.id];
                const busy = segmentBusy[seg.id];

                // Risk indicators
                const isMissingTranslation = !trans;
                const isDurationOverflow = trans && trans.durationRatio > 1.15;
                const isDurationUnderflow = trans && trans.durationRatio < 0.75;
                const isLowConfidence = trans && trans.qualityScore < 0.5;
                const isMissingGeneratedAudio = trans && trans.generatedAudioStatus !== 'ready';
                const lipSyncStatus = lipSyncStatuses[seg.id];
                const hasLipSyncFailure = lipSyncStatus === 'failed';
                const hasRisk = isMissingTranslation || isDurationOverflow || isDurationUnderflow || isLowConfidence || isMissingGeneratedAudio || hasLipSyncFailure;

                return (
                  <div
                    key={seg.id}
                    data-segment-id={seg.id}
                    onClick={() => timeline.setSelectedSegmentId(seg.id)}
                    role="group"
                    aria-label={`Segment by ${seg.speakerTag} at ${timeline.formatTimecode(seg.startTimeSeconds)}`}
                    className={`border rounded-xl p-4 transition grid grid-cols-1 md:grid-cols-2 gap-4 cursor-pointer ${
                      timeline.selectedSegmentId === seg.id
                        ? 'border-indigo-500 bg-indigo-950/20 shadow-[0_0_15px_rgba(99,102,241,0.1)]'
                        : dirtySegments.has(seg.id)
                        ? 'border-amber-500/50 bg-amber-950/20'
                        : hasRisk
                        ? 'border-red-800/50 bg-red-950/10'
                        : 'border-slate-800 bg-slate-900/30 hover:border-slate-700 hover:bg-slate-900/50'
                    }`}
                  >
                    {/* Left column: source transcript */}
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              seekToTime(seg.startTimeSeconds, seg.id);
                              if (videoRef.current && videoRef.current.paused) {
                                void videoRef.current.play();
                              }
                            }}
                            className="text-[10px] bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500 hover:text-white px-2 py-0.5 rounded transition flex items-center gap-1 font-semibold uppercase tracking-wider"
                          >
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>
                            Play
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setLoopSegmentId((current) => current === seg.id ? null : seg.id);
                              seekToTime(seg.startTimeSeconds, seg.id);
                              if (videoRef.current?.paused) {
                                void videoRef.current.play();
                              }
                            }}
                            className={`text-[10px] px-2 py-0.5 rounded transition font-semibold uppercase tracking-wider ${
                              loopSegmentId === seg.id
                                ? 'bg-amber-500/30 text-amber-200'
                                : 'bg-slate-800 text-slate-500 hover:bg-slate-700 hover:text-slate-200'
                            }`}
                            aria-pressed={loopSegmentId === seg.id}
                            title="Loop this segment"
                          >
                            Loop
                          </button>
                          <span className="text-xs font-bold text-slate-500 uppercase">{seg.speakerTag}</span>
                          <span className="text-[10px] text-slate-600">{seg.durationSeconds.toFixed(1)}s</span>
                        </div>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            seekToTime(seg.startTimeSeconds, seg.id);
                          }}
                          className="text-xs font-mono text-slate-500 transition hover:text-white"
                        >
                          {timeline.formatTimecode(seg.startTimeSeconds)}
                        </button>
                      </div>
                      <textarea
                        dir={getTextDirection(currentProject.sourceLanguage)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-sm text-white focus:outline-none focus:border-indigo-700 resize-none h-16"
                        value={seg.text}
                        onChange={(e) => handleTextChange(seg.id, e.target.value)}
                      />
                    </div>

                    {/* Right column: translation + risk + actions */}
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs font-bold text-indigo-400 uppercase">Translation ({currentProject.targetLanguage})</span>
                          {/* Risk badges */}
                          {isMissingTranslation && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 font-semibold">Missing</span>
                          )}
                          {isDurationOverflow && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 font-semibold" title="Translation is too long — will be sped up">
                              Too long · {trans!.durationRatio.toFixed(2)}x
                            </span>
                          )}
                          {isDurationUnderflow && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 font-semibold" title="Translation is too short — may have silence gaps">
                              Too short · {trans!.durationRatio.toFixed(2)}x
                            </span>
                          )}
                          {isLowConfidence && !isMissingTranslation && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 font-semibold" title="Low translation confidence score">
                              Low confidence
                            </span>
                          )}
                          {hasLipSyncFailure && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 font-semibold" title="Lip-sync rendering failed for this segment">
                              Lip-sync failed
                            </span>
                          )}
                          {isMissingGeneratedAudio && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 font-semibold" title="Generated dubbed audio is not ready for this segment">
                              No audio
                            </span>
                          )}
                          {trans && !hasRisk && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-950 text-green-400 font-semibold">OK</span>
                          )}
                        </div>

                        {/* ⋯ Action menu */}
                        <div className="relative" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={() => setActiveActionMenu(activeActionMenu === seg.id ? null : seg.id)}
                            disabled={!!busy}
                            className="text-slate-500 hover:text-white px-1.5 py-0.5 rounded transition text-sm disabled:opacity-40"
                            title="Segment actions"
                          >
                            {busy === 'retranslating' ? 'Translating…' : busy === 'synthesizing' ? 'Synthesizing…' : '⋯'}
                          </button>
                          {activeActionMenu === seg.id && (
                            <div className="absolute right-0 top-6 z-20 w-44 rounded-xl border border-slate-700 bg-slate-900 shadow-xl py-1 text-sm">
                              <button
                                type="button"
                                onClick={() => void handleRetranslateSegment(seg.id)}
                                className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-800 transition"
                              >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5" /><path d="M20 4v7h-7" /></svg>
                                Retranslate
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleSynthesizeSegment(seg.id)}
                                disabled={!trans?.id}
                                className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-800 transition disabled:opacity-40"
                              >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 5.5a9 9 0 0 1 0 13" /></svg>
                                Regenerate audio
                              </button>
                              <div className="my-1 border-t border-slate-800" />
                              <button
                                type="button"
                                onClick={() => handleResetTranslation(seg.id)}
                                disabled={!originalTranslations[seg.id]}
                                className="w-full text-left px-3 py-2 text-red-400 hover:bg-slate-800 transition disabled:opacity-40"
                              >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
                                Reset to original
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                      <textarea
                        dir={getTextDirection(currentProject.targetLanguage)}
                        className={`w-full bg-slate-950 border rounded-lg p-2 text-sm text-indigo-100 focus:outline-none resize-none h-16 ${
                          dirtySegments.has(seg.id) ? 'border-amber-600/60 focus:border-amber-500' : 'border-slate-800 focus:border-indigo-700'
                        }`}
                        value={trans?.translatedText || ''}
                        onChange={(e) => handleTranslationChange(seg.id, e.target.value)}
                        placeholder={isMissingTranslation ? 'No translation yet — use ⋯ to retranslate' : 'Edit translation…'}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
          {uploadMessage && (
            <div className="px-6 pb-4" aria-live="polite" aria-atomic="true">
              <StatePanel title="Project update">{uploadMessage}</StatePanel>
            </div>
          )}
        </div>

        {/* Right Grid: Video Preview Player */}
        <div className="order-first flex flex-col justify-between overflow-hidden bg-slate-950 p-6 md:order-last">
          <div className="border border-slate-800 rounded-xl bg-slate-900 aspect-video flex items-center justify-center text-slate-500 overflow-hidden">
            {renderedVideoUrl ? (
              <video
                key={renderedVideoUrl}
                ref={videoRef}
                src={renderedVideoUrl}
                controls
                aria-label={`${currentProject.targetLanguage.toUpperCase()} dubbed video preview`}
                className="h-full w-full"
                onError={() => void refreshRenderedVideoUrl()}
              >
                Your browser does not support embedded video playback.
              </video>
            ) : (
              'Preview Media Player Placeholder'
            )}
          </div>

          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Export Output</h3>
                <p className="mt-2 text-sm text-slate-300">
                  {renderedVideoUrl
                    ? `Your ${currentProject.targetLanguage.toUpperCase()} dubbed video preview is ready.`
                    : 'Run dub and lip-sync to generate a preview and downloadable output.'}
                </p>
              </div>
              {renderedVideoUrl && (
                <div className="flex shrink-0 gap-2">
                  <a
                    href={renderedVideoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500"
                  >
                    Open video
                  </a>
                  <button
                    type="button"
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={async () => {
                      try {
                        const response = await fetch(renderedVideoUrl);
                        const blob = await response.blob();
                        const objectUrl = URL.createObjectURL(blob);
                        const anchor = document.createElement('a');
                        anchor.href = objectUrl;
                        anchor.download = `${currentProject.name}-${currentProject.targetLanguage}.mp4`;
                        document.body.appendChild(anchor);
                        anchor.click();
                        document.body.removeChild(anchor);
                        URL.revokeObjectURL(objectUrl);
                      } catch {
                        window.open(renderedVideoUrl, '_blank');
                      }
                    }}
                  >
                    Download video
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="border border-slate-800 rounded-xl p-4 bg-slate-900/30 mt-6 flex-1 flex flex-col justify-between gap-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Segment Timeline</h3>
              <span className="text-xs text-slate-500">Click a segment bar to seek the preview player.</span>
            </div>
            <label className="flex items-center gap-3 text-xs text-slate-500">
              <span className="shrink-0">Fine seek</span>
              <input
                type="range"
                aria-label="Fine seek preview timeline"
                min={0}
                max={totalDurationSeconds || 1}
                step={0.1}
                value={Math.min(timeline.currentTimeSeconds, totalDurationSeconds || 1)}
                onChange={(event) => seekToTime(Number(event.target.value))}
                disabled={segments.length === 0 || totalDurationSeconds === 0}
                className="w-full accent-indigo-500 disabled:opacity-40"
              />
            </label>
            <div
              className="relative h-32 rounded-lg border border-slate-800 bg-slate-950 p-3"
              onPointerDown={(event) => {
                isScrubbingRef.current = true;
                event.currentTarget.setPointerCapture(event.pointerId);
                seekFromTrackPointer(event.clientX, event.currentTarget);
              }}
              onPointerMove={(event) => {
                if (isScrubbingRef.current) {
                  seekFromTrackPointer(event.clientX, event.currentTarget);
                }
              }}
              onPointerUp={(event) => {
                isScrubbingRef.current = false;
                event.currentTarget.releasePointerCapture(event.pointerId);
              }}
              onPointerCancel={() => {
                isScrubbingRef.current = false;
              }}
            >
              {segments.length === 0 || totalDurationSeconds === 0 ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-600">
                  Upload media to populate the review timeline.
                </div>
              ) : (
                <div className="relative flex h-full items-end gap-1">
                  <div className="pointer-events-none absolute inset-0 opacity-70">
                    <WaveformCanvas
                      data={waveformData}
                      viewStart={0}
                      viewEnd={totalDurationSeconds}
                      width={1200}
                      height={96}
                    />
                  </div>
                  {segments.map((segment) => {
                    const widthPercent = Math.max(8, (segment.durationSeconds / totalDurationSeconds) * 100);
                    const isActive = timeline.selectedSegmentId === segment.id;
                    return (
                      <button
                        key={segment.id}
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          seekToTime(segment.startTimeSeconds, segment.id);
                        }}
                        aria-label={`Seek to segment ${timeline.formatTimecode(segment.startTimeSeconds)} by ${segment.speakerTag}`}
                        aria-current={isActive ? 'true' : undefined}
                        title={`${timeline.formatTimecode(segment.startTimeSeconds)} • ${segment.speakerTag}`}
                        className={`min-w-[2rem] rounded-md border transition ${
                          isActive
                            ? 'border-indigo-400 bg-indigo-500/40'
                            : 'border-slate-700 bg-slate-800 hover:border-slate-500 hover:bg-slate-700'
                        }`}
                        style={{ width: `${widthPercent}%`, height: `${Math.max(30, Math.min(96, 28 + segment.durationSeconds * 18))}px` }}
                      />
                    );
                  })}
                </div>
              )}
            </div>
            <div className="sticky bottom-0 z-10 -mx-3 flex items-center justify-between border-t border-slate-800 bg-slate-900/95 px-3 py-3 backdrop-blur md:static md:mx-0 md:border-0 md:bg-transparent md:px-0 md:py-0 md:backdrop-blur-none">
              <div>
                <span className="text-sm font-mono text-slate-400">{timeline.formatTimecode(timeline.currentTimeSeconds)}</span>
                {selectedSegment && (
                  <p className="mt-1 text-xs text-slate-500">
                    Focused segment: {selectedSegment.speakerTag} at {timeline.formatTimecode(selectedSegment.startTimeSeconds)}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  if (!videoRef.current) {
                    timeline.setPlaying(!timeline.isPlaying);
                    return;
                  }

                  if (videoRef.current.paused) {
                    void videoRef.current.play();
                  } else {
                    videoRef.current.pause();
                  }
                }}
                aria-label={timeline.isPlaying ? 'Pause preview' : 'Play preview'}
                aria-pressed={timeline.isPlaying}
                className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-full p-2 w-10 h-10 flex items-center justify-center transition"
              >
                {timeline.isPlaying ? '⏸' : '▶'}
              </button>
            </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500">Compare audio</span>
                <button
                  type="button"
                  onClick={() => setComparisonMode('original')}
                  disabled={!sourceMediaUrl?.startsWith('http')}
                  aria-pressed={comparisonMode === 'original'}
                  className={`rounded border px-2 py-1 text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${comparisonMode === 'original' ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200' : 'border-slate-700 text-slate-400 hover:border-slate-500'}`}
                >
                  Original
                </button>
                <button
                  type="button"
                  onClick={() => setComparisonMode('dubbed')}
                  disabled={!renderedVideoUrl}
                  aria-pressed={comparisonMode === 'dubbed'}
                  className={`rounded border px-2 py-1 text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${comparisonMode === 'dubbed' ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200' : 'border-slate-700 text-slate-400 hover:border-slate-500'}`}
                >
                  Dubbed
                </button>
                <button
                  type="button"
                  onClick={playComparisonSegment}
                  disabled={!selectedSegment || !hasComparisonUrl}
                  className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Play selected segment
                </button>
              </div>
          </div>

          <audio
            ref={comparisonAudioRef}
            src={comparisonUrl ?? undefined}
            onError={() => {
              if (comparisonMode === 'original') {
                void refreshSourceMediaUrl();
              } else {
                void refreshRenderedVideoUrl();
              }
            }}
            onTimeUpdate={(event) => {
              if (selectedSegment && event.currentTarget.currentTime >= selectedSegment.endTimeSeconds) {
                event.currentTarget.pause();
                event.currentTarget.currentTime = selectedSegment.startTimeSeconds;
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}
