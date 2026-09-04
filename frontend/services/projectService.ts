import { ApiError, apiClient } from './apiClient';
import { authService } from './authService';
import type { Project } from '../store/projectStore';
import type { TranscriptSegment } from '../store/mediaStore';
import type { TranslatedSegment } from '../store/translationStore';
import type { HeygenXFile } from './storageService';

export interface UploadedMedia {
  media_id: string;
  filename: string;
  media_type: string;
  filesize_bytes: number;
  duration_seconds: number;
  media_url?: string | null;
  status: string;
}

interface SignedResumableUploadResponse {
  upload_id: string;
  filename: string;
  filesize_bytes: number;
  storage_path: string;
  gcs_resumable_url: string;
  expires_at: string;
  upload_mode: 'gcs_resumable';
}

export interface MediaDetails extends UploadedMedia {
  storage_path: string;
  thumbnail_url?: string | null;
  created_at: string;
}

export interface MediaAudioDetails {
  media_id: string;
  audio_url: string;
  format: string;
  duration_seconds: number;
}

export interface TranscriptStatus {
  transcript_id: string;
  media_id?: string;
  status: 'queued' | 'in_progress' | 'completed' | 'failed';
  language?: string;
  confidence_score?: number | null;
  word_count?: number;
  speaker_count?: number;
  full_text?: string | null;
  segments: Array<{
    id: string | null;
    start_time: number;
    end_time: number;
    duration: number;
    speaker: string;
    text: string;
    confidence: number | null;
    sequence_order: number;
  }>;
}

export interface TranslationJobStatus {
  job_id: string;
  transcript_id: string;
  target_language: string;
  status: 'queued' | 'completed' | 'failed';
  message: string;
}

export interface TranslationItemResponse {
  translation_id: string;
  segment_id: string;
  sequence_order: number;
  speaker_tag: string;
  start_time_seconds: number;
  end_time_seconds: number;
  source_text: string;
  translated_text: string;
  original_duration_ms: number;
  estimated_duration_ms: number;
  duration_ratio: number;
  duration_status: string;
  iterations_count: number;
  confidence_score: number;
  is_cached: boolean;
  is_user_edited: boolean;
  generated_audio_status?: string | null;
  created_at: string;
}

export interface ProjectTranslationResponse {
  transcript_id: string;
  target_language: string;
  total_segments: number;
  average_duration_ratio: number;
  overall_confidence: number;
  translations: TranslationItemResponse[];
}

interface ProjectApiShape {
  id: string;
  workspace_id: string;
  owner_user_id: string;
  name: string;
  status: Project['status'] | 'archived';
  source_language: string | null;
  target_language: string | null;
  active_translation_language: string | null;
  media_file_id: string | null;
  media_filename?: string | null;
  media_duration_seconds?: number | null;
  pipeline_stage?: string | null;
  pipeline_status?: string | null;
  pipeline_progress_percent?: number | null;
  pipeline_error_message?: string | null;
  transcript_id: string | null;
  latest_draft_version: number;
  last_rendered_video_gcs_path: string | null;
  created_at: string;
  updated_at: string;
}

interface ProjectDetailApiShape extends ProjectApiShape {
  created_by_user_id: string;
  slug: string | null;
  current_lipsync_job_id: string | null;
  current_export_job_id: string | null;
  archived_at: string | null;
}

export interface ProjectUpdateRequest {
  name?: string;
  status?: Project['status'];
  sourceLanguage?: string;
  targetLanguage?: string;
  activeTranslationLanguage?: string;
  mediaId?: string;
  transcriptId?: string;
}

interface ProjectUpdateApiRequest {
  name?: string;
  status?: Project['status'];
  source_language?: string;
  target_language?: string;
  active_translation_language?: string;
  media_file_id?: string;
  transcript_id?: string;
}

interface ProjectDraftApiResponse {
  project_id: string;
  workspace_id: string;
  version: number;
  draft_schema_version: string;
  base_project_updated_at: string | null;
  last_saved_by_user_id: string;
  created_at: string;
  updated_at: string;
  draft_payload: HeygenXFile;
}

export interface ProjectDraftConflictErrorDetail {
  code: 'DRAFT_VERSION_CONFLICT';
  message: string;
  project_id: string;
  client_version: number;
  server_version: number;
  server_updated_at: string;
  last_saved_by_user_id: string;
}

interface ProjectDraftPutApiResponse {
  project_id: string;
  workspace_id: string;
  version: number;
  draft_schema_version: string;
  base_project_updated_at: string | null;
  last_saved_by_user_id: string;
  updated_at: string;
}

interface ProjectListApiResponse {
  items: ProjectApiShape[];
  next_cursor: string | null;
}

export interface ProjectVersionResponse {
  version: number;
  draft_schema_version: string;
  draft_payload: HeygenXFile;
  created_by_user_id: string;
  created_at: string;
}

export interface ProjectVersionSummary {
  version: number;
  draft_schema_version: string;
  created_by_user_id: string;
  created_at: string;
}

export interface ProjectExportHistoryItem {
  id: string;
  project_id?: string | null;
  target_language: string;
  format: string;
  resolution: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress_percent: number;
  current_stage: string;
  output_video_url?: string | null;
  download_video_url?: string | null;
  filesize_bytes?: number | null;
  created_at: string;
}

export interface ProjectRenderHistoryItem {
  job_id: string;
  target_language: string;
  render_mode: 'dub_only' | 'dub_and_lipsync';
  status: string;
  progress_percent: number;
  current_stage: string;
  last_successful_stage?: string | null;
  output_video_url?: string | null;
  download_video_url?: string | null;
  output_filesize_bytes?: number | null;
  execution_time_seconds?: number | null;
  quality_score: number;
  created_at: string;
}

export interface PipelineOperationStatus {
  id: string;
  project_id: string | null;
  workspace_id: string | null;
  transcript_id: string | null;
  operation_type: 'transcription' | 'translation' | string;
  target_language: string | null;
  status: 'queued' | 'in_progress' | 'completed' | 'failed' | string;
  progress_percent: number;
  current_stage: string;
  last_successful_stage: string | null;
  message: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineOperationRetryResponse {
  operation_id: string;
  operation_type: string;
  status: string;
  message: string;
}

type ProjectApiScope = {
  workspaceId: string;
  actorUserId: string;
};

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function normalizeOptionalUuid(value?: string): string | undefined {
  return value && UUID_PATTERN.test(value) ? value : undefined;
}

function buildScopedEndpoint(endpoint: string, _scope: ProjectApiScope, params: Record<string, string | number | boolean | undefined> = {}): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value));
    }
  });

  return `${endpoint}?${searchParams.toString()}`;
}

function mapProjectApiShape(project: ProjectApiShape | ProjectDetailApiShape): Project {
  return {
    id: project.id,
    name: project.name,
    sourceLanguage: project.source_language || 'en',
    targetLanguage: project.target_language || 'en',
    status: project.status,
    createdAt: project.created_at,
    updatedAt: project.updated_at,
    transcriptId: project.transcript_id || undefined,
    mediaId: project.media_file_id || undefined,
    mediaFilename: project.media_filename || undefined,
    mediaDurationSeconds: project.media_duration_seconds ?? undefined,
    pipelineStage: project.pipeline_stage || undefined,
    pipelineStatus: project.pipeline_status || undefined,
    pipelineProgressPercent: project.pipeline_progress_percent ?? undefined,
    pipelineErrorMessage: project.pipeline_error_message || undefined,
    currentLipsyncJobId: 'current_lipsync_job_id' in project ? project.current_lipsync_job_id || undefined : undefined,
    lastRenderedVideoPath: project.last_rendered_video_gcs_path || undefined,
  };
}

export function getProjectDraftConflictDetail(error: unknown): ProjectDraftConflictErrorDetail | null {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }

  const detail = (error.data as { error?: ProjectDraftConflictErrorDetail } | undefined)?.error;
  if (!detail || detail.code !== 'DRAFT_VERSION_CONFLICT') {
    return null;
  }

  return detail;
}

function mapDraftPayloadToLocalDraft(projectId: string, payload: Partial<HeygenXFile>, fallbackProject?: Project): HeygenXFile {
  return {
    version: payload.version || '1.2.0',
    projectMetadata: {
      id: payload.projectMetadata?.id || projectId,
      name: payload.projectMetadata?.name || fallbackProject?.name || 'Untitled Project',
      sourceLanguage: payload.projectMetadata?.sourceLanguage || fallbackProject?.sourceLanguage || 'en',
      targetLanguage: payload.projectMetadata?.targetLanguage || fallbackProject?.targetLanguage || 'en',
      createdAt: payload.projectMetadata?.createdAt || fallbackProject?.createdAt || new Date().toISOString(),
      updatedAt: payload.projectMetadata?.updatedAt || fallbackProject?.updatedAt || new Date().toISOString(),
    },
    mediaReferences: {
      videoFilename: payload.mediaReferences?.videoFilename || fallbackProject?.mediaFilename || 'source_video.mp4',
      durationSeconds: payload.mediaReferences?.durationSeconds || 0,
      originalTranscriptSegments: payload.mediaReferences?.originalTranscriptSegments || [],
      transcriptId: payload.mediaReferences?.transcriptId || fallbackProject?.transcriptId,
      mediaId: payload.mediaReferences?.mediaId || fallbackProject?.mediaId,
    },
    translations: payload.translations || [],
    timelineState: payload.timelineState,
  };
}

function mapTranslationItem(item: TranslationItemResponse): TranslatedSegment {
  return {
    id: item.translation_id,
    transcriptSegmentId: item.segment_id,
    translatedText: item.translated_text,
    originalDurationMs: item.original_duration_ms,
    estimatedDurationMs: item.estimated_duration_ms,
    durationRatio: item.duration_ratio,
    speedAdjustmentFactor: Math.max(0.8, Math.min(1.25, item.duration_ratio || 1)),
    qualityScore: item.confidence_score,
    generatedAudioStatus: item.generated_audio_status ?? undefined,
    status: 'completed',
  };
}

export class ProjectService {
  hasProjectApiScope(): boolean {
    return Boolean(this.getProjectApiScope()) || authService.hasBootstrapConfig();
  }

  async bootstrapAuthContext(): Promise<ProjectApiScope> {
    const existingScope = this.getProjectApiScope();
    if (existingScope) {
      return existingScope;
    }

    const context = await authService.ensureAuthenticatedContext();
    return {
      workspaceId: context.workspace.id,
      actorUserId: context.user.id,
    };
  }

  private getProjectApiScope(): ProjectApiScope | null {
    const cachedContext = authService.getCachedContext();
    const workspaceId = process.env.NEXT_PUBLIC_WORKSPACE_ID?.trim() || cachedContext?.workspace.id;
    const actorUserId = process.env.NEXT_PUBLIC_ACTOR_USER_ID?.trim() || cachedContext?.user.id;

    if (!workspaceId || !actorUserId) {
      return null;
    }

    return {
      workspaceId,
      actorUserId,
    };
  }

  private requireProjectApiScope(): ProjectApiScope {
    const scope = this.getProjectApiScope();
    if (!scope) {
      throw new Error('Project API scope is not configured. Set NEXT_PUBLIC_WORKSPACE_ID and NEXT_PUBLIC_ACTOR_USER_ID, or provide frontend auth bootstrap inputs so the scope can be derived automatically.');
    }
    return scope;
  }

  buildLocalDraftFromProject(project: Project): HeygenXFile {
    return mapDraftPayloadToLocalDraft(project.id, {}, project);
  }

  private async ensureApiRequestAuth(): Promise<void> {
    if (authService.hasBootstrapConfig()) {
      await authService.ensureAuthenticatedContext();
    }
  }

  async uploadMedia(file: File): Promise<UploadedMedia> {
    await this.ensureApiRequestAuth();
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<UploadedMedia>('/media/uploads/direct', formData);
  }

  async uploadMediaResumable(
    file: File,
    projectId: string,
    onProgress?: (progressPercent: number) => void,
  ): Promise<UploadedMedia> {
    await this.ensureApiRequestAuth();
    const origin = typeof window !== 'undefined' ? window.location.origin : undefined;
    const session = await apiClient.post<SignedResumableUploadResponse>('/media/uploads/signed-resumable', {
      filename: file.name,
      filesize_bytes: file.size,
      mime_type: file.type || 'application/octet-stream',
      ...(origin ? { origin } : {}),
    });

    const chunkSize = 8 * 1024 * 1024;
    for (let start = 0; start < file.size; start += chunkSize) {
      const end = Math.min(file.size, start + chunkSize) - 1;
      const response = await fetch(session.gcs_resumable_url, {
        method: 'PUT',
        headers: {
          'Content-Length': String(end - start + 1),
          'Content-Range': `bytes ${start}-${end}/${file.size}`,
          'Content-Type': file.type || 'application/octet-stream',
        },
        body: file.slice(start, end + 1),
      });

      if (!response.ok && response.status !== 308) {
        throw new Error(`Large-file upload failed at ${Math.round((start / file.size) * 100)}%.`);
      }
      onProgress?.(Math.round(((end + 1) / file.size) * 100));
    }

    return apiClient.post<UploadedMedia>(
      `/media/uploads/signed-resumable/${session.upload_id}/complete?project_id=${encodeURIComponent(projectId)}`,
      {},
    );
  }

  async startTranscription(mediaId: string, language: string): Promise<{ transcript_id: string }> {
    await this.ensureApiRequestAuth();
    return apiClient.post('/transcription/start', {
      media_id: mediaId,
      language,
      enable_noise_reduction: true,
      enable_loudness_norm: true,
      enable_vad: true,
    });
  }

  async getTranscription(transcriptId: string): Promise<TranscriptStatus> {
    await this.ensureApiRequestAuth();
    return apiClient.get<TranscriptStatus>(`/transcription/${transcriptId}`);
  }

  async fetchAllProjects(): Promise<Project[]> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.get<ProjectListApiResponse>(
      buildScopedEndpoint('/projects', scope),
    );
    return response.items.map(mapProjectApiShape);
  }

  async createProjectShell(name: string, sourceLanguage: string, targetLanguage: string): Promise<Project> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.post<ProjectDetailApiShape>(
      buildScopedEndpoint('/projects', scope),
      {
        name,
        source_language: sourceLanguage,
        target_language: targetLanguage,
      },
    );
    return mapProjectApiShape(response);
  }

  async createProjectShellWithDraft(name: string, sourceLanguage: string, targetLanguage: string): Promise<Project> {
    const project = await this.createProjectShell(name, sourceLanguage, targetLanguage);
    await this.saveProjectDraft(project.id, this.buildLocalDraftFromProject(project), {
      version: 1,
      baseProjectUpdatedAt: project.updatedAt,
    });
    return project;
  }

  async getProject(projectId: string): Promise<Project> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.get<ProjectDetailApiShape>(
      buildScopedEndpoint(`/projects/${projectId}`, scope),
    );
    return mapProjectApiShape(response);
  }

  async getPipelineOperation(projectId: string): Promise<PipelineOperationStatus> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    return apiClient.get<PipelineOperationStatus>(
      buildScopedEndpoint(`/projects/${projectId}/pipeline-operation`, scope),
    );
  }

  async retryPipelineOperation(operationId: string): Promise<PipelineOperationRetryResponse> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    return apiClient.post<PipelineOperationRetryResponse>(
      buildScopedEndpoint(`/translation/pipeline-operation/${operationId}/retry`, scope),
      {},
    );
  }

  async retryTranscriptionOperation(operationId: string): Promise<PipelineOperationRetryResponse> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    return apiClient.post<PipelineOperationRetryResponse>(
      buildScopedEndpoint(`/transcription/pipeline-operation/${operationId}/retry`, scope),
      {},
    );
  }

  async getMedia(mediaId: string): Promise<MediaDetails> {
    await this.ensureApiRequestAuth();
    return apiClient.get<MediaDetails>(`/media/${mediaId}`);
  }

  async getMediaAudio(mediaId: string): Promise<MediaAudioDetails> {
    await this.ensureApiRequestAuth();
    return apiClient.get<MediaAudioDetails>(`/media/${mediaId}/audio`);
  }

  async getProjectVersions(projectId: string): Promise<ProjectVersionSummary[]> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.get<{ items: ProjectVersionSummary[] }>(
      buildScopedEndpoint(`/projects/${projectId}/versions`, scope),
    );
    return response.items;
  }

  async getProjectVersion(projectId: string, version: number): Promise<ProjectVersionResponse> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    return apiClient.get<ProjectVersionResponse>(
      buildScopedEndpoint(`/projects/${projectId}/versions/${version}`, scope),
    );
  }

  async getProjectExportHistory(projectId: string): Promise<ProjectExportHistoryItem[]> {
    await this.ensureApiRequestAuth();
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    if (!normalizedProjectId) {
      return [];
    }
    return apiClient.get<ProjectExportHistoryItem[]>(`/export/history?project_id=${encodeURIComponent(normalizedProjectId)}`);
  }

  async updateProject(projectId: string, payload: ProjectUpdateRequest): Promise<Project> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const apiPayload: ProjectUpdateApiRequest = {
      ...(payload.name !== undefined ? { name: payload.name } : {}),
      ...(payload.status !== undefined ? { status: payload.status } : {}),
      ...(payload.sourceLanguage !== undefined ? { source_language: payload.sourceLanguage } : {}),
      ...(payload.targetLanguage !== undefined ? { target_language: payload.targetLanguage } : {}),
      ...(payload.activeTranslationLanguage !== undefined
        ? { active_translation_language: payload.activeTranslationLanguage }
        : {}),
      ...(payload.mediaId !== undefined ? { media_file_id: payload.mediaId } : {}),
      ...(payload.transcriptId !== undefined ? { transcript_id: payload.transcriptId } : {}),
    };

    const response = await apiClient.patch<ProjectDetailApiShape>(
      buildScopedEndpoint(`/projects/${projectId}`, scope),
      apiPayload,
    );
    return mapProjectApiShape(response);
  }

  async renameProject(projectId: string, name: string): Promise<Project> {
    return this.updateProject(projectId, { name });
  }

  async archiveProject(projectId: string): Promise<Project> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.post<ProjectDetailApiShape>(
      buildScopedEndpoint(`/projects/${projectId}/archive`, scope),
      {},
    );
    return mapProjectApiShape(response);
  }

  async duplicateProject(projectId: string): Promise<Project> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.post<ProjectDetailApiShape>(
      buildScopedEndpoint(`/projects/${projectId}/duplicate`, scope),
      {},
    );
    return mapProjectApiShape(response);
  }

  async getProjectDraft(projectId: string): Promise<{ draft: HeygenXFile; version: number; baseProjectUpdatedAt: string | null }> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    const response = await apiClient.get<ProjectDraftApiResponse>(
      buildScopedEndpoint(`/projects/${projectId}/draft`, scope),
    );
    const project = await this.getProject(projectId);
    return {
      draft: mapDraftPayloadToLocalDraft(projectId, response.draft_payload, project),
      version: response.version,
      baseProjectUpdatedAt: response.base_project_updated_at,
    };
  }

  async saveProjectDraft(
    projectId: string,
    draft: HeygenXFile,
    options: { version: number; baseProjectUpdatedAt?: string | null; checkpointReason?: string },
  ): Promise<ProjectDraftPutApiResponse> {
    await this.ensureApiRequestAuth();
    const scope = this.requireProjectApiScope();
    return apiClient.put<ProjectDraftPutApiResponse>(
      buildScopedEndpoint(`/projects/${projectId}/draft`, scope),
      {
        version: options.version,
        draft_schema_version: draft.version,
        base_project_updated_at: options.baseProjectUpdatedAt || null,
        draft_payload: draft,
        ...(options.checkpointReason ? { checkpoint_reason: options.checkpointReason } : {}),
      },
    );
  }

  async seedProjectDraft(project: Project): Promise<ProjectDraftPutApiResponse> {
    return this.saveProjectDraft(project.id, this.buildLocalDraftFromProject(project), {
      version: 1,
      baseProjectUpdatedAt: project.updatedAt,
    });
  }

  async getTranscript(mediaId: string): Promise<TranscriptSegment[]> {
    await this.ensureApiRequestAuth();
    const response = await apiClient.get<TranscriptStatus>(`/transcription/media/${mediaId}`);
    return response.segments.map((segment) => ({
      id: segment.id ?? '',
      sequenceOrder: segment.sequence_order,
      startTimeSeconds: segment.start_time,
      endTimeSeconds: segment.end_time,
      durationSeconds: segment.duration,
      speakerTag: segment.speaker,
      text: segment.text,
      confidence: segment.confidence ?? 0,
    }));
  }

  async triggerProjectTranslation(transcriptId: string, sourceLanguage: string, targetLanguage: string): Promise<TranslationJobStatus> {
    await this.ensureApiRequestAuth();
    return apiClient.post<TranslationJobStatus>('/translation/translate-project', {
      transcript_id: transcriptId,
      source_language: sourceLanguage,
      target_language: targetLanguage,
    });
  }

  async fetchProjectTranslations(transcriptId: string, lang: string): Promise<ProjectTranslationResponse> {
    await this.ensureApiRequestAuth();
    return apiClient.get<ProjectTranslationResponse>(`/translation/${transcriptId}?target_language=${lang}`);
  }

  async fetchTranslations(transcriptId: string, lang: string): Promise<TranslatedSegment[]> {
    const response = await this.fetchProjectTranslations(transcriptId, lang);
    return response.translations.map(mapTranslationItem);
  }

  async updateTranslationSegment(translationId: string, text: string): Promise<TranslatedSegment> {
    await this.ensureApiRequestAuth();
    const response = await apiClient.put<TranslationItemResponse>(`/translation/segment/${translationId}`, {
      translated_text: text,
    });
    return mapTranslationItem(response);
  }

  async triggerTtsSynthesis(transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    await this.ensureApiRequestAuth();
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    return apiClient.post<{ job_id: string }>('/tts/synthesize-project', {
      transcript_id: transcriptId,
      target_language: lang,
      ...(normalizedProjectId ? { project_id: normalizedProjectId } : {}),
    });
  }

  async triggerLipSync(mediaId: string, transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    await this.ensureApiRequestAuth();
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    return apiClient.post<{ job_id: string }>('/lipsync/render-project', {
      media_file_id: mediaId,
      transcript_id: transcriptId,
      target_language: lang,
      ...(normalizedProjectId ? { project_id: normalizedProjectId } : {}),
      model_preference: 'liveportrait',
      burn_in_subtitles: false,
      enable_lipsync: true,
    });
  }

  async triggerDubOnly(mediaId: string, transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    await this.ensureApiRequestAuth();
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    return apiClient.post<{ job_id: string }>('/lipsync/render-project', {
      media_file_id: mediaId,
      transcript_id: transcriptId,
      target_language: lang,
      ...(normalizedProjectId ? { project_id: normalizedProjectId } : {}),
      model_preference: 'liveportrait',
      burn_in_subtitles: false,
      enable_lipsync: false,
    });
  }

  async getExportStatus(jobId: string): Promise<any> {
    await this.ensureApiRequestAuth();
    return apiClient.get<any>(`/lipsync/job/${jobId}`);
  }

  async getProjectRenderHistory(projectId: string): Promise<ProjectRenderHistoryItem[]> {
    await this.ensureApiRequestAuth();
    return apiClient.get<ProjectRenderHistoryItem[]>(`/lipsync/history?project_id=${encodeURIComponent(projectId)}`);
  }

  async retranslateSegment(params: {
    segmentId: string;
    sourceText: string;
    originalDurationMs: number;
    sourceLanguage: string;
    targetLanguage: string;
    speakerTag?: string;
    previousContext?: string;
    nextContext?: string;
  }): Promise<TranslatedSegment> {
    await this.ensureApiRequestAuth();
    const response = await apiClient.post<TranslationItemResponse>('/translation/translate-segment', {
      segment_id: params.segmentId,
      source_text: params.sourceText,
      original_duration_ms: params.originalDurationMs,
      source_language: params.sourceLanguage,
      target_language: params.targetLanguage,
      speaker_tag: params.speakerTag ?? 'Speaker 1',
      previous_context: params.previousContext ?? null,
      next_context: params.nextContext ?? null,
    });
    return mapTranslationItem(response);
  }

  async synthesizeSegment(translationId: string): Promise<{ audioUrl: string }> {
    await this.ensureApiRequestAuth();
    const response = await apiClient.post<{ audio_url: string }>('/tts/synthesize-segment', {
      translation_id: translationId,
    });
    return { audioUrl: response.audio_url };
  }
}

export const projectService = new ProjectService();
