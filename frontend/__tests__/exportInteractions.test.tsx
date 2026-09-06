import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExportDialog } from '../components/ExportHub/ExportDialog';
import { ExportProgress } from '../components/ExportHub/ExportProgress';
import { ExportQueue } from '../components/ExportHub/ExportQueue';
import { useExportStore } from '../store/exportStore';
import { useUIStore } from '../store/uiStore';

const api = vi.hoisted(() => ({ post: vi.fn() }));
const processing = vi.hoisted(() => ({ status: null as unknown, error: null as string | null }));

vi.mock('../services/apiClient', () => ({ apiClient: api }));
vi.mock('../hooks/useProcessingStatus', () => ({
  useProcessingStatus: () => processing,
}));

describe('export interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ isExportDialogOpen: false });
    useExportStore.setState({ jobs: [], currentJob: null });
    processing.status = null;
    processing.error = null;
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('configures and queues an export job', async () => {
    const user = userEvent.setup();
    useUIStore.setState({ isExportDialogOpen: true });
    api.post.mockResolvedValue({ job_id: 'export-1' });
    render(
      <ExportDialog
        projectId="project-1"
        mediaFileId="media-1"
        transcriptId="transcript-1"
        targetLanguage="es"
        durationSeconds={120}
      />,
    );

    const selects = screen.getAllByRole('combobox');
    await user.selectOptions(selects[0], 'webm');
    await user.selectOptions(selects[1], '4k');
    await user.selectOptions(selects[2], 'h265');
    await user.click(screen.getByRole('checkbox', { name: /Burn Subtitles/ }));
    await user.click(screen.getByRole('checkbox', { name: /Color-Grade/ }));
    await user.click(screen.getByRole('button', { name: 'Queue Render Task' }));

    expect(api.post).toHaveBeenCalledWith('/export/render', expect.objectContaining({
      media_file_id: 'media-1',
      transcript_id: 'transcript-1',
      project_id: 'project-1',
      target_language: 'es',
      format: 'webm',
      resolution: '4k',
      codec: 'h265',
      subtitles: expect.objectContaining({ enabled: true }),
      post_processing: expect.objectContaining({ color_grading: true }),
    }));
    expect(useExportStore.getState().currentJob).toMatchObject({
      id: 'export-1',
      status: 'queued',
      burnInSubtitles: true,
    });
    expect(useUIStore.getState().isExportDialogOpen).toBe(false);
  });

  it('closes the dialog without queueing', async () => {
    const user = userEvent.setup();
    useUIStore.setState({ isExportDialogOpen: true });
    render(
      <ExportDialog
        projectId="project-1"
        mediaFileId="media-1"
        transcriptId="transcript-1"
        targetLanguage="es"
        durationSeconds={30}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(useUIStore.getState().isExportDialogOpen).toBe(false);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('keeps the dialog open when export creation fails', async () => {
    const user = userEvent.setup();
    useUIStore.setState({ isExportDialogOpen: true });
    api.post.mockRejectedValue(new Error('queue failed'));
    render(
      <ExportDialog
        projectId="project-1"
        mediaFileId="media-1"
        transcriptId="transcript-1"
        targetLanguage="es"
        durationSeconds={30}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Queue Render Task' }));
    expect(useUIStore.getState().isExportDialogOpen).toBe(true);
    expect(useExportStore.getState().jobs).toEqual([]);
  });

  it('cancels only active export queue jobs', async () => {
    const user = userEvent.setup();
    useExportStore.setState({
      jobs: [
        {
          id: 'active-job-1234',
          projectId: 'project-1',
          targetLanguage: 'es',
          burnInSubtitles: false,
          status: 'processing',
          progressPercent: 25,
          createdAt: '2026-01-01T00:00:00.000Z',
        },
        {
          id: 'complete-job',
          projectId: 'project-1',
          targetLanguage: 'fr',
          burnInSubtitles: false,
          status: 'completed',
          progressPercent: 100,
          createdAt: '2026-01-01T00:00:00.000Z',
        },
      ],
    });
    api.post.mockResolvedValue({});
    render(<ExportQueue />);
    expect(screen.queryByText(/complete-job/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).toHaveBeenCalledWith('/export/job/active-job-1234/cancel', {});
    expect(useExportStore.getState().jobs[0]).toMatchObject({
      status: 'failed',
      progressPercent: 0,
    });
  });

  it('renders processing progress, ETA, and stream failures', () => {
    processing.status = {
      status: 'in_progress',
      progress_percent: 45,
      message: 'Encoding',
      eta_seconds: 12.2,
    };
    processing.error = 'Stream disconnected';
    render(<ExportProgress jobId="job-1" />);
    expect(screen.getByText('Stage: Encoding')).toBeInTheDocument();
    expect(screen.getByText('ETA: 13s')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByText('Stream disconnected')).toBeInTheDocument();
  });

  it('hides absent progress and highlights failures', () => {
    const { rerender } = render(<ExportProgress jobId={undefined} />);
    expect(screen.queryByText('Render Progress Status')).not.toBeInTheDocument();

    processing.status = {
      status: 'failed',
      progress_percent: 10,
      message: '',
      eta_seconds: 0,
    };
    rerender(<ExportProgress jobId="job-1" />);
    expect(screen.getByText('Stage: Queued in worker pool')).toBeInTheDocument();
    expect(screen.getByText('10%')).toHaveClass('text-red-400');
  });
});
