import { create } from 'zustand';

export interface Project {
  id: string;
  name: string;
  sourceLanguage: string;
  targetLanguage: string;
  status: 'draft' | 'processing' | 'completed' | 'failed' | 'archived';
  createdAt: string;
  updatedAt: string;
  transcriptId?: string;
  mediaId?: string;
  mediaFilename?: string;
  mediaDurationSeconds?: number;
  pipelineStage?: string;
  pipelineStatus?: string;
  pipelineProgressPercent?: number;
  pipelineErrorMessage?: string;
  currentLipsyncJobId?: string;
  lastRenderedVideoPath?: string;
}

interface ProjectState {
  currentProject: Project | null;
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  setCurrentProject: (project: Project | null) => void;
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  updateProjectStatus: (projectId: string, status: Project['status']) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  currentProject: null,
  projects: [],
  isLoading: false,
  error: null,

  setCurrentProject: (project) => set((state) => {
    if (!project) {
      return { currentProject: null };
    }

    const existingIndex = state.projects.findIndex((candidate) => candidate.id === project.id);
    const projects = existingIndex >= 0
      ? state.projects.map((candidate) => (candidate.id === project.id ? project : candidate))
      : [project, ...state.projects];

    return {
      currentProject: project,
      projects,
    };
  }),
  setProjects: (projects) => set({ projects }),
  addProject: (project) => set((state) => ({
    projects: [project, ...state.projects]
  })),
  updateProjectStatus: (projectId, status) => set((state) => {
    const updatedProjects = state.projects.map((p) =>
      p.id === projectId ? { ...p, status, updatedAt: new Date().toISOString() } : p
    );
    const updatedCurrent = state.currentProject?.id === projectId
      ? { ...state.currentProject, status, updatedAt: new Date().toISOString() }
      : state.currentProject;
    return { projects: updatedProjects, currentProject: updatedCurrent };
  }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
}));
