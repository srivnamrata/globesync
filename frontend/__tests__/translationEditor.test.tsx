import React, { act } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/apiClient';
import { draftFixture, projectFixture } from '../test/fixtures';
import { useMediaStore } from '../store/mediaStore';
import { useProjectStore, type Project } from '../store/projectStore';
import { useTranslationStore } from '../store/translationStore';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const service = vi.hoisted(() => ({
  hasProjectApiScope: vi.fn(),
  bootstrapAuthContext: vi.fn(),
  getProject: vi.fn(),
  getPipelineOperation: vi.fn(),
  getMedia: vi.fn(),
  getMediaAudio: vi.fn(),
  getExportStatus: vi.fn(),
  getProjectDraft: vi.fn(),
  buildLocalDraftFromProject: vi.fn(),
  seedProjectDraft: vi.fn(),
  saveProjectDraft: vi.fn(),
  fetchTranslations: vi.fn(),
  updateProject: vi.fn(),
  getProjectVersions: vi.fn(),
  getProjectVersion: vi.fn(),
  uploadMedia: vi.fn(),
  uploadMediaResumable: vi.fn(),
  startTranscription: vi.fn(),
  getTranscription: vi.fn(),
  triggerProjectTranslation: vi.fn(),
  retryPipelineOperation: vi.fn(),
  retryTranscriptionOperation: vi.fn(),
  updateTranslationSegment: vi.fn(),
  triggerTtsSynthesis: vi.fn(),
  triggerLipSync: vi.fn(),
  triggerDubOnly: vi.fn(),
  createProjectShell: vi.fn(),
}));
const storage = vi.hoisted(() => ({
  getDraft: vi.fn(),
  saveDraft: vi.fn(),
  deleteDraft: vi.fn(),
}));
const autoSave = vi.hoisted(() => ({
  callback: undefined as undefined | (() => Promise<void>),
}));
const timeline = vi.hoisted(() => ({
  selectedSegmentId: null as string | null,
  currentTimeSeconds: 0,
  isPlaying: false,
  zoomLevel: 100,
  setSelectedSegmentId: vi.fn(),
  setCurrentTimeSeconds: vi.fn(),
  setPlaying: vi.fn(),
  setZoomLevel: vi.fn(),
  secondsToPixels: vi.fn(),
  pixelsToSeconds: vi.fn(),
  formatTimecode: vi.fn(() => '00:00:00.00'),
}));

vi.mock('next/navigation', () => ({
  useParams: () => ({ projectId: projectFixture.id }),
  useRouter: () => router,
}));
vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return { ...actual, projectService: service };
});
vi.mock('../services/storageService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/storageService')>();
  return { ...actual, storageService: storage };
});
vi.mock('../hooks/useProject', () => ({
  useProjectAutoSave: (callback: () => Promise<void>) => {
    autoSave.callback = callback;
  },
}));
vi.mock('../hooks/useTimeline', () => ({ useTimeline: () => timeline }));
vi.mock('../hooks/useHistory', () => ({
  useHistory: () => ({
    canUndo: false,
    canRedo: false,
    undo: vi.fn(),
    redo: vi.fn(),
    pushHistory: vi.fn(),
  }),
}));
vi.mock('../components/WaveformRenderer/WaveformCanvas', () => ({
  default: () => <div data-testid="waveform" />,
}));
vi.mock('../components/ExportHub/ExportHistory', () => ({
  default: ({ projectId }: { projectId: string }) => <div>Exports for {projectId}</div>,
}));
vi.mock('../components/ExportHub/ExportReadiness', () => ({
  ExportReadiness: ({ hasDraftConflict }: { hasDraftConflict: boolean }) => (
    <div>Readiness conflict: {String(hasDraftConflict)}</div>
  ),
}));
vi.mock('../components/ExportHub/PipelineStatus', () => ({
  PipelineStatus: ({ status, currentStage }: { status: string; currentStage: string }) => (
    <div data-testid="pipeline-status">{status}:{currentStage}</div>
  ),
}));

import TranslationEditor from '../app/editor/[projectId]/page';

const baseProject: Project = {
  ...projectFixture,
  mediaId: undefined,
  transcriptId: undefined,
  mediaFilename: undefined,
  mediaDurationSeconds: undefined,
};

const loadedSegment = {
  id: 'segment-1',
  sequenceOrder: 1,
  startTimeSeconds: 0,
  endTimeSeconds: 2,
  durationSeconds: 2,
  speakerTag: 'Speaker 1',
  text: 'Hello',
  confidence: 0.95,
};

const loadedTranslation = {
  id: 'translation-1',
  transcriptSegmentId: 'segment-1',
  translatedText: 'Hola',
  originalDurationMs: 2000,
  estimatedDurationMs: 2000,
  durationRatio: 1,
  speedAdjustmentFactor: 1,
  qualityScore: 0.95,
  generatedAudioStatus: 'ready',
  status: 'completed' as const,
};

function draftWithContent() {
  return {
    ...draftFixture,
    projectMetadata: { ...draftFixture.projectMetadata },
    mediaReferences: {
      ...draftFixture.mediaReferences,
      originalTranscriptSegments: [loadedSegment],
      transcriptId: undefined,
      mediaId: undefined,
    },
    translations: [loadedTranslation],
  };
}

describe('TranslationEditor workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    autoSave.callback = undefined;
    timeline.selectedSegmentId = null;
    useProjectStore.setState({ currentProject: null, projects: [], isLoading: false, error: null });
    useMediaStore.setState({ metadata: null, segments: [], isLoading: false });
    useTranslationStore.setState({ translations: {}, targetLanguage: 'es', isLoading: false });
    service.hasProjectApiScope.mockReturnValue(true);
    service.bootstrapAuthContext.mockResolvedValue({ workspaceId: 'workspace-1', actorUserId: 'user-1' });
    service.getProject.mockResolvedValue(baseProject);
    service.getPipelineOperation.mockResolvedValue(null);
    service.getProjectDraft.mockResolvedValue({
      draft: draftWithContent(),
      version: 2,
      baseProjectUpdatedAt: baseProject.updatedAt,
    });
    service.saveProjectDraft.mockResolvedValue({
      version: 3,
      base_project_updated_at: baseProject.updatedAt,
    });
    service.getProjectVersions.mockResolvedValue([]);
    service.fetchTranslations.mockResolvedValue([]);
    service.buildLocalDraftFromProject.mockReturnValue(draftWithContent());
    storage.getDraft.mockResolvedValue(draftWithContent());
    storage.saveDraft.mockResolvedValue(undefined);
    storage.deleteDraft.mockResolvedValue(undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('hydrates a recoverable draft and opens history, exports, and readiness panels', async () => {
    const user = userEvent.setup();
    render(<TranslationEditor />);

    expect(screen.getByText('Loading translation project resources...')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Launch film' })).toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Hola')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'History' }));
    expect(await screen.findByRole('dialog', { name: 'Version history' }))
      .toHaveTextContent('No saved versions yet.');
    await user.click(screen.getByRole('button', { name: 'Close version history' }));

    await user.click(screen.getByRole('button', { name: 'Exports' }));
    expect(screen.getByRole('dialog', { name: 'Project outputs' }))
      .toHaveTextContent(`Exports for ${projectFixture.id}`);
    await user.click(screen.getByRole('button', { name: 'Close exports' }));

    await user.click(screen.getByRole('button', { name: 'Readiness' }));
    expect(screen.getByRole('dialog', { name: 'Export readiness' }))
      .toHaveTextContent('Readiness conflict: false');
  });

  it('defaults preview playback to the original media until a dubbed render exists', async () => {
    render(<TranslationEditor />);

    await screen.findByRole('heading', { name: 'Launch film' });
    expect(screen.getByRole('button', { name: 'Original' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Dubbed' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Dubbed' })).toBeDisabled();
  });

  it('does not leave a queued message behind when lip-sync is unavailable', async () => {
    const user = userEvent.setup();
    const projectWithAssets: Project = {
      ...baseProject,
      mediaId: 'media-1',
      transcriptId: 'transcript-1',
      targetLanguage: 'es',
    };
    const draftWithAssets = {
      ...draftWithContent(),
      mediaReferences: {
        ...draftWithContent().mediaReferences,
        mediaId: 'media-1',
        transcriptId: 'transcript-1',
      },
    };

    service.getProject.mockResolvedValue(projectWithAssets);
    service.getProjectDraft.mockResolvedValue({
      draft: draftWithAssets,
      version: 2,
      baseProjectUpdatedAt: projectWithAssets.updatedAt,
    });
    service.getMedia.mockResolvedValue({
      media_id: 'media-1',
      filename: 'source.mp4',
      media_type: 'video/mp4',
      filesize_bytes: 1024,
      duration_seconds: 2,
      status: 'ready',
      storage_path: 'gs://bucket/source.mp4',
      created_at: projectWithAssets.createdAt,
      media_url: 'https://cdn.test/source.mp4',
    });
    service.fetchTranslations.mockResolvedValue([loadedTranslation]);
    service.updateTranslationSegment.mockResolvedValue(loadedTranslation);
    service.updateProject.mockResolvedValue(projectWithAssets);
    service.triggerLipSync.mockRejectedValue(new ApiError(
      'Dub + Lip-Sync is not configured for this deployment. Add a valid Replicate API token, or use Dub only.',
      503,
      { detail: 'Dub + Lip-Sync is not configured for this deployment. Add a valid Replicate API token, or use Dub only.' },
    ));

    render(<TranslationEditor />);
    await screen.findByRole('heading', { name: 'Launch film' });

    await user.click(screen.getByRole('button', { name: 'Dub + Lip-Sync' }));

    await screen.findByText('Dub + Lip-Sync is not configured for this deployment. Ask an administrator to add the Replicate credential, or use Dub only.');
    expect(screen.queryByText('Queuing dub and lip-sync pipeline…')).not.toBeInTheDocument();
  });

  it('preserves local edits on a genuine conflict and supports both resolution choices', async () => {
    const user = userEvent.setup();
    render(<TranslationEditor />);
    await screen.findByRole('heading', { name: 'Launch film' });

    const conflictDetail = {
      code: 'DRAFT_VERSION_CONFLICT',
      message: 'stale',
      project_id: projectFixture.id,
      client_version: 2,
      server_version: 4,
      server_updated_at: '2026-01-03T00:00:00.000Z',
      last_saved_by_user_id: 'user-2',
    };
    service.saveProjectDraft.mockRejectedValueOnce(
      new ApiError('stale', 409, { error: conflictDetail }),
    );

    await act(async () => {
      await autoSave.callback?.();
    });
    expect(screen.getAllByText(/saved project draft changed/)).toHaveLength(2);
    expect(storage.saveDraft).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Dub only' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Keep editor edits' }));
    expect(screen.queryByRole('button', { name: 'Keep editor edits' })).not.toBeInTheDocument();

    service.saveProjectDraft.mockRejectedValueOnce(
      new ApiError('stale', 409, { error: conflictDetail }),
    );
    await act(async () => {
      await autoSave.callback?.();
    });
    const callsBeforeReload = service.getProjectDraft.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Load saved draft' }));
    await waitFor(() => expect(service.getProjectDraft.mock.calls.length).toBeGreaterThan(callsBeforeReload));
  });

  it('uses the freshly updated project timestamp through upload, transcription, and first translation', async () => {
    const updatedProject = {
      ...projectFixture,
      updatedAt: '2026-04-05T06:07:08.000Z',
    };
    service.uploadMedia.mockResolvedValue({
      media_id: 'media-1',
      filename: 'clip.mp4',
      media_type: 'video/mp4',
      filesize_bytes: 5,
      duration_seconds: 2,
      media_url: 'https://cdn.test/clip.mp4',
      status: 'uploaded',
    });
    service.startTranscription.mockResolvedValue({ transcript_id: 'transcript-1' });
    service.getTranscription.mockResolvedValue({
      transcript_id: 'transcript-1',
      status: 'completed',
      segments: [{
        id: 'segment-1',
        sequence_order: 1,
        start_time: 0,
        end_time: 2,
        duration: 2,
        speaker: 'Speaker 1',
        text: 'Hello',
        confidence: 0.9,
      }],
    });
    service.updateProject.mockResolvedValue(updatedProject);
    service.triggerProjectTranslation.mockResolvedValue({
      job_id: 'translation-job',
      transcript_id: 'transcript-1',
      target_language: 'es',
      status: 'queued',
      message: 'Queued',
    });
    service.fetchTranslations.mockResolvedValue([loadedTranslation]);

    render(<TranslationEditor />);
    await screen.findByRole('heading', { name: 'Launch film' });
    vi.useFakeTimers();
    const input = screen.getByLabelText('Upload audio or video and start transcription');
    fireEvent.change(input, {
      target: { files: [new File(['video'], 'clip.mp4', { type: 'video/mp4' })] },
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    vi.useRealTimers();
    await waitFor(() => expect(service.triggerProjectTranslation).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/Translation complete/)).toBeInTheDocument());

    const workflowSaves = service.saveProjectDraft.mock.calls.slice(-2);
    expect(workflowSaves).toHaveLength(2);
    expect(workflowSaves.every((call) =>
      call[2].baseProjectUpdatedAt === updatedProject.updatedAt)).toBe(true);
    expect(screen.queryByText(/saved project draft changed/)).not.toBeInTheDocument();
  });

  it('rejects unsupported uploads without touching network services', async () => {
    render(<TranslationEditor />);
    await screen.findByRole('heading', { name: 'Launch film' });
    fireEvent.change(screen.getByLabelText('Upload audio or video and start transcription'), {
      target: { files: [new File(['text'], 'notes.txt', { type: 'text/plain' })] },
    });

    expect(await screen.findByText('Choose an audio or video file.')).toBeInTheDocument();
    expect(service.uploadMedia).not.toHaveBeenCalled();
  });

  it('renders failed translation status and retries the operation', async () => {
    const user = userEvent.setup();
    const projectWithPipeline = {
      ...baseProject,
      currentPipelineOperationId: 'operation-1',
    };
    service.getProject.mockResolvedValue(projectWithPipeline);
    service.getPipelineOperation.mockResolvedValue({
      id: 'operation-1',
      project_id: projectFixture.id,
      workspace_id: 'workspace-1',
      transcript_id: 'transcript-1',
      operation_type: 'translation',
      target_language: 'es',
      status: 'failed',
      progress_percent: 20,
      current_stage: 'translate',
      last_successful_stage: 'transcribe',
      message: null,
      error_message: 'Translation worker stopped.',
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
    });
    service.retryPipelineOperation.mockResolvedValue({
      operation_id: 'operation-2',
      operation_type: 'translation',
      status: 'queued',
      message: 'Retry queued',
    });

    render(<TranslationEditor />);
    expect(await screen.findByText('Translation needs attention')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-status')).toHaveTextContent('failed:translate');
    await user.click(screen.getByRole('button', { name: 'Retry translation' }));
    expect(service.retryPipelineOperation).toHaveBeenCalledWith('operation-1');
    expect(await screen.findByText('Retry queued')).toBeInTheDocument();
  });
});
