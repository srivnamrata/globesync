'use client';

import React, { ChangeEvent, useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useProjectStore, type Project } from '../../../store/projectStore';
import { useMediaStore, type TranscriptSegment } from '../../../store/mediaStore';
import { useTranslationStore, type TranslatedSegment } from '../../../store/translationStore';
import { storageService, type HeygenXFile } from '../../../services/storageService';
import { useProjectAutoSave } from '../../../hooks/useProject';
import { useTimeline } from '../../../hooks/useTimeline';
import { useHistory } from '../../../hooks/useHistory';
import { getProjectDraftConflictDetail, projectService } from '../../../services/projectService';

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

  const timeline = useTimeline();
  const history = useHistory();

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
            console.warn('No server-side draft found yet, seeded editor from project metadata:', draftError);
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
      setBaseProjectUpdatedAt(nextBaseProjectUpdatedAt ?? hydratedProject.updatedAt);
      setHasRemoteDraftConflict(false);
      setUploadMessage(null);

      const draftSegments = draft.mediaReferences.originalTranscriptSegments || [];
      const draftTranslations = draft.translations || [];

      setSegments(draftSegments);
      setTranslations(draftTranslations);

      if (
        draft.mediaReferences.transcriptId &&
        draftSegments.length > 0 &&
        draftTranslations.length < draftSegments.length
      ) {
        try {
          const fetchedTranslations = await projectService.fetchTranslations(
            draft.mediaReferences.transcriptId,
            hydratedProject.targetLanguage,
          );

          if (fetchedTranslations.length > 0) {
            setTranslations(fetchedTranslations);
            await storageService.saveDraft({
              ...draft,
              translations: fetchedTranslations,
            });
          }
        } catch (translationErr) {
          console.warn('No persisted translations available yet for this transcript:', translationErr);
        }
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

  const persistDraft = async ({
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

    await storageService.saveDraft(nextDraft);

    if (projectService.hasProjectApiScope() && !hasRemoteDraftConflict) {
      try {
        const remoteDraft = await projectService.saveProjectDraft(project.id, nextDraft, {
          version: remoteDraftVersion ?? 1,
          baseProjectUpdatedAt: baseProjectUpdatedAtOverride ?? baseProjectUpdatedAt,
        });
        setRemoteDraftVersion(remoteDraft.version);
        setBaseProjectUpdatedAt(remoteDraft.base_project_updated_at ?? project.updatedAt);
        setHasRemoteDraftConflict(false);
      } catch (error) {
        const conflictDetail = getProjectDraftConflictDetail(error);
        if (conflictDetail) {
          setHasRemoteDraftConflict(true);
          setUploadMessage('A newer backend draft exists for this project. Reload the latest backend state before saving more changes. Your browser draft is still cached locally for recovery.');
          console.warn('Project draft save hit a version conflict; kept the local IndexedDB draft for recovery:', conflictDetail);
          return;
        }

        console.warn('Failed to persist project draft to backend; kept local IndexedDB draft as fallback:', error);
      }
    }
  };

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

  const handleBuildDubAndLipSync = async () => {
    if (!currentProject?.id || !currentProject.mediaId || !currentProject.transcriptId) {
      setUploadMessage('Upload and transcribe media before building dub and lip-sync.');
      return;
    }

    if (segments.length === 0) {
      setUploadMessage('Transcript segments are required before building dub and lip-sync.');
      return;
    }

    if (Object.keys(translations).length < segments.length) {
      setUploadMessage('Wait until all translated segments are available before building dub and lip-sync.');
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
      setUploadMessage('Queuing dub and lip-sync pipeline…');
      const job = await projectService.triggerLipSync(
        projectForBuild.mediaId!,
        projectForBuild.transcriptId!,
        projectForBuild.targetLanguage,
        projectForBuild.id,
      );

      setUploadMessage('Dub and lip-sync queued. Building dubbed audio…');
      const completedJob = await pollForLipSyncCompletion(job.job_id);

      if (completedJob?.output_video_url) {
        setRenderedVideoUrl(completedJob.output_video_url);
        await applyProjectPatch({ status: 'completed' });
        setUploadMessage('Dub & Lip-Sync complete. Preview is ready.');
      } else {
        await applyProjectPatch({ status: 'completed' });
        setUploadMessage('Dub & Lip-Sync completed successfully.');
      }
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'Unable to build dub and lip-sync output.');
    } finally {
      setBuildState('idle');
    }
  };

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
      setUploadState('uploading');
      setUploadMessage(`Uploading ${file.name}…`);
      const media = await projectService.uploadMedia(file);
      setUploadState('transcribing');
      setUploadMessage('Upload complete. Starting transcription…');
      const job = await projectService.startTranscription(media.media_id, currentProject.sourceLanguage);

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
      setUploadMessage(error instanceof Error ? error.message : 'Unable to upload and transcribe the media.');
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
    <div className="h-full flex flex-col bg-slate-950 text-white">
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
          <button
            onClick={handleBuildDubAndLipSync}
            disabled={buildState !== 'idle' || uploadState !== 'idle' || hasRemoteDraftConflict || isReloadingProject}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {buildState === 'syncing'
              ? 'Saving Translations…'
              : buildState === 'building'
                ? 'Building…'
                : 'Build Dub & Lip-Sync'}
          </button>
        </div>
      </header>

      {hasRemoteDraftConflict && (
        <div className="border-b border-amber-700/40 bg-amber-950/40 px-6 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-amber-100">
              A newer backend draft was saved in another session. Reload the latest project state to resume backend saves. Your browser draft remains cached locally until you reload.
            </p>
            <button
              onClick={() => void loadProjectData()}
              disabled={isReloadingProject}
              className="shrink-0 rounded-lg border border-amber-500/60 bg-amber-500/10 px-3 py-1.5 text-sm font-semibold text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isReloadingProject ? 'Reloading…' : 'Reload latest draft'}
            </button>
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

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {segments.length === 0 ? (
              <div className="text-center text-slate-600 py-12">
                <p>No transcript segments available.</p>
                <p className="mt-2 text-sm">Upload an audio or video file to generate a transcript.</p>
              </div>
            ) : (
              segments.map((seg) => {
                const trans = translations[seg.id];
                return (
                  <div
                    key={seg.id}
                    onClick={() => timeline.setSelectedSegmentId(seg.id)}
                    className={`border rounded-xl p-4 transition grid grid-cols-2 gap-4 cursor-pointer ${
                      timeline.selectedSegmentId === seg.id
                        ? 'border-indigo-500 bg-indigo-950/10'
                        : 'border-slate-800 bg-slate-900/30'
                    }`}
                  >
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-bold text-slate-500 uppercase">{seg.speakerTag}</span>
                        <span className="text-xs font-mono text-slate-500">{timeline.formatTimecode(seg.startTimeSeconds)}</span>
                      </div>
                      <textarea
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-sm text-white focus:outline-none focus:border-slate-700 resize-none h-16"
                        value={seg.text}
                        onChange={(e) => handleTextChange(seg.id, e.target.value)}
                      />
                    </div>

                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-bold text-indigo-400 uppercase">Translation ({currentProject.targetLanguage})</span>
                        {trans && (
                          <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                            trans.durationRatio > 1.1 ? 'bg-red-950 text-red-400' : 'bg-green-950 text-green-400'
                          }`}>
                            Speed: {trans.speedAdjustmentFactor}x
                          </span>
                        )}
                      </div>
                      <textarea
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-sm text-indigo-100 focus:outline-none focus:border-slate-700 resize-none h-16"
                        value={trans?.translatedText || ''}
                        onChange={(e) => handleTranslationChange(seg.id, e.target.value)}
                        placeholder="Translating segment text..."
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

          <div className="border border-slate-800 rounded-xl p-4 bg-slate-900/30 mt-6 flex-1 flex flex-col justify-between">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Audio Waveform Timeline</h3>
            <div className="h-24 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-center text-slate-600 text-xs">
              Zoom Level: {timeline.zoomLevel}%
            </div>
            <div className="flex justify-between items-center mt-4">
              <span className="text-sm font-mono text-slate-400">{timeline.formatTimecode(timeline.currentTimeSeconds)}</span>
              <button
                onClick={() => timeline.setPlaying(!timeline.isPlaying)}
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
