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
import { getProjectDraftConflictDetail, projectService } from '../../../services/projectService';
import { mapUserFacingError } from '../../../services/userFacingErrors';

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
    videoFilename: project?.originalVideoUrl ?? draft.mediaReferences.videoFilename,
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
  currentLipsyncJobId: project?.currentLipsyncJobId,
  lastRenderedVideoPath: project?.lastRenderedVideoPath,
  lastRenderedVideoUrl: project?.lastRenderedVideoUrl,
  originalVideoUrl: project?.originalVideoUrl ?? draft.mediaReferences.videoFilename,
  dubbedAudioUrl: project?.dubbedAudioUrl,
});

export default function TranslationEditor() {
  const params = useParams();
  const router = useRouter();
  const projectId = params?.projectId as string;

  const { currentProject, setCurrentProject } = useProjectStore();
  const { segments, setSegments, updateSegmentText } = useMediaStore();
  const { translations, setTranslations, updateTranslationText } = useTranslationStore();
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'transcribing' | 'translating'>('idle');
  const [buildState, setBuildState] = useState<'idle' | 'syncing' | 'building'>('idle');
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
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
            videoFilename: currentProject.originalVideoUrl ?? 'source_video.mp4',
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
    try {
      let draft: HeygenXFile | null = null;
      let backendProject: Project | null = null;
      let nextBaseProjectUpdatedAt: string | null = null;

      if (projectService.hasProjectApiScope()) {
        try {
          await projectService.bootstrapAuthContext();
          backendProject = await projectService.getProject(projectId);
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

          await storageService.saveDraft(draft);
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

      const hydratedProject = buildProjectFromDraft(draft, backendProject);

      setCurrentProject(hydratedProject);
      setRenderedVideoUrl(backendProject?.lastRenderedVideoUrl ?? hydratedProject.lastRenderedVideoUrl ?? null);
      // Clear conflict state and stale upload message together before
      // updating segments/translations so the banner disappears atomically.
      setHasRemoteDraftConflict(false);
      setUploadMessage(null);
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

  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement) {
      return;
    }

    const syncTime = () => timeline.setCurrentTimeSeconds(videoElement.currentTime);
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
  }, [renderedVideoUrl, timeline]);

  const persistDraft = useCallback(async ({
    projectOverride,
    segmentsOverride,
    translationsOverride,
    videoFilename,
    durationSeconds,
    transcriptId,
    mediaId,
    baseProjectUpdatedAtOverride,
  }: {
    projectOverride?: typeof currentProject;
    segmentsOverride?: TranscriptSegment[];
    translationsOverride?: TranslatedSegment[];
    videoFilename?: string;
    durationSeconds?: number;
    transcriptId?: string;
    mediaId?: string;
    baseProjectUpdatedAtOverride?: string | null;
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
        videoFilename: videoFilename ?? project.originalVideoUrl ?? 'source_video.mp4',
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
  const totalDurationSeconds = useMemo(
    () => segments.reduce((acc, segment) => Math.max(acc, segment.endTimeSeconds), 0),
    [segments],
  );

  const seekToTime = useCallback((seconds: number, segmentId?: string) => {
    timeline.setCurrentTimeSeconds(seconds);
    if (segmentId) {
      timeline.setSelectedSegmentId(segmentId);
    }

    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
    }
  }, [timeline]);

  const applyProjectPatch = useCallback(async ({
    name,
    sourceLanguage,
    targetLanguage,
    status,
    transcriptId,
    mediaId,
    originalVideoUrl,
    dubbedAudioUrl,
  }: {
    name?: string;
    sourceLanguage?: string;
    targetLanguage?: string;
    status?: Project['status'];
    transcriptId?: string;
    mediaId?: string;
    originalVideoUrl?: string;
    dubbedAudioUrl?: string;
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

      const hydratedProject: Project = {
        ...updatedProject,
        originalVideoUrl: originalVideoUrl ?? currentProject.originalVideoUrl,
        dubbedAudioUrl: dubbedAudioUrl ?? currentProject.dubbedAudioUrl,
      };

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
      ...(originalVideoUrl !== undefined ? { originalVideoUrl } : {}),
      ...(dubbedAudioUrl !== undefined ? { dubbedAudioUrl } : {}),
      updatedAt: new Date().toISOString(),
    };

    setCurrentProject(hydratedProject);
    setBaseProjectUpdatedAt(hydratedProject.updatedAt);
    return hydratedProject;
  }, [currentProject, hasRemoteDraftConflict, setCurrentProject]);

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
      updateTranslationText(segId, result.translatedText);
      setDirtySegments((prev) => new Set(prev).add(segId));
    } catch (err) {
      console.error('Retranslate failed:', err);
    } finally {
      setSegmentBusy((prev) => { const n = { ...prev }; delete n[segId]; return n; });
    }
  }, [currentProject, segments, updateTranslationText]);

  const handleSynthesizeSegment = useCallback(async (segId: string) => {
    const trans = translations[segId];
    if (!trans?.id) return;
    setSegmentBusy((prev) => ({ ...prev, [segId]: 'synthesizing' }));
    setActiveActionMenu(null);
    try {
      await projectService.synthesizeSegment(trans.id);
    } catch (err) {
      console.error('Synthesize segment failed:', err);
    } finally {
      setSegmentBusy((prev) => { const n = { ...prev }; delete n[segId]; return n; });
    }
  }, [translations]);

  const handleResetTranslation = useCallback((segId: string) => {
    const original = originalTranslations[segId];
    if (original !== undefined) {
      updateTranslationText(segId, original);
      setDirtySegments((prev) => { const n = new Set(prev); n.delete(segId); return n; });
    }
    setActiveActionMenu(null);
  }, [originalTranslations, updateTranslationText]);

  const handleManualSave = useCallback(async () => {
    await persistDraft();
  }, [persistDraft]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        void handleManualSave();
      }
      if (e.key === ' ' && e.target instanceof HTMLElement && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) void videoRef.current.play();
          else videoRef.current.pause();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleManualSave]);

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
    await persistDraft({ translationsOverride: persistedTranslations });
    return persistedTranslations;
  };

  const pollForLipSyncCompletion = async (jobId: string) => {
    let latestStatus: any = null;

    for (let attempt = 0; attempt < 180; attempt += 1) {
      latestStatus = await projectService.getExportStatus(jobId);

      if (latestStatus?.status === 'failed') {
        throw new Error(latestStatus?.error_message || 'Dub & Lip-Sync failed. Check the backend logs for details.');
      }

      if (latestStatus?.status === 'completed') {
        return latestStatus;
      }

      setUploadMessage(
        `Dub & Lip-Sync ${String(latestStatus?.status || 'in progress').replace('_', ' ')}…`,
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
      setBuildState('syncing');
      setRenderedVideoUrl(null);
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

      setUploadMessage(withLipSync ? 'Building dubbed audio and syncing lip motion…' : 'Building dubbed audio…');
      const completedJob = await pollForLipSyncCompletion(job.job_id);

      if (completedJob?.output_video_url) {
        setRenderedVideoUrl(completedJob.output_video_url);
        const refreshedProject = await projectService.getProject(projectForBuild.id).catch(() => null);
        if (refreshedProject) {
          setCurrentProject({
            ...refreshedProject,
            originalVideoUrl: projectForBuild.originalVideoUrl,
            dubbedAudioUrl: projectForBuild.dubbedAudioUrl,
          });
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
    if (file.size > 100 * 1024 * 1024) {
      setUploadMessage('This first UI integration supports files up to 100 MB. Larger files need the resumable-upload flow.');
      return;
    }

    try {
      const projectForUpload = await ensureCanonicalProjectForWrite();
      if (!projectForUpload) {
        throw new Error('Project context is unavailable. Reload the project and try again.');
      }

      setUploadState('uploading');
      setUploadMessage(`Uploading ${file.name}…`);
      const media = await projectService.uploadMedia(file);
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
        const updatedProject = (await applyProjectPatch({
          status: 'processing',
          transcriptId: job.transcript_id,
          mediaId: media.media_id,
          originalVideoUrl: media.filename,
        })) ?? currentProject;

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
      <header className="h-14 border-b border-slate-800 bg-slate-900/50 px-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push('/')} className="text-slate-400 hover:text-white transition">
            &larr; Projects
          </button>
          <span className="text-slate-600">/</span>
          <h1 className="text-md font-bold text-white">{currentProject.name}</h1>
          <span className="bg-slate-800 text-slate-400 text-xs px-2 py-0.5 rounded font-mono uppercase">
            {currentProject.sourceLanguage} &rarr; {currentProject.targetLanguage}
          </span>
        </div>

        {/* History & Mux Export Triggers */}
        <div className="flex items-center gap-3">
          <button
            onClick={history.undo}
            disabled={!history.canUndo}
            className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition text-sm"
          >
            Undo
          </button>
          <button
            onClick={history.redo}
            disabled={!history.canRedo}
            className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition text-sm"
          >
            Redo
          </button>
          <div className="w-px h-6 bg-slate-800 mx-2" />
          <div className="flex items-center gap-2">
            <button
              onClick={handleManualSave}
              className={`px-3 py-1.5 rounded transition text-sm font-semibold border ${
                dirtySegments.size > 0
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-200 hover:bg-amber-500/20'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white'
              }`}
              title="Save changes (Ctrl+S)"
            >
              {dirtySegments.size > 0 ? `Save (${dirtySegments.size})` : 'Saved'}
            </button>
            {lastSavedAt && dirtySegments.size === 0 && (
              <span className="text-xs text-slate-600" title="Last saved">
                · {lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
          <div className="w-px h-6 bg-slate-800 mx-2" />
          <button
            onClick={handleBuildDubOnly}
            disabled={buildState !== 'idle' || uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject}
            className="border border-indigo-500 text-indigo-300 hover:bg-indigo-500/10 px-4 py-1.5 rounded-lg text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed"
            title="Replace audio with dubbed voice — no facial animation"
          >
            {buildState !== 'idle' ? '…' : 'Dub only'}
          </button>
          <button
            onClick={handleBuildDubAndLipSync}
            disabled={buildState !== 'idle' || uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed"
            title="Replace audio and animate lip movement to match translated speech"
          >
            {buildState === 'syncing'
              ? 'Saving…'
              : buildState === 'building'
                ? 'Building…'
                : 'Dub + Lip-Sync'}
          </button>
        </div>
      </header>

      {hasRemoteDraftConflict && (
        <div className="border-b border-amber-700/40 bg-amber-950/40 px-6 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-amber-100">
              A newer draft was saved in another session. Autosave is paused to protect that work.
            </p>
            <div className="flex shrink-0 gap-2">
              <button
                onClick={() => {
                  // "Keep my edits": Accept the remote version number so autosave resumes
                  // from this point forward, without discarding local edits.
                  setHasRemoteDraftConflict(false);
                }}
                className="rounded-lg border border-slate-600 bg-slate-800/60 px-3 py-1.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-700"
              >
                Keep my edits
              </button>
              <button
                onClick={() => void loadProjectData()}
                disabled={isReloadingProject}
                className="shrink-0 rounded-lg border border-amber-500/60 bg-amber-500/10 px-3 py-1.5 text-sm font-semibold text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isReloadingProject ? 'Reloading…' : 'Load server draft'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Workspace Layout Grid */}
      <div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-3">
        {/* Left Grid: Transcript & Translation Edit Workspace */}
        <div className="md:col-span-2 border-r border-slate-800 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-800 bg-slate-900/20 flex justify-between items-center">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">Dialogue Segments Script</h2>
            <div className="flex items-center gap-3">
              <label className={`cursor-pointer bg-slate-800 hover:bg-slate-700 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition ${uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject ? 'pointer-events-none opacity-50' : ''}`}>
                {uploadState === 'uploading'
                  ? 'Uploading…'
                  : uploadState === 'transcribing'
                    ? 'Transcribing…'
                    : uploadState === 'translating'
                      ? 'Translating…'
                      : 'Upload & Transcribe'}
                <input type="file" accept="video/*,audio/*" className="hidden" onChange={handleMediaSelected} disabled={uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject} />
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
                const hasRisk = isMissingTranslation || isDurationOverflow || isDurationUnderflow || isLowConfidence;

                return (
                  <div
                    key={seg.id}
                    data-segment-id={seg.id}
                    onClick={() => timeline.setSelectedSegmentId(seg.id)}
                    className={`border rounded-xl p-4 transition grid grid-cols-2 gap-4 cursor-pointer ${
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
                            ▶ Play
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
                            {busy === 'retranslating' ? '⟳ Translating…' : busy === 'synthesizing' ? '⟳ Synthesizing…' : '⋯'}
                          </button>
                          {activeActionMenu === seg.id && (
                            <div className="absolute right-0 top-6 z-20 w-44 rounded-xl border border-slate-700 bg-slate-900 shadow-xl py-1 text-sm">
                              <button
                                type="button"
                                onClick={() => void handleRetranslateSegment(seg.id)}
                                className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-800 transition"
                              >
                                ↻ Retranslate
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleSynthesizeSegment(seg.id)}
                                disabled={!trans?.id}
                                className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-800 transition disabled:opacity-40"
                              >
                                🔊 Regenerate audio
                              </button>
                              <div className="my-1 border-t border-slate-800" />
                              <button
                                type="button"
                                onClick={() => handleResetTranslation(seg.id)}
                                disabled={!originalTranslations[seg.id]}
                                className="w-full text-left px-3 py-2 text-red-400 hover:bg-slate-800 transition disabled:opacity-40"
                              >
                                ✕ Reset to original
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                      <textarea
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
            <div className="px-6 pb-4 text-sm text-slate-400" role="status">{uploadMessage}</div>
          )}
        </div>

        {/* Right Grid: Video Preview Player */}
        <div className="bg-slate-950 p-6 flex flex-col justify-between overflow-hidden">
          <div className="border border-slate-800 rounded-xl bg-slate-900 aspect-video flex items-center justify-center text-slate-500 overflow-hidden">
            {renderedVideoUrl ? (
              <video
                key={renderedVideoUrl}
                ref={videoRef}
                src={renderedVideoUrl}
                controls
                className="h-full w-full"
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
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
              {segments.length === 0 || totalDurationSeconds === 0 ? (
                <div className="flex h-24 items-center justify-center text-xs text-slate-600">
                  Upload media to populate the review timeline.
                </div>
              ) : (
                <div className="flex h-24 items-end gap-1">
                  {segments.map((segment) => {
                    const widthPercent = Math.max(8, (segment.durationSeconds / totalDurationSeconds) * 100);
                    const isActive = timeline.selectedSegmentId === segment.id;
                    return (
                      <button
                        key={segment.id}
                        type="button"
                        onClick={() => seekToTime(segment.startTimeSeconds, segment.id)}
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
            <div className="flex justify-between items-center">
              <div>
                <span className="text-sm font-mono text-slate-400">{timeline.formatTimecode(timeline.currentTimeSeconds)}</span>
                {selectedSegment && (
                  <p className="mt-1 text-xs text-slate-500">
                    Focused segment: {selectedSegment.speakerTag} at {timeline.formatTimecode(selectedSegment.startTimeSeconds)}
                  </p>
                )}
              </div>
              <button
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
                className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-full p-2 w-10 h-10 flex items-center justify-center transition"
              >
                {timeline.isPlaying ? '⏸' : '▶'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
