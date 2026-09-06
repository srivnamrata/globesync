import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExportHistory } from '../components/ExportHub/ExportHistory';
import { ExportReadiness } from '../components/ExportHub/ExportReadiness';
import { PipelineStatus } from '../components/ExportHub/PipelineStatus';
import type { TranscriptSegment } from '../store/mediaStore';
import type { TranslatedSegment } from '../store/translationStore';

const projectApi = vi.hoisted(() => ({
  getProjectRenderHistory: vi.fn(),
  getProjectExportHistory: vi.fn(),
}));

vi.mock('../services/projectService', () => ({ projectService: projectApi }));

const segments: TranscriptSegment[] = [
  {
    id: 'segment-1',
    sequenceOrder: 1,
    startTimeSeconds: 0,
    endTimeSeconds: 2,
    durationSeconds: 2,
    speakerTag: 'Speaker 1',
    text: 'Hello',
    confidence: 0.9,
  },
  {
    id: 'segment-2',
    sequenceOrder: 2,
    startTimeSeconds: 2,
    endTimeSeconds: 4,
    durationSeconds: 2,
    speakerTag: 'Speaker 2',
    text: 'World',
    confidence: 0.8,
  },
];

const translated = (
  segmentId: string,
  overrides: Partial<TranslatedSegment> = {},
): TranslatedSegment => ({
  id: `translation-${segmentId}`,
  transcriptSegmentId: segmentId,
  translatedText: 'Hola',
  originalDurationMs: 2000,
  estimatedDurationMs: 2000,
  durationRatio: 1,
  speedAdjustmentFactor: 1,
  qualityScore: 0.9,
  generatedAudioStatus: 'ready',
  status: 'completed',
  ...overrides,
});

describe('ExportReadiness', () => {
  it('reports blocking requirements and pluralizes segment issues', () => {
    render(
      <ExportReadiness
        hasDraftConflict
        hasMedia={false}
        hasTranscript={false}
        dirtySegmentCount={0}
        segments={segments}
        translations={{}}
      />,
    );

    expect(screen.getByText('Action required')).toBeInTheDocument();
    expect(screen.getByText('Source media is required')).toBeInTheDocument();
    expect(screen.getByText('A completed transcript is required')).toBeInTheDocument();
    expect(screen.getByText('2 segments has no translation')).toBeInTheDocument();
    expect(screen.getByText('draft conflict needs review before rendering')).toBeInTheDocument();
  });

  it('distinguishes quality warnings from render blockers', () => {
    render(
      <ExportReadiness
        hasDraftConflict={false}
        hasMedia
        hasTranscript
        dirtySegmentCount={2}
        segments={segments}
        translations={{
          'segment-1': translated('segment-1', {
            durationRatio: 1.3,
            qualityScore: 0.4,
            generatedAudioStatus: 'pending',
          }),
          'segment-2': translated('segment-2'),
        }}
      />,
    );

    expect(screen.getByText('Ready to build')).toBeInTheDocument();
    expect(screen.getByText('2 edited segments have not been saved')).toBeInTheDocument();
    expect(screen.getByText('segment needs timing-fit review')).toBeInTheDocument();
    expect(screen.getByText('segment has low translation confidence')).toBeInTheDocument();
    expect(screen.getByText('segment audio will be synthesized during build')).toBeInTheDocument();
  });

  it('announces when every readiness check passes', () => {
    render(
      <ExportReadiness
        hasDraftConflict={false}
        hasMedia
        hasTranscript
        dirtySegmentCount={0}
        segments={segments}
        translations={{
          'segment-1': translated('segment-1'),
          'segment-2': translated('segment-2'),
        }}
      />,
    );

    expect(screen.getByText('All checks passed')).toBeInTheDocument();
    expect(screen.getByText('2/2')).toBeInTheDocument();
  });
});

describe('PipelineStatus', () => {
  it('clamps progress and renders upstream prerequisite state', () => {
    render(
      <PipelineStatus
        mode="upstream"
        status="in_progress"
        progressPercent={140}
        currentStage="voice"
        hasMedia
        hasTranscript
        translationCount={2}
        segmentCount={2}
      />,
    );

    expect(screen.getByText('Project processing status')).toBeInTheDocument();
    expect(screen.getByText('Generating voice')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '100% during Voice');
  });

  it('uses stage copy instead of showing 0 percent', () => {
    render(
      <PipelineStatus
        mode="dub_only"
        status="in_progress"
        progressPercent={0}
        currentStage="translate"
        hasMedia
        hasTranscript
        translationCount={0}
        segmentCount={1}
      />,
    );

    expect(screen.getByText('Translating')).toBeInTheDocument();
    expect(screen.queryByText('0% in progress')).not.toBeInTheDocument();
  });

  it('omits lip-sync for dub-only builds and renders completion', () => {
    render(
      <PipelineStatus
        mode="dub_only"
        status="completed"
        progressPercent={100}
        currentStage="export"
        hasMedia
        hasTranscript
        translationCount={1}
        segmentCount={1}
      />,
    );

    expect(screen.getByText('Dub build status')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByText('Lip-sync')).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('maps legacy lip-sync stage copy to export for dub-only builds', () => {
    render(
      <PipelineStatus
        mode="dub_only"
        status="in_progress"
        progressPercent={42}
        currentStage="lip_sync"
        hasMedia
        hasTranscript
        translationCount={1}
        segmentCount={1}
      />,
    );

    expect(screen.getByText('Currently Export.')).toBeInTheDocument();
    expect(screen.getByText('Exporting')).toBeInTheDocument();
    expect(screen.queryByText('Lip-sync')).not.toBeInTheDocument();
  });

  it('treats succeeded exports as completed for stage styling and badge copy', () => {
    render(
      <PipelineStatus
        mode="dub_only"
        status="succeeded"
        progressPercent={100}
        currentStage="export"
        hasMedia
        hasTranscript
        translationCount={1}
        segmentCount={1}
      />,
    );

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('The build is complete.')).toBeInTheDocument();
  });

  it.each([
    ['transcribe', 'retry transcription'],
    ['translate', 'retry translation'],
    ['voice', 'voice configuration'],
    ['lip-sync', 'lip-sync provider'],
    ['export', 'final artifact'],
    ['unknown', 'Review the project inputs'],
  ])('renders safe recovery guidance for %s failures', (stage, expected) => {
    const { unmount } = render(
      <PipelineStatus
        mode="dub_and_lipsync"
        status="failed"
        progressPercent={25}
        currentStage={stage}
        lastSuccessfulStage="upload"
        errorMessage="Worker stopped."
        hasMedia
        hasTranscript={false}
        translationCount={0}
        segmentCount={0}
      />,
    );

    expect(screen.getByText(new RegExp(expected, 'i'))).toBeInTheDocument();
    expect(screen.getByText(/Last successful checkpoint: Upload/)).toBeInTheDocument();
    unmount();
  });
});

describe('ExportHistory', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('loads render history before format history and renders download links', async () => {
    let resolveRender!: (value: unknown[]) => void;
    projectApi.getProjectRenderHistory.mockImplementation(() => new Promise((resolve) => {
      resolveRender = resolve;
    }));
    projectApi.getProjectExportHistory.mockResolvedValue([{
      id: 'export-1',
      target_language: 'fr',
      format: 'mp4',
      resolution: '1080p',
      status: 'completed',
      progress_percent: 100,
      current_stage: 'completed',
      output_video_url: 'https://cdn.test/export.mp4',
      filesize_bytes: 2 * 1024 * 1024,
      created_at: '2026-01-02T00:00:00.000Z',
    }]);

    render(<ExportHistory projectId="project-1" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading export history');
    expect(projectApi.getProjectExportHistory).not.toHaveBeenCalled();

    resolveRender([{
      job_id: 'render-1',
      target_language: 'es',
      render_mode: 'dub_and_lipsync',
      status: 'completed',
      progress_percent: 100,
      current_stage: 'completed',
      output_video_url: 'https://cdn.test/render.mp4',
      download_video_url: 'https://cdn.test/render-download.mp4',
      output_filesize_bytes: 1024 * 1024,
      execution_time_seconds: 75,
      quality_score: 0.9,
      created_at: '2026-01-01T00:00:00.000Z',
    }]);

    expect(await screen.findByText('Dub + Lip-Sync')).toBeInTheDocument();
    expect(await screen.findByText('mp4 | 1080p | fr')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Download dub and lip-sync/ }))
      .toHaveAttribute('href', 'https://cdn.test/render-download.mp4');
    expect(screen.getByRole('link', { name: /Download mp4 1080p/ }))
      .toHaveAttribute('href', 'https://cdn.test/export.mp4');
    expect(projectApi.getProjectRenderHistory.mock.invocationCallOrder[0])
      .toBeLessThan(projectApi.getProjectExportHistory.mock.invocationCallOrder[0]);
  });

  it('retains successful render results when format history fails and retries both', async () => {
    const user = userEvent.setup();
    projectApi.getProjectRenderHistory.mockResolvedValue([{
      job_id: 'render-1',
      target_language: 'es',
      render_mode: 'dub_only',
      status: 'failed',
      progress_percent: 55,
      current_stage: 'voice',
      last_successful_stage: 'translate',
      output_video_url: null,
      output_filesize_bytes: null,
      execution_time_seconds: 10,
      quality_score: 0,
      created_at: '2026-01-01T00:00:00.000Z',
    }]);
    projectApi.getProjectExportHistory
      .mockRejectedValueOnce(new Error('format history unavailable'))
      .mockResolvedValueOnce([]);

    render(<ExportHistory projectId="project-1" />);

    expect(await screen.findByText('Dub only')).toBeInTheDocument();
    expect(screen.getByText(/Last successful stage: Translate/)).toBeInTheDocument();
    expect(screen.getByText('Format export history unavailable')).toBeInTheDocument();
    expect(screen.getByText('No output')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry export history' }));
    await waitFor(() => expect(projectApi.getProjectRenderHistory).toHaveBeenCalledTimes(2));
    expect(projectApi.getProjectExportHistory).toHaveBeenCalledTimes(2);
  });

  it('shows independent render history failure while preserving format exports', async () => {
    projectApi.getProjectRenderHistory.mockRejectedValue(new Error('render unavailable'));
    projectApi.getProjectExportHistory.mockResolvedValue([{
      id: 'export-1',
      target_language: 'de',
      format: 'webm',
      resolution: '720p',
      status: 'processing',
      progress_percent: 40,
      current_stage: 'muxing',
      created_at: '2026-01-02T00:00:00.000Z',
    }]);

    render(<ExportHistory projectId="project-1" />);

    expect(await screen.findByText('Dub and Lip-Sync history unavailable')).toBeInTheDocument();
    expect(screen.getByText('webm | 720p | de')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
  });

  it('renders a deterministic empty state', async () => {
    projectApi.getProjectRenderHistory.mockResolvedValue([]);
    projectApi.getProjectExportHistory.mockResolvedValue([]);

    render(<ExportHistory projectId="project-1" />);

    expect(await screen.findByText('No exports have been created for this project yet.'))
      .toBeInTheDocument();
  });
});
