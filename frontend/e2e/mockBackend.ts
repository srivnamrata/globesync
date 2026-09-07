import type { Page, Route } from '@playwright/test';

export const PROJECT_ID = '11111111-1111-4111-8111-111111111111';
export const MEDIA_ID = '22222222-2222-4222-8222-222222222222';
export const TRANSCRIPT_ID = '33333333-3333-4333-8333-333333333333';
export const SEGMENT_ID = '44444444-4444-4444-8444-444444444444';
export const TRANSLATION_ID = '55555555-5555-4555-8555-555555555555';
export const JOB_ID = '66666666-6666-4666-8666-666666666666';

const NOW = '2026-09-06T00:00:00Z';

export const authContext = {
  user: {
    id: '77777777-7777-4777-8777-777777777777',
    email: 'e2e@globesync.test',
    display_name: 'E2E Operator',
    auth_provider: 'test',
    auth_subject: 'e2e-user',
    is_active: true,
    last_login_at: NOW,
    created_at: NOW,
    updated_at: NOW,
  },
  workspace: {
    id: '88888888-8888-4888-8888-888888888888',
    name: 'Production Test Workspace',
    slug: 'production-test',
    owner_user_id: '77777777-7777-4777-8777-777777777777',
    is_personal: false,
    archived_at: null,
    created_at: NOW,
    updated_at: NOW,
  },
  membership: {
    workspace_id: '88888888-8888-4888-8888-888888888888',
    user_id: '77777777-7777-4777-8777-777777777777',
    role: 'owner',
    invited_by_user_id: null,
    joined_at: NOW,
    created_at: NOW,
    updated_at: NOW,
  },
  bootstrap_completed: true,
};

export type MockProject = {
  id: string;
  workspace_id: string;
  owner_user_id: string;
  created_by_user_id: string;
  name: string;
  slug: string | null;
  status: 'draft' | 'processing' | 'completed';
  source_language: string;
  target_language: string;
  active_translation_language: string;
  media_file_id: string | null;
  media_filename: string | null;
  media_duration_seconds: number | null;
  transcript_id: string | null;
  latest_draft_version: number;
  current_lipsync_job_id: string | null;
  current_export_job_id: string | null;
  current_pipeline_operation_id: string | null;
  last_rendered_video_gcs_path: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export function makeProject(overrides: Partial<MockProject> = {}): MockProject {
  return {
    id: PROJECT_ID,
    workspace_id: authContext.workspace.id,
    owner_user_id: authContext.user.id,
    created_by_user_id: authContext.user.id,
    name: 'Launch video',
    slug: null,
    status: 'draft',
    source_language: 'en',
    target_language: 'es',
    active_translation_language: 'es',
    media_file_id: MEDIA_ID,
    media_filename: 'launch.mp4',
    media_duration_seconds: 4,
    transcript_id: TRANSCRIPT_ID,
    latest_draft_version: 1,
    current_lipsync_job_id: null,
    current_export_job_id: null,
    current_pipeline_operation_id: null,
    last_rendered_video_gcs_path: null,
    archived_at: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

export function makeSegment(text = 'Welcome to GlobeSync') {
  return {
    id: SEGMENT_ID,
    sequenceOrder: 0,
    startTimeSeconds: 0,
    endTimeSeconds: 4,
    durationSeconds: 4,
    speakerTag: 'Speaker 1',
    text,
    confidence: 0.97,
  };
}

export function makeTranslation(text = 'Bienvenido a GlobeSync') {
  return {
    id: TRANSLATION_ID,
    transcriptSegmentId: SEGMENT_ID,
    translatedText: text,
    originalDurationMs: 4000,
    estimatedDurationMs: 3900,
    durationRatio: 0.98,
    speedAdjustmentFactor: 0.98,
    qualityScore: 0.96,
    generatedAudioStatus: 'ready',
    status: 'completed',
  };
}

export function makeDraft(project: MockProject, translationText = 'Bienvenido a GlobeSync') {
  const segments = project.transcript_id ? [makeSegment()] : [];
  return {
    version: '1.2.0',
    projectMetadata: {
      id: project.id,
      name: project.name,
      sourceLanguage: project.source_language,
      targetLanguage: project.target_language,
      createdAt: project.created_at,
      updatedAt: project.updated_at,
    },
    mediaReferences: {
      videoFilename: project.media_filename || 'source_video.mp4',
      durationSeconds: project.media_duration_seconds || 0,
      originalTranscriptSegments: segments,
      transcriptId: project.transcript_id || undefined,
      mediaId: project.media_file_id || undefined,
    },
    translations: project.transcript_id ? [makeTranslation(translationText)] : [],
  };
}

function translationApiShape(text = 'Bienvenido a GlobeSync') {
  return {
    translation_id: TRANSLATION_ID,
    segment_id: SEGMENT_ID,
    sequence_order: 0,
    speaker_tag: 'Speaker 1',
    start_time_seconds: 0,
    end_time_seconds: 4,
    source_text: 'Welcome to GlobeSync',
    translated_text: text,
    original_duration_ms: 4000,
    estimated_duration_ms: 3900,
    duration_ratio: 0.98,
    duration_status: 'matched',
    iterations_count: 1,
    confidence_score: 0.96,
    is_cached: false,
    is_user_edited: false,
    generated_audio_status: 'ready',
    created_at: NOW,
  };
}

type JsonValue = Record<string, unknown> | unknown[];

async function json(route: Route, body: JsonValue, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function silentWav(): Buffer {
  const sampleRate = 8000;
  const sampleCount = 800;
  const dataSize = sampleCount * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVEfmt ', 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

export class MockBackend {
  project: MockProject;
  projects: MockProject[];
  draft: ReturnType<typeof makeDraft>;
  draftVersion = 1;
  rejectDraftWrites = false;
  authStatus = 200;
  buildStatus = 200;
  formatHistoryStatus = 200;
  translationText = 'Bienvenido a GlobeSync';
  buildPollCount = 0;
  draftWriteVersions: number[] = [];
  renderRequests: Array<Record<string, unknown>> = [];

  constructor(project = makeProject()) {
    this.project = project;
    this.projects = [project];
    this.draft = makeDraft(project);
  }

  async install(page: Page) {
    await page.route('http://127.0.0.1:8000/e2e/silence.wav', (route) => route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: silentWav(),
    }));
    await page.route('http://127.0.0.1:8000/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace('/v1', '');
      const method = request.method();

      if (path === '/auth/bootstrap') {
        await json(
          route,
          this.authStatus === 200
            ? authContext
            : { error: { message: this.authStatus === 401 ? 'Session expired' : 'Authentication service unavailable' } },
          this.authStatus,
        );
        return;
      }
      if (path === '/auth/workspaces') {
        await json(route, { items: [{ workspace: authContext.workspace, membership: authContext.membership }] });
        return;
      }
      if (path === '/auth/workspace-members') {
        await json(route, {
          items: [{
            user_id: authContext.user.id,
            display_name: authContext.user.display_name,
            email: authContext.user.email,
            role: 'owner',
          }],
        });
        return;
      }
      if (path === '/translation/languages') {
        await json(route, {
          languages: [
            { code: 'en', name: 'English', native_name: 'English' },
            { code: 'es', name: 'Spanish', native_name: 'Español' },
          ],
        });
        return;
      }
      if (path === '/projects' && method === 'GET') {
        await json(route, { items: this.projects, next_cursor: null });
        return;
      }
      if (path === '/projects' && method === 'POST') {
        const requestBody = request.postDataJSON();
        this.project = makeProject({
          name: requestBody.name,
          source_language: requestBody.source_language,
          target_language: requestBody.target_language,
          active_translation_language: requestBody.target_language,
          media_file_id: null,
          media_filename: null,
          media_duration_seconds: null,
          transcript_id: null,
        });
        this.projects = [this.project];
        this.draft = makeDraft(this.project);
        await json(route, this.project, 201);
        return;
      }
      if (path === `/projects/${this.project.id}/draft` && method === 'GET') {
        await json(route, {
          project_id: this.project.id,
          workspace_id: authContext.workspace.id,
          version: this.draftVersion,
          draft_schema_version: '1.2.0',
          base_project_updated_at: this.project.updated_at,
          last_saved_by_user_id: authContext.user.id,
          created_at: NOW,
          updated_at: NOW,
          draft_payload: this.draft,
        });
        return;
      }
      if (path === `/projects/${this.project.id}/draft` && method === 'PUT') {
        const requestBody = request.postDataJSON();
        this.draftWriteVersions.push(requestBody.version);
        if (this.rejectDraftWrites || requestBody.version !== this.draftVersion) {
          await json(route, {
            error: {
              code: 'DRAFT_VERSION_CONFLICT',
              message: 'The saved draft has changed.',
              project_id: this.project.id,
              client_version: requestBody.version,
              server_version: this.draftVersion,
              server_updated_at: NOW,
              last_saved_by_user_id: authContext.user.id,
            },
          }, 409);
          return;
        }
        this.draft = requestBody.draft_payload;
        this.draftVersion += 1;
        await json(route, {
          project_id: this.project.id,
          workspace_id: authContext.workspace.id,
          version: this.draftVersion,
          draft_schema_version: '1.2.0',
          base_project_updated_at: this.project.updated_at,
          last_saved_by_user_id: authContext.user.id,
          updated_at: NOW,
        });
        return;
      }
      if (path === `/projects/${this.project.id}/versions`) {
        await json(route, { items: [] });
        return;
      }
      if (path === `/projects/${this.project.id}` && method === 'GET') {
        await json(route, this.project);
        return;
      }
      if (path === `/projects/${this.project.id}` && method === 'PATCH') {
        const requestBody = request.postDataJSON();
        this.project = {
          ...this.project,
          name: requestBody.name ?? this.project.name,
          status: requestBody.status ?? this.project.status,
          source_language: requestBody.source_language ?? this.project.source_language,
          target_language: requestBody.target_language ?? this.project.target_language,
          active_translation_language: requestBody.active_translation_language ?? this.project.active_translation_language,
          media_file_id: requestBody.media_file_id ?? this.project.media_file_id,
          transcript_id: requestBody.transcript_id ?? this.project.transcript_id,
          updated_at: '2026-09-06T00:00:01Z',
        };
        await json(route, this.project);
        return;
      }
      if (path === '/media/uploads/direct' && method === 'POST') {
        await json(route, {
          media_id: MEDIA_ID,
          filename: 'sample.mp4',
          media_type: 'video/mp4',
          filesize_bytes: 16,
          duration_seconds: 4,
          media_url: null,
          status: 'ready',
        }, 201);
        return;
      }
      if (path === '/transcription/start' && method === 'POST') {
        await json(route, { transcript_id: TRANSCRIPT_ID }, 202);
        return;
      }
      if (path === `/transcription/${TRANSCRIPT_ID}`) {
        await json(route, {
          transcript_id: TRANSCRIPT_ID,
          media_id: MEDIA_ID,
          status: 'completed',
          language: 'en',
          confidence_score: 0.97,
          word_count: 3,
          speaker_count: 1,
          full_text: 'Welcome to GlobeSync',
          segments: [{
            id: SEGMENT_ID,
            start_time: 0,
            end_time: 4,
            duration: 4,
            speaker: 'Speaker 1',
            text: 'Welcome to GlobeSync',
            confidence: 0.97,
            sequence_order: 0,
          }],
        });
        return;
      }
      if (path === '/translation/translate-project' && method === 'POST') {
        await json(route, {
          job_id: JOB_ID,
          transcript_id: TRANSCRIPT_ID,
          target_language: 'es',
          status: 'queued',
          message: 'Translation queued',
        }, 202);
        return;
      }
      if (path === `/translation/${TRANSCRIPT_ID}` && method === 'GET') {
        await json(route, {
          transcript_id: TRANSCRIPT_ID,
          target_language: 'es',
          total_segments: 1,
          average_duration_ratio: 0.98,
          overall_confidence: 0.96,
          translations: [translationApiShape(this.translationText)],
        });
        return;
      }
      if (path === `/translation/segment/${TRANSLATION_ID}` && method === 'PUT') {
        const requestBody = request.postDataJSON();
        await json(route, translationApiShape(requestBody.translated_text));
        return;
      }
      if (path === `/media/${MEDIA_ID}`) {
        await json(route, {
          media_id: MEDIA_ID,
          filename: 'launch.mp4',
          media_type: 'video/mp4',
          filesize_bytes: 1024,
          duration_seconds: 4,
          media_url: 'https://media.globesync.test/launch.mp4',
          status: 'ready',
          storage_path: 'e2e/launch.mp4',
          thumbnail_url: null,
          created_at: NOW,
        });
        return;
      }
      if (path === `/media/${MEDIA_ID}/audio`) {
        await json(route, {
          media_id: MEDIA_ID,
          audio_url: 'http://127.0.0.1:8000/e2e/silence.wav',
          format: 'wav',
          duration_seconds: 0.1,
        });
        return;
      }
      if (path === '/lipsync/render-project' && method === 'POST') {
        this.renderRequests.push(request.postDataJSON());
        if (this.buildStatus !== 200) {
          await json(route, { error: { message: 'Rendering service unavailable' } }, this.buildStatus);
          return;
        }
        await json(route, { job_id: JOB_ID }, 202);
        return;
      }
      if (path === `/lipsync/job/${JOB_ID}`) {
        this.buildPollCount += 1;
        if (this.buildPollCount === 1) {
          await json(route, {
            job_id: JOB_ID,
            render_mode: 'dub_only',
            status: 'in_progress',
            progress_percent: 48,
            current_stage: 'audio_retiming',
            last_successful_stage: 'voice_synthesis',
            output_video_url: null,
          });
          return;
        }
        await json(route, {
          job_id: JOB_ID,
          render_mode: 'dub_only',
          status: 'completed',
          progress_percent: 100,
          current_stage: 'completed',
          last_successful_stage: 'mux_export',
          output_video_url: 'https://media.globesync.test/output.mp4',
          download_video_url: 'https://media.globesync.test/output.mp4?download=1',
          segments_metadata: [],
        });
        return;
      }
      if (path === '/lipsync/history') {
        await json(route, [
          {
            job_id: JOB_ID,
            target_language: 'es',
            render_mode: 'dub_only',
            status: 'completed',
            progress_percent: 100,
            current_stage: 'completed',
            last_successful_stage: 'mux_export',
            output_video_url: 'https://media.globesync.test/output.mp4',
            download_video_url: 'https://media.globesync.test/output.mp4?download=1',
            output_filesize_bytes: 5242880,
            execution_time_seconds: 42,
            quality_score: 0.94,
            created_at: NOW,
          },
          {
            job_id: '99999999-9999-4999-8999-999999999999',
            target_language: 'es',
            render_mode: 'dub_and_lipsync',
            status: 'failed',
            progress_percent: 72,
            current_stage: 'lipsync_render',
            last_successful_stage: 'audio_retiming',
            output_video_url: null,
            output_filesize_bytes: null,
            execution_time_seconds: 18,
            quality_score: 0,
            created_at: NOW,
          },
        ]);
        return;
      }
      if (path === '/export/history') {
        if (this.formatHistoryStatus !== 200) {
          await json(route, { error: { message: 'Export history unavailable' } }, this.formatHistoryStatus);
          return;
        }
        await json(route, []);
        return;
      }

      await json(route, { detail: `No E2E mock for ${method} ${path}` }, 404);
    });
  }
}
