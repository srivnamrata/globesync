import { create } from 'zustand';

export interface Project {
  id: string;
  name: string;
  sourceLanguage: string;
  targetLanguage: string;
  status: 'draft' | 'processing' | 'completed' | 'failed';
  createdAt: string;
  updatedAt: string;
  transcriptId?: string;
  mediaId?: string;
  originalVideoUrl?: string;
  dubbedAudioUrl?: string;
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

  setCurrentProject: (project) => set({ currentProject: project }),
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
