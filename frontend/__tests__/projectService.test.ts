import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/apiClient';
import { authContextFixture, draftFixture, projectFixture } from '../test/fixtures';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
}));
const auth = vi.hoisted(() => ({
  hasBootstrapConfig: vi.fn(),
  ensureAuthenticatedContext: vi.fn(),
  getCachedContext: vi.fn(),
}));

vi.mock('../services/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/apiClient')>();
  return { ...actual, apiClient: api };
});
vi.mock('../services/authService', () => ({ authService: auth }));

import {
  getProjectDraftConflictDetail,
  ProjectService,
  type TranslationItemResponse,
} from '../services/projectService';

const apiProject = {
  id: projectFixture.id,
  workspace_id: 'workspace-1',
  owner_user_id: 'user-1',
  created_by_user_id: 'user-1',
  name: projectFixture.name,
  status: 'draft' as const,
  source_language: 'en',
  target_language: 'es',
  active_translation_language: 'es',
  media_file_id: 'media-1',
  media_filename: 'launch.mp4',
  media_duration_seconds: 42,
  pipeline_stage: 'translation',
  pipeline_status: 'in_progress',
  pipeline_progress_percent: 35,
  pipeline_error_message: null,
  transcript_id: 'transcript-1',
  latest_draft_version: 2,
  last_rendered_video_gcs_path: 'renders/final.mp4',
  current_lipsync_job_id: 'render-1',
  current_export_job_id: null,
  current_pipeline_operation_id: 'operation-1',
  slug: null,
  archived_at: null,
  created_at: projectFixture.createdAt,
  updated_at: projectFixture.updatedAt,
};

const translationItem = (overrides: Partial<TranslationItemResponse> = {}): TranslationItemResponse => ({
  translation_id: 'translation-1',
  segment_id: 'segment-1',
  sequence_order: 1,
  speaker_tag: 'Speaker 1',
  start_time_seconds: 0,
  end_time_seconds: 4,
  source_text: 'Hello',
  translated_text: 'Hola',
  original_duration_ms: 4000,
  estimated_duration_ms: 4400,
  duration_ratio: 1.1,
  duration_status: 'good',
  iterations_count: 1,
  confidence_score: 0.95,
  is_cached: false,
  is_user_edited: false,
  generated_audio_status: 'completed',
  created_at: '2026-01-01T00:00:00.000Z',
  ...overrides,
});

describe('ProjectService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('NEXT_PUBLIC_WORKSPACE_ID', 'workspace-1');
    vi.stubEnv('NEXT_PUBLIC_ACTOR_USER_ID', 'user-1');
    auth.hasBootstrapConfig.mockReturnValue(false);
    auth.getCachedContext.mockReturnValue(null);
    auth.ensureAuthenticatedContext.mockResolvedValue(authContextFixture);
  });

  it('uses configured or authenticated project scopes', async () => {
    const service = new ProjectService();
    expect(service.hasProjectApiScope()).toBe(true);
    await expect(service.bootstrapAuthContext()).resolves.toEqual({
      workspaceId: 'workspace-1',
      actorUserId: 'user-1',
    });

    vi.stubEnv('NEXT_PUBLIC_WORKSPACE_ID', '');
    vi.stubEnv('NEXT_PUBLIC_ACTOR_USER_ID', '');
    auth.hasBootstrapConfig.mockReturnValue(true);
    await expect(service.bootstrapAuthContext()).resolves.toEqual({
      workspaceId: 'workspace-1',
      actorUserId: 'user-1',
    });
    expect(auth.ensureAuthenticatedContext).toHaveBeenCalled();
  });

  it('fails explicitly when API scope is unavailable', async () => {
    vi.stubEnv('NEXT_PUBLIC_WORKSPACE_ID', '');
    vi.stubEnv('NEXT_PUBLIC_ACTOR_USER_ID', '');
    const service = new ProjectService();

    await expect(service.fetchAllProjects()).rejects.toThrow('Project API scope is not configured');
  });

  it('fetches and maps project list fields', async () => {
    api.get.mockResolvedValue({ items: [apiProject], next_cursor: null });

    await expect(new ProjectService().fetchAllProjects()).resolves.toEqual([
      expect.objectContaining({
        id: projectFixture.id,
        sourceLanguage: 'en',
        targetLanguage: 'es',
        mediaId: 'media-1',
        pipelineProgressPercent: 35,
        currentPipelineOperationId: 'operation-1',
        lastRenderedVideoPath: 'renders/final.mp4',
      }),
    ]);
    expect(api.get).toHaveBeenCalledWith('/projects?');
  });

  it('maps nullable project fields to safe defaults', async () => {
    api.get.mockResolvedValue({
      ...apiProject,
      source_language: null,
      target_language: null,
      media_file_id: null,
      media_filename: null,
      media_duration_seconds: null,
      pipeline_progress_percent: null,
      transcript_id: null,
      last_rendered_video_gcs_path: null,
    });

    await expect(new ProjectService().getProject(projectFixture.id)).resolves.toMatchObject({
      sourceLanguage: 'en',
      targetLanguage: 'en',
      mediaId: undefined,
      mediaDurationSeconds: undefined,
      transcriptId: undefined,
    });
    expect(api.get).toHaveBeenCalledWith(`/projects/${projectFixture.id}?`);
  });

  it('creates a project shell and maps request fields', async () => {
    api.post.mockResolvedValue(apiProject);

    await expect(new ProjectService().createProjectShell('Launch', 'en', 'fr'))
      .resolves.toMatchObject({ id: projectFixture.id, name: projectFixture.name });
    expect(api.post).toHaveBeenCalledWith('/projects?', {
      name: 'Launch',
      source_language: 'en',
      target_language: 'fr',
    });
  });

  it('creates a canonical first draft after the project shell', async () => {
    api.post.mockResolvedValue(apiProject);
    api.put.mockResolvedValue({ version: 1 });
    const service = new ProjectService();

    await service.createProjectShellWithDraft('Launch', 'en', 'es');

    expect(api.put).toHaveBeenCalledWith(
      `/projects/${projectFixture.id}/draft?`,
      expect.objectContaining({
        version: 1,
        base_project_updated_at: projectFixture.updatedAt,
        draft_schema_version: '1.2.0',
      }),
    );
  });

  it('maps sparse project updates and convenience operations', async () => {
    api.patch.mockResolvedValue({ ...apiProject, name: 'Renamed' });
    api.post.mockResolvedValue(apiProject);
    const service = new ProjectService();

    await service.updateProject(projectFixture.id, {
      name: 'Renamed',
      status: 'processing',
      sourceLanguage: 'de',
      targetLanguage: 'fr',
      activeTranslationLanguage: 'fr',
      mediaId: 'media-2',
      transcriptId: 'transcript-2',
    });
    expect(api.patch).toHaveBeenCalledWith(`/projects/${projectFixture.id}?`, {
      name: 'Renamed',
      status: 'processing',
      source_language: 'de',
      target_language: 'fr',
      active_translation_language: 'fr',
      media_file_id: 'media-2',
      transcript_id: 'transcript-2',
    });

    await service.renameProject(projectFixture.id, 'Again');
    await service.archiveProject(projectFixture.id);
    await service.duplicateProject(projectFixture.id);
    expect(api.patch).toHaveBeenLastCalledWith(
      `/projects/${projectFixture.id}?`,
      { name: 'Again' },
    );
    expect(api.post).toHaveBeenCalledWith(`/projects/${projectFixture.id}/archive?`, {});
    expect(api.post).toHaveBeenCalledWith(`/projects/${projectFixture.id}/duplicate?`, {});
  });

  it('loads and normalizes server drafts using current project metadata', async () => {
    api.get
      .mockResolvedValueOnce({
        project_id: projectFixture.id,
        version: 4,
        base_project_updated_at: projectFixture.updatedAt,
        draft_payload: {
          version: '',
          projectMetadata: { id: '', name: '', sourceLanguage: '', targetLanguage: '' },
          mediaReferences: { videoFilename: '', durationSeconds: 0 },
        },
      })
      .mockResolvedValueOnce(apiProject);

    await expect(new ProjectService().getProjectDraft(projectFixture.id)).resolves.toEqual({
      version: 4,
      baseProjectUpdatedAt: projectFixture.updatedAt,
      draft: expect.objectContaining({
        version: '1.2.0',
        projectMetadata: expect.objectContaining({ name: projectFixture.name }),
        mediaReferences: expect.objectContaining({
          videoFilename: 'launch.mp4',
          originalTranscriptSegments: [],
        }),
        translations: [],
      }),
    });
  });

  it('serializes draft saves and optional checkpoint reasons', async () => {
    api.put.mockResolvedValue({ version: 3 });
    const service = new ProjectService();

    await service.saveProjectDraft(projectFixture.id, draftFixture, {
      version: 3,
      baseProjectUpdatedAt: projectFixture.updatedAt,
      checkpointReason: 'manual-save',
    });
    expect(api.put).toHaveBeenCalledWith(`/projects/${projectFixture.id}/draft?`, {
      version: 3,
      draft_schema_version: '1.2.0',
      base_project_updated_at: projectFixture.updatedAt,
      draft_payload: draftFixture,
      checkpoint_reason: 'manual-save',
    });

    await service.seedProjectDraft(projectFixture);
    expect(api.put).toHaveBeenLastCalledWith(
      `/projects/${projectFixture.id}/draft?`,
      expect.objectContaining({ version: 1 }),
    );
  });

  it('recognizes only canonical draft version conflicts', () => {
    const detail = {
      code: 'DRAFT_VERSION_CONFLICT' as const,
      message: 'stale',
      project_id: projectFixture.id,
      client_version: 2,
      server_version: 3,
      server_updated_at: projectFixture.updatedAt,
      last_saved_by_user_id: 'user-2',
    };
    expect(getProjectDraftConflictDetail(new ApiError('stale', 409, { error: detail })))
      .toEqual(detail);
    expect(getProjectDraftConflictDetail(new ApiError('other', 409, { error: { code: 'OTHER' } })))
      .toBeNull();
    expect(getProjectDraftConflictDetail(new ApiError('stale', 400, { error: detail })))
      .toBeNull();
    expect(getProjectDraftConflictDetail(new Error('stale'))).toBeNull();
  });

  it('maps transcripts and translations into store models', async () => {
    api.get
      .mockResolvedValueOnce({
        segments: [{
          id: null,
          sequence_order: 2,
          start_time: 1,
          end_time: 3,
          duration: 2,
          speaker: 'Speaker 2',
          text: 'Hello',
          confidence: null,
        }],
      })
      .mockResolvedValueOnce({
        translations: [
          translationItem({ duration_ratio: 2 }),
          translationItem({
            translation_id: 'translation-2',
            segment_id: 'segment-2',
            duration_ratio: 0.5,
            generated_audio_status: null,
          }),
        ],
      });
    const service = new ProjectService();

    await expect(service.getTranscript('media-1')).resolves.toEqual([{
      id: '',
      sequenceOrder: 2,
      startTimeSeconds: 1,
      endTimeSeconds: 3,
      durationSeconds: 2,
      speakerTag: 'Speaker 2',
      text: 'Hello',
      confidence: 0,
    }]);
    await expect(service.fetchTranslations('transcript-1', 'es')).resolves.toEqual([
      expect.objectContaining({
        transcriptSegmentId: 'segment-1',
        speedAdjustmentFactor: 1.25,
        status: 'completed',
      }),
      expect.objectContaining({
        transcriptSegmentId: 'segment-2',
        speedAdjustmentFactor: 0.8,
        generatedAudioStatus: undefined,
      }),
    ]);
  });

  it('maps translation, retranslation, and synthesis requests', async () => {
    api.post
      .mockResolvedValueOnce({ job_id: 'translation-job', status: 'queued' })
      .mockResolvedValueOnce(translationItem())
      .mockResolvedValueOnce({ audio_url: 'https://cdn.test/audio.mp3' });
    api.put.mockResolvedValue(translationItem({ translated_text: 'Editado' }));
    const service = new ProjectService();

    await service.triggerProjectTranslation('transcript-1', 'en', 'es');
    expect(api.post).toHaveBeenNthCalledWith(1, '/translation/translate-project', {
      transcript_id: 'transcript-1',
      source_language: 'en',
      target_language: 'es',
    });

    await expect(service.retranslateSegment({
      segmentId: 'segment-1',
      sourceText: 'Hello',
      originalDurationMs: 4000,
      sourceLanguage: 'en',
      targetLanguage: 'es',
    })).resolves.toMatchObject({ translatedText: 'Hola' });
    expect(api.post).toHaveBeenNthCalledWith(2, '/translation/translate-segment', {
      segment_id: 'segment-1',
      source_text: 'Hello',
      original_duration_ms: 4000,
      source_language: 'en',
      target_language: 'es',
      speaker_tag: 'Speaker 1',
      previous_context: null,
      next_context: null,
    });

    await expect(service.updateTranslationSegment('translation-1', 'Editado'))
      .resolves.toMatchObject({ translatedText: 'Editado' });
    await expect(service.synthesizeSegment('translation-1'))
      .resolves.toEqual({ audioUrl: 'https://cdn.test/audio.mp3' });
  });

  it('uploads small media and starts transcription', async () => {
    api.post
      .mockResolvedValueOnce({ media_id: 'media-1' })
      .mockResolvedValueOnce({ transcript_id: 'transcript-1' });
    const service = new ProjectService();
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' });

    await service.uploadMedia(file);
    const body = api.post.mock.calls[0][1] as FormData;
    expect(body.get('file')).toBe(file);
    await service.startTranscription('media-1', 'en');
    expect(api.post).toHaveBeenLastCalledWith('/transcription/start', {
      media_id: 'media-1',
      language: 'en',
      enable_noise_reduction: true,
      enable_loudness_norm: true,
      enable_vad: true,
    });
  });

  it('uploads large media in deterministic resumable chunks', async () => {
    api.post
      .mockResolvedValueOnce({
        upload_id: 'upload-1',
        gcs_resumable_url: 'https://upload.test/session',
      })
      .mockResolvedValueOnce({ media_id: 'media-1' });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 308 }),
    );
    const progress = vi.fn();
    const file = new File([new Uint8Array(9 * 1024 * 1024)], 'large.mp4', { type: 'video/mp4' });

    await new ProjectService().uploadMediaResumable(file, projectFixture.id, progress);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(progress.mock.calls.flat()).toEqual([89, 100]);
    expect(api.post).toHaveBeenLastCalledWith(
      `/media/uploads/signed-resumable/upload-1/complete?project_id=${projectFixture.id}`,
      {},
    );
  });

  it('surfaces resumable upload chunk failures', async () => {
    api.post.mockResolvedValue({
      upload_id: 'upload-1',
      gcs_resumable_url: 'https://upload.test/session',
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 500 }));

    await expect(new ProjectService().uploadMediaResumable(
      new File(['video'], 'large.mp4'),
      projectFixture.id,
    )).rejects.toThrow('Large-file upload failed at 0%');
  });

  it('queries pipeline, media, versions, and histories at their canonical endpoints', async () => {
    api.get
      .mockResolvedValueOnce({ id: 'operation-1' })
      .mockResolvedValueOnce({ media_id: 'media-1' })
      .mockResolvedValueOnce({ audio_url: 'audio' })
      .mockResolvedValueOnce({ items: [{ version: 1 }] })
      .mockResolvedValueOnce({ version: 1 })
      .mockResolvedValueOnce([{ id: 'export-1' }])
      .mockResolvedValueOnce([{ job_id: 'render-1' }])
      .mockResolvedValueOnce({ status: 'completed' })
      .mockResolvedValueOnce({ translations: [] });
    const service = new ProjectService();

    await service.getPipelineOperation(projectFixture.id);
    await service.getMedia('media-1');
    await service.getMediaAudio('media-1');
    await service.getProjectVersions(projectFixture.id);
    await service.getProjectVersion(projectFixture.id, 1);
    await service.getProjectExportHistory(projectFixture.id);
    await service.getProjectRenderHistory(projectFixture.id);
    await service.getExportStatus('render-1');
    await service.fetchProjectTranslations('transcript-1', 'fr');

    expect(api.get.mock.calls.map(([endpoint]) => endpoint)).toEqual([
      `/projects/${projectFixture.id}/pipeline-operation?`,
      '/media/media-1',
      '/media/media-1/audio',
      `/projects/${projectFixture.id}/versions?`,
      `/projects/${projectFixture.id}/versions/1?`,
      `/export/history?project_id=${projectFixture.id}`,
      `/lipsync/history?project_id=${projectFixture.id}`,
      '/lipsync/job/render-1',
      '/translation/transcript-1?target_language=fr',
    ]);
  });

  it('skips export history for noncanonical project ids', async () => {
    await expect(new ProjectService().getProjectExportHistory('local-draft'))
      .resolves.toEqual([]);
    expect(api.get).not.toHaveBeenCalled();
  });

  it('retries transcription and translation pipeline operations', async () => {
    api.post.mockResolvedValue({ operation_id: 'operation-1' });
    const service = new ProjectService();

    await service.retryPipelineOperation('operation-1');
    await service.retryTranscriptionOperation('operation-2');

    expect(api.post.mock.calls).toEqual([
      ['/translation/pipeline-operation/operation-1/retry?', {}],
      ['/transcription/pipeline-operation/operation-2/retry?', {}],
    ]);
  });

  it('maps TTS and render requests with only canonical project ids', async () => {
    api.post.mockResolvedValue({ job_id: 'job-1' });
    const service = new ProjectService();

    await service.triggerTtsSynthesis('transcript-1', 'es', projectFixture.id);
    await service.triggerLipSync('media-1', 'transcript-1', 'es', projectFixture.id);
    await service.triggerDubOnly('media-1', 'transcript-1', 'fr', 'local-draft');

    expect(api.post.mock.calls).toEqual([
      ['/tts/synthesize-project', {
        transcript_id: 'transcript-1',
        target_language: 'es',
        project_id: projectFixture.id,
      }],
      ['/lipsync/render-project', {
        media_file_id: 'media-1',
        transcript_id: 'transcript-1',
        target_language: 'es',
        project_id: projectFixture.id,
        model_preference: 'liveportrait',
        burn_in_subtitles: false,
        enable_lipsync: true,
      }],
      ['/lipsync/render-project', {
        media_file_id: 'media-1',
        transcript_id: 'transcript-1',
        target_language: 'fr',
        model_preference: 'liveportrait',
        burn_in_subtitles: false,
        enable_lipsync: false,
      }],
    ]);
  });
});
