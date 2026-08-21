import { create } from 'zustand';

export interface ExportJob {
  id: string;
  projectId: string;
  targetLanguage: string;
  burnInSubtitles: boolean;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progressPercent: number;
  outputVideoUrl?: string;
  error?: string;
  createdAt: string;
}

interface ExportState {
  jobs: ExportJob[];
  currentJob: ExportJob | null;
  setJobs: (jobs: ExportJob[]) => void;
  setCurrentJob: (job: ExportJob | null) => void;
  addJob: (job: ExportJob) => void;
  updateJobProgress: (jobId: string, progressPercent: number, status?: ExportJob['status']) => void;
}

export const useExportStore = create<ExportState>((set) => ({
  jobs: [],
  currentJob: null,

  setJobs: (jobs) => set({ jobs }),
  setCurrentJob: (job) => set({ currentJob: job }),
  addJob: (job) => set((state) => ({
    jobs: [job, ...state.jobs],
    currentJob: job,
  })),
  updateJobProgress: (jobId, progressPercent, status) => set((state) => {
    const updatedJobs = state.jobs.map((job) => {
      if (job.id === jobId) {
        const nextStatus = status || job.status;
        return { ...job, progressPercent, status: nextStatus };
      }
      return job;
    });
    const updatedCurrent = state.currentJob?.id === jobId
      ? { ...state.currentJob, progressPercent, status: status || state.currentJob.status }
      : state.currentJob;

    return { jobs: updatedJobs, currentJob: updatedCurrent };
  }),
}));
