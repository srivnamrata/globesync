'use client';

import React, { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useProjectStore, type Project } from '../../../store/projectStore';
import { useMediaStore, type TranscriptSegment } from '../../../store/mediaStore';
import { useTranslationStore, type TranslatedSegment } from '../../../store/translationStore';
import { useProjectAutoSave } from '../../../hooks/useProject';
import { useTimeline } from '../../../hooks/useTimeline';
import { useHistory } from '../../../hooks/useHistory';
import { useBuildPipeline } from '../../../hooks/useBuildPipeline';
import { useDialogAccessibility } from '../../../hooks/useDialogAccessibility';
import { useEditorProjectData } from '../../../hooks/useEditorProjectData';
import { useSegmentActions } from '../../../hooks/useSegmentActions';
import { projectService, type ProjectVersionSummary } from '../../../services/projectService';
import { mapUserFacingError } from '../../../services/userFacingErrors';
import type { WaveformData } from '../../../utils/waveformProcessing';
import { Button, StatePanel, StatusBadge } from '../../../components/ui';
import ExportHistory from '../../../components/ExportHub/ExportHistory';
import { ExportReadiness } from '../../../components/ExportHub/ExportReadiness';
import { PipelineStatus } from '../../../components/ExportHub/PipelineStatus';
import MediaPreviewPanel from '../../../components/editor/MediaPreviewPanel';
import SegmentCard from '../../../components/editor/SegmentCard';
import { formatDateTime } from '../../../utils/formatDateTime';
import {
  formatTranslationCompletionMessage,
  pollForTranslations,
} from '../../../utils/editorWorkflow';

function deriveFilenameFromUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    const pathname = new URL(url).pathname;
    const candidate = decodeURIComponent(pathname.split('/').filter(Boolean).pop() ?? '');
    return candidate || null;
  } catch {
    return null;
  }
}

function hasFileExtension(name: string): boolean {
  return /\.[^./]+$/i.test(name);
}

function ensureFilenameExtension(name: string, extension: string): string {
  return hasFileExtension(name) ? name : `${name}${extension}`;
}

export default function TranslationEditor() {
  const params = useParams();
  const router = useRouter();
  const rawProjectId = params?.projectId;
  const projectId = typeof rawProjectId === 'string' && rawProjectId.trim().length > 0
    ? rawProjectId
    : null;

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950 text-slate-400">
        Invalid project URL.
      </div>
    );
  }

  const { currentProject, setCurrentProject } = useProjectStore();
  const { segments, setSegments, updateSegmentText } = useMediaStore();
  const { translations, setTranslations, updateTranslationText } = useTranslationStore();
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'transcribing' | 'translating'>('idle');
  const [uploadProgressPercent, setUploadProgressPercent] = useState(0);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [dirtySegments, setDirtySegments] = useState<Set<string>>(new Set());
  const [originalTranslations, setOriginalTranslations] = useState<Record<string, string>>({});
  const [loopSegmentId, setLoopSegmentId] = useState<string | null>(null);
  const [waveformData, setWaveformData] = useState<WaveformData | null>(null);
  const [comparisonMode, setComparisonMode] = useState<'original' | 'dubbed'>('original');
  const [projectVersions, setProjectVersions] = useState<ProjectVersionSummary[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isExportHistoryOpen, setIsExportHistoryOpen] = useState(false);
  const [isExportReadinessOpen, setIsExportReadinessOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const isScrubbingRef = useRef(false);
  const transcriptContainerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const timeline = useTimeline();
  const history = useHistory();
  const isAnyDialogOpen = isHistoryOpen || isExportHistoryOpen || isExportReadinessOpen;
  const closeOpenDialogs = useCallback(() => {
    setIsHistoryOpen(false);
    setIsExportHistoryOpen(false);
    setIsExportReadinessOpen(false);
  }, []);

  useDialogAccessibility({
    isOpen: isAnyDialogOpen,
    onRequestClose: closeOpenDialogs,
  });

  const handleRedirectHome = useCallback(() => {
    router.push('/');
  }, [router]);

  const handleReplaceProject = useCallback((nextProjectId: string) => {
    router.replace(`/editor/${nextProjectId}`);
  }, [router]);

  const {
    applyProjectPatch,
    applyProjectStatus,
    dismissRemoteDraftConflict,
    ensureCanonicalProjectForWrite,
    hasRemoteDraftConflict,
    isReloadingProject,
    lastSavedAt,
    loadProjectData,
    persistDraft,
    pipelineOperation: initialPipelineOperation,
    refreshRenderedVideoUrl,
    refreshSourceMediaUrl,
    renderedVideoUrl,
    setPipelineOperation,
    setRenderedVideoUrl,
    setSourceMediaUrl,
    sourceMediaUrl,
  } = useEditorProjectData({
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
    onRedirectHome: handleRedirectHome,
    onReplaceProject: handleReplaceProject,
  });

  useEffect(() => {
    setComparisonMode('original');
  }, [projectId]);

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

  const seekFromTrackPointer = useCallback((clientX: number, element: HTMLElement) => {
    const bounds = element.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width));
    seekToTime(ratio * totalDurationSeconds);
  }, [seekToTime, totalDurationSeconds]);

  const playComparisonSegment = useCallback(() => {
    if (!selectedSegment || !videoRef.current) {
      return;
    }

    videoRef.current.currentTime = selectedSegment.startTimeSeconds;
    void videoRef.current.play();
  }, [selectedSegment]);

  const handleTogglePreviewPlayback = useCallback(() => {
    if (!videoRef.current) {
      timeline.setPlaying(!timeline.isPlaying);
      return;
    }

    if (videoRef.current.paused) {
      void videoRef.current.play();
    } else {
      videoRef.current.pause();
    }
  }, [timeline]);

  const handleTimelinePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    isScrubbingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    seekFromTrackPointer(event.clientX, event.currentTarget);
  }, [seekFromTrackPointer]);

  const handleTimelinePointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (isScrubbingRef.current) {
      seekFromTrackPointer(event.clientX, event.currentTarget);
    }
  }, [seekFromTrackPointer]);

  const handleTimelinePointerUp = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    isScrubbingRef.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const handleTimelinePointerCancel = useCallback(() => {
    isScrubbingRef.current = false;
  }, []);

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



  const {
    activeBuildJob,
    buildMode,
    buildState,
    handleBuildDubAndLipSync,
    handleBuildDubOnly,
    isRetryingPipelineOperation,
    lipSyncStatuses,
    pipelineOperation,
    retryFailedTranscription,
    retryFailedTranslation,
  } = useBuildPipeline({
    projectId,
    currentProject,
    segments,
    translations,
    persistDraft,
    applyProjectStatus,
    ensureCanonicalProjectForWrite,
    pipelineOperation: initialPipelineOperation,
    setPipelineOperation,
    setCurrentProject,
    setTranslations,
    setRenderedVideoUrl,
    setComparisonMode,
    setUploadMessage,
    setUploadState,
  });

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

  const {
    activeActionMenu,
    handleResetTranslation,
    handleRetranslateSegment,
    handleSynthesizeSegment,
    registerActionMenuContainer,
    segmentBusy,
    toggleActionMenu,
  } = useSegmentActions({
    currentProject,
    segments,
    translations,
    originalTranslations,
    setTranslations,
    getLatestTranslations: () => useTranslationStore.getState().translations,
    updateTranslationText,
    setDirtySegments,
    setUploadMessage,
  });

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
        const transcript = await projectService.getTranscription(job.transcript_id);
        if (transcript.status === 'failed') {
          throw new Error('Transcription failed. Check the backend and Celery worker logs.');
        }
        if (transcript.status !== 'completed') {
          setUploadMessage(`Transcription ${transcript.status.replace('_', ' ')}…`);
          await new Promise((resolve) => setTimeout(resolve, 1000));
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

        const fetchedTranslations = await pollForTranslations({
          transcriptId: job.transcript_id,
          targetLanguage: updatedProject.targetLanguage,
          expectedCount: loadedSegments.length,
          fetchTranslations: (id, language) => projectService.fetchTranslations(id, language),
          intervalMs: 1000,
        });

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
        }
        setUploadMessage(formatTranslationCompletionMessage(
          fetchedTranslations.length,
          loadedSegments.length,
        ));
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

  const previewUrl = comparisonMode === 'original' ? sourceMediaUrl : renderedVideoUrl;
  const previewDownloadName = comparisonMode === 'original'
    ? (
      currentProject.mediaFilename
      ?? deriveFilenameFromUrl(sourceMediaUrl)
      ?? `${currentProject.name}-original`
    )
    : ensureFilenameExtension(
      deriveFilenameFromUrl(renderedVideoUrl)
      ?? `${currentProject.name}-${currentProject.targetLanguage}`,
      '.mp4',
    );

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
          <div className="w-px h-6 bg-slate-800 mx-2" />
          <div className="flex items-center gap-2">
            <Button
              onClick={handleManualSave}
              variant="secondary"
              size="sm"
              className={`${dirtySegments.size > 0
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
                        {formatDateTime(version.created_at)}
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
              A newer saved draft is available. Autosave is paused to avoid overwriting it. Keep current edits to continue here, or load the latest saved draft to refresh the editor. Saved translated segments are safe.
            </p>
            <div className="flex shrink-0 gap-2">
              <Button
                onClick={dismissRemoteDraftConflict}
                variant="secondary"
                size="sm"
              >
                Keep editor edits
              </Button>
              <Button
                onClick={() => void loadProjectData()}
                disabled={isReloadingProject}
                variant="secondary"
                size="sm"
                className="shrink-0 border-amber-500/60 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20"
              >
                {isReloadingProject ? 'Reloading…' : 'Load saved draft'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {activeBuildJob && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-4 py-2 sm:px-6">
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
      <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-[minmax(0,3fr)_minmax(380px,2fr)] xl:grid-cols-[minmax(0,1.45fr)_minmax(520px,1fr)]">
        {/* Left Grid: Transcript & Translation Edit Workspace */}
        <div className="order-last flex min-w-0 flex-col overflow-hidden border-r border-slate-800 md:order-first">
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

          {uploadMessage && (
            <div className="border-b border-slate-800 px-6 py-4" aria-live="polite" aria-atomic="true">
              <StatePanel title="Project update">{uploadMessage}</StatePanel>
            </div>
          )}

          <div ref={transcriptContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4">
            {segments.length === 0 ? (
              <div className="text-center text-slate-600 py-12">
                <p>No transcript segments available.</p>
                <p className="mt-2 text-sm">Upload an audio or video file to generate a transcript.</p>
              </div>
            ) : (
              segments.map((seg) => {
                const trans = translations[seg.id];

                return (
                  <SegmentCard
                    key={seg.id}
                    currentProject={currentProject}
                    segment={seg}
                    translation={trans}
                    lipSyncStatus={lipSyncStatuses[seg.id]}
                    isDirty={dirtySegments.has(seg.id)}
                    isLooping={loopSegmentId === seg.id}
                    isSelected={timeline.selectedSegmentId === seg.id}
                    isActionMenuOpen={activeActionMenu === seg.id}
                    isBusy={segmentBusy[seg.id]}
                    canResetTranslation={originalTranslations[seg.id] !== undefined}
                    formatTimecode={timeline.formatTimecode}
                    actionMenuContainerRef={registerActionMenuContainer(seg.id)}
                    onSelect={() => timeline.setSelectedSegmentId(seg.id)}
                    onSeek={() => seekToTime(seg.startTimeSeconds, seg.id)}
                    onPlay={() => {
                      seekToTime(seg.startTimeSeconds, seg.id);
                      if (videoRef.current?.paused) {
                        void videoRef.current.play();
                      }
                    }}
                    onToggleLoop={() => {
                      setLoopSegmentId((current) => current === seg.id ? null : seg.id);
                      seekToTime(seg.startTimeSeconds, seg.id);
                      if (videoRef.current?.paused) {
                        void videoRef.current.play();
                      }
                    }}
                    onSourceTextChange={(text) => handleTextChange(seg.id, text)}
                    onTranslationTextChange={(text) => handleTranslationChange(seg.id, text)}
                    onToggleActionMenu={() => toggleActionMenu(seg.id)}
                    onRetranslate={() => void handleRetranslateSegment(seg.id)}
                    onSynthesize={() => void handleSynthesizeSegment(seg.id)}
                    onResetTranslation={() => handleResetTranslation(seg.id)}
                  />
                );
              })
            )}
          </div>
        </div>

        {/* Right Grid: Video Preview Player */}
        <MediaPreviewPanel
          currentProject={currentProject}
          comparisonMode={comparisonMode}
          sourceMediaUrl={sourceMediaUrl}
          renderedVideoUrl={renderedVideoUrl}
          previewUrl={previewUrl}
          previewDownloadName={previewDownloadName}
          waveformData={waveformData}
          totalDurationSeconds={totalDurationSeconds}
          segments={segments}
          selectedSegment={selectedSegment}
          selectedSegmentId={timeline.selectedSegmentId}
          currentTimeSeconds={timeline.currentTimeSeconds}
          isPlaying={timeline.isPlaying}
          videoRef={videoRef}
          formatTimecode={timeline.formatTimecode}
          onComparisonModeChange={setComparisonMode}
          onRefreshSourceMediaUrl={() => {
            void refreshSourceMediaUrl();
          }}
          onRefreshRenderedVideoUrl={() => {
            void refreshRenderedVideoUrl();
          }}
          onSeek={seekToTime}
          onTogglePlayback={handleTogglePreviewPlayback}
          onPlaySelectedSegment={playComparisonSegment}
          onTimelinePointerDown={handleTimelinePointerDown}
          onTimelinePointerMove={handleTimelinePointerMove}
          onTimelinePointerUp={handleTimelinePointerUp}
          onTimelinePointerCancel={handleTimelinePointerCancel}
        />
      </div>
    </div>
  );
}
