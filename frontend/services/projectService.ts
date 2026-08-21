import { apiClient } from './apiClient';
import { Project } from '../store/projectStore';
import { TranscriptSegment } from '../store/mediaStore';
import { TranslatedSegment } from '../store/translationStore';

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

  async fetchTranslations(transcriptId: string, lang: string): Promise<TranslatedSegment[]> {
    return apiClient.get<TranslatedSegment[]>(`/translation/segments?transcript_id=${transcriptId}&lang=${lang}`);
  }

  async updateTranslationSegment(translationId: string, text: string): Promise<TranslatedSegment> {
    return apiClient.post<TranslatedSegment>(`/translation/segment/${translationId}/edit`, {
      translated_text: text,
    });
  }

  async triggerTtsSynthesis(transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    return apiClient.post<{ job_id: string }>('/tts/synthesize-project', {
      transcript_id: transcriptId,
      target_language: lang,
      project_id: projectId,
    });
  }

  async triggerLipSync(mediaId: string, transcriptId: string, lang: string, projectId: string): Promise<{ job_id: string }> {
    return apiClient.post<{ job_id: string }>('/lipsync/render-project', {
      media_file_id: mediaId,
      transcript_id: transcriptId,
      target_language: lang,
      project_id: projectId,
      model_preference: 'liveportrait',
      burn_in_subtitles: false,
    });
  }

  async getExportStatus(jobId: string): Promise<any> {
    return apiClient.get<any>(`/lipsync/job/${jobId}`);
  }
}

export const projectService = new ProjectService();
