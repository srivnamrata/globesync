import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import type { TranscriptSegment } from '../store/mediaStore';
import type { Project } from '../store/projectStore';
import type { TranslatedSegment } from '../store/translationStore';
import { projectService, type PipelineOperationStatus } from '../services/projectService';
import { mapUserFacingError } from '../services/userFacingErrors';

export type ActiveBuildJob = {
    job_id: string;
    render_mode?: 'dub_only' | 'dub_and_lipsync';
    status: string;
    progress_percent: number;
    current_stage: string;
    last_successful_stage?: string | null;
    error_message?: string | null;
};

type PersistDraftOptions = {
    translationsOverride?: TranslatedSegment[];
    checkpointReason?: string;
};

type UseBuildPipelineOptions = {
    projectId: string;
    currentProject: Project | null;
    segments: TranscriptSegment[];
    translations: Record<string, TranslatedSegment>;
    persistDraft: (options?: PersistDraftOptions) => Promise<void>;
    applyProjectStatus: (status: Project['status']) => Promise<Project | null>;
    ensureCanonicalProjectForWrite: () => Promise<Project | null>;
    pipelineOperation: PipelineOperationStatus | null;
    setPipelineOperation: Dispatch<SetStateAction<PipelineOperationStatus | null>>;
    setCurrentProject: (project: Project) => void;
    setTranslations: (translations: TranslatedSegment[]) => void;
    setRenderedVideoUrl: (url: string | null) => void;
    setComparisonMode: (mode: 'original' | 'dubbed') => void;
    setUploadMessage: (message: string | null) => void;
    setUploadState: (state: 'idle' | 'uploading' | 'transcribing' | 'translating') => void;
};

export function useBuildPipeline({
    projectId,
    currentProject,
    segments,
    translations,
    persistDraft,
    applyProjectStatus,
    ensureCanonicalProjectForWrite,
    pipelineOperation,
    setPipelineOperation,
    setCurrentProject,
    setTranslations,
    setRenderedVideoUrl,
    setComparisonMode,
    setUploadMessage,
    setUploadState,
}: UseBuildPipelineOptions) {
    const [buildState, setBuildState] = useState<'idle' | 'syncing' | 'building'>('idle');
    const [buildMode, setBuildMode] = useState<'dub_only' | 'dub_and_lipsync' | null>(null);
    const [activeBuildJob, setActiveBuildJob] = useState<ActiveBuildJob | null>(null);
    const [isRetryingPipelineOperation, setIsRetryingPipelineOperation] = useState(false);
    const [lipSyncStatuses, setLipSyncStatuses] = useState<Record<string, string>>({});

    useEffect(() => {
        setActiveBuildJob(null);
        setBuildState('idle');
        setBuildMode(null);
        setLipSyncStatuses({});
    }, [projectId]);

    const syncTranslationsBeforeBuild = useCallback(async (): Promise<TranslatedSegment[]> => {
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
    }, [persistDraft, setTranslations, translations]);

    const pollForBuildCompletion = useCallback(async (jobId: string, withLipSync: boolean) => {
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

            if (attempt < 179) {
                await new Promise((resolve) => setTimeout(resolve, 1000));
            }
        }

        return latestStatus;
    }, [setUploadMessage]);

    const retryFailedTranslation = useCallback(async () => {
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
    }, [pipelineOperation, setUploadMessage, setUploadState]);

    const retryFailedTranscription = useCallback(async () => {
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
    }, [pipelineOperation, setUploadMessage, setUploadState]);

    const runBuildPipeline = useCallback(async (withLipSync: boolean) => {
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
            const nextRenderMode = withLipSync ? 'dub_and_lipsync' : 'dub_only';
            setBuildMode(nextRenderMode);
            setBuildState('syncing');
            setLipSyncStatuses({});
            setActiveBuildJob({
                job_id: 'pending',
                render_mode: nextRenderMode,
                status: 'queued',
                progress_percent: 0,
                current_stage: 'queued',
                last_successful_stage: null,
                error_message: null,
            });
            setUploadMessage('Saving translated segment edits…');
            const persistedTranslations = await syncTranslationsBeforeBuild();

            if (persistedTranslations.length < segments.length) {
                throw new Error('Not all translated segments are ready yet.');
            }

            const projectForBuild = (await applyProjectStatus('processing')) ?? currentProject;
            const canonicalProjectForBuild = await ensureCanonicalProjectForWrite();
            const effectiveProjectForBuild = canonicalProjectForBuild ?? projectForBuild;

            if (canonicalProjectForBuild) {
                setCurrentProject(canonicalProjectForBuild);
            }

            if (!effectiveProjectForBuild.mediaId || !effectiveProjectForBuild.transcriptId) {
                throw new Error('Reload the latest workspace draft before building the dubbed preview.');
            }

            setBuildState('building');
            setUploadMessage(withLipSync ? 'Checking Dub + Lip-Sync availability…' : 'Queuing dub-only pipeline…');

            const trigger = withLipSync ? projectService.triggerLipSync : projectService.triggerDubOnly;
            const job = await trigger.call(
                projectService,
                effectiveProjectForBuild.mediaId,
                effectiveProjectForBuild.transcriptId,
                effectiveProjectForBuild.targetLanguage,
                effectiveProjectForBuild.id,
            );
            setActiveBuildJob({
                job_id: job.job_id,
                render_mode: nextRenderMode,
                status: 'queued',
                progress_percent: 0,
                current_stage: 'queued',
                last_successful_stage: null,
                error_message: null,
            });

            setUploadMessage(withLipSync ? 'Starting Dub + Lip-Sync build…' : 'Queuing dub-only pipeline…');
            const completedJob = await pollForBuildCompletion(job.job_id, withLipSync);
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
                setComparisonMode('dubbed');
                const refreshedProject = await projectService.getProject(effectiveProjectForBuild.id).catch(() => null);
                if (refreshedProject) {
                    setCurrentProject(refreshedProject);
                } else {
                    await applyProjectStatus('completed');
                }

                if (effectiveProjectForBuild.transcriptId) {
                    const refreshedTranslations = await projectService
                        .fetchTranslations(effectiveProjectForBuild.transcriptId, effectiveProjectForBuild.targetLanguage)
                        .catch(() => null);
                    if (refreshedTranslations && refreshedTranslations.length > 0) {
                        setTranslations(refreshedTranslations);
                    }
                }

                if (!withLipSync) {
                    setUploadMessage('Dub complete. Preview is ready — download the dubbed video below.');
                } else {
                    const skippedSegments = Array.isArray(completedJob?.segments_metadata)
                        ? completedJob.segments_metadata.filter((s: { render_status?: string }) => s.render_status && s.render_status !== 'completed')
                        : [];
                    if (skippedSegments.length === 0) {
                        setUploadMessage('Dub & Lip-Sync complete. Preview is ready — download the dubbed video below.');
                    } else if (skippedSegments.length === segments.length) {
                        setUploadMessage('Dub completed, but lip-sync could not be applied because no usable face was detected in the source footage. You can still preview and download the dubbed video below.');
                    } else {
                        setUploadMessage(`Dub completed. Lip-sync was skipped for ${skippedSegments.length} segment${skippedSegments.length === 1 ? '' : 's'}, so parts of the video may keep the original facial motion. You can still preview and download the dubbed video below.`);
                    }
                }
            } else {
                await applyProjectStatus('completed');
                setUploadMessage('Build completed successfully, but the preview link is not available yet. Reload the project in a few moments to fetch the latest export.');
            }
        } catch (error) {
            setActiveBuildJob((job) => (job?.job_id === 'pending' ? null : job));
            setUploadMessage(mapUserFacingError(error, withLipSync ? 'Unable to build dub and lip-sync output.' : 'Unable to build dubbed output.'));
        } finally {
            setBuildState('idle');
            setBuildMode(null);
        }
    }, [
        applyProjectStatus,
        currentProject,
        ensureCanonicalProjectForWrite,
        pollForBuildCompletion,
        segments,
        setComparisonMode,
        setCurrentProject,
        setRenderedVideoUrl,
        setTranslations,
        setUploadMessage,
        syncTranslationsBeforeBuild,
        translations,
    ]);

    return {
        activeBuildJob,
        buildMode,
        buildState,
        handleBuildDubAndLipSync: () => void runBuildPipeline(true),
        handleBuildDubOnly: () => void runBuildPipeline(false),
        isRetryingPipelineOperation,
        lipSyncStatuses,
        pipelineOperation,
        retryFailedTranscription,
        retryFailedTranslation,
        setPipelineOperation,
    };
}
