import { apiClient } from './apiClient';
import type { Project } from '../store/projectStore';
import type { TranscriptSegment } from '../store/mediaStore';
import type { TranslatedSegment } from '../store/translationStore';

export interface UploadedMedia {
  media_id: string;
  filename: string;
  media_type: string;
  filesize_bytes: number;
  duration_seconds: number;
  status: string;
}

export interface TranscriptStatus {
  transcript_id: string;
  status: 'queued' | 'in_progress' | 'completed' | 'failed';
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

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function normalizeOptionalUuid(value?: string): string | undefined {
  return value && UUID_PATTERN.test(value) ? value : undefined;
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
    status: 'completed',
  };
}

export class ProjectService {
  async uploadMedia(file: File): Promise<UploadedMedia> {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<UploadedMedia>('/media/uploads/direct', formData);
  }

  async startTranscription(mediaId: string, language: string): Promise<{ transcript_id: string }> {
    return apiClient.post('/transcription/start', {
      media_id: mediaId,
      language,
      enable_noise_reduction: true,
      enable_loudness_norm: true,
      enable_vad: true,
    });
  }

  async getTranscription(transcriptId: string): Promise<TranscriptStatus> {
    return apiClient.get<TranscriptStatus>(`/transcription/${transcriptId}`);
  }

  async fetchAllProjects(): Promise<Project[]> {
    return apiClient.get<Project[]>('/projects');
  }

  async getProject(projectId: string): Promise<Project> {
    return apiClient.get<Project>(`/projects/${projectId}`);
  }

  async getTranscript(mediaId: string): Promise<TranscriptSegment[]> {
    return apiClient.get<TranscriptSegment[]>(`/transcription/${mediaId}/segments`);
  }

  async triggerProjectTranslation(transcriptId: string, sourceLanguage: string, targetLanguage: string): Promise<TranslationJobStatus> {
    return apiClient.post<TranslationJobStatus>('/translation/translate-project', {
      transcript_id: transcriptId,
      source_language: sourceLanguage,
      target_language: targetLanguage,
    });
  }

  async fetchProjectTranslations(transcriptId: string, lang: string): Promise<ProjectTranslationResponse> {
    return apiClient.get<ProjectTranslationResponse>(`/translation/${transcriptId}?target_language=${lang}`);
  }

  async fetchTranslations(transcriptId: string, lang: string): Promise<TranslatedSegment[]> {
    const response = await this.fetchProjectTranslations(transcriptId, lang);
    return response.translations.map(mapTranslationItem);
  }

  async updateTranslationSegment(translationId: string, text: string): Promise<TranslatedSegment> {
    const response = await apiClient.put<TranslationItemResponse>(`/translation/segment/${translationId}`, {
      translated_text: text,
    });
    return mapTranslationItem(response);
  }

  async triggerTtsSynthesis(transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    return apiClient.post<{ job_id: string }>('/tts/synthesize-project', {
      transcript_id: transcriptId,
      target_language: lang,
      ...(normalizedProjectId ? { project_id: normalizedProjectId } : {}),
    });
  }

  async triggerLipSync(mediaId: string, transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    const normalizedProjectId = normalizeOptionalUuid(projectId);
    return apiClient.post<{ job_id: string }>('/lipsync/render-project', {
      media_file_id: mediaId,
      transcript_id: transcriptId,
      target_language: lang,
      ...(normalizedProjectId ? { project_id: normalizedProjectId } : {}),
      model_preference: 'liveportrait',
      burn_in_subtitles: false,
    });
  }

  async getExportStatus(jobId: string): Promise<any> {
    return apiClient.get<any>(`/lipsync/job/${jobId}`);
  }
}

export const projectService = new ProjectService();
