'use client';


import React, { useEffect, useRef, useState } from 'react';
import { useProjectStore, Project } from '../store/projectStore';
import { storageService } from '../services/storageService';
import { apiClient } from '../services/apiClient';
import { projectService } from '../services/projectService';
import { authService, type AuthBootstrapResponse } from '../services/authService';
import { PublicLanding, WorkspaceHome, WorkspaceLoadingState, type HomeShellLanguageOption } from '../components/homeShell';
import { mapAuthError, mapLanguageLoadError, mapProjectCreateError, mapProjectLoadError } from '../services/userFacingErrors';

type SupportedLanguagesResponse = {
  languages: Array<{
    code: string;
    name: string;
    native_name: string;
  }>;
};

const fallbackLanguageOptions: HomeShellLanguageOption[] = [
  { value: 'ar', label: 'Arabic' },
  { value: 'bn', label: 'Bengali' },
  { value: 'de', label: 'German' },
  { value: 'el', label: 'Greek' },
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'gu', label: 'Gujarati' },
  { value: 'he', label: 'Hebrew' },
  { value: 'hi', label: 'Hindi' },
  { value: 'id', label: 'Indonesian' },
  { value: 'it', label: 'Italian' },
  { value: 'ja', label: 'Japanese' },
  { value: 'kn', label: 'Kannada' },
  { value: 'ko', label: 'Korean' },
  { value: 'ml', label: 'Malayalam' },
  { value: 'mr', label: 'Marathi' },
  { value: 'nl', label: 'Dutch' },
  { value: 'pa', label: 'Punjabi' },
  { value: 'pl', label: 'Polish' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'ru', label: 'Russian' },
  { value: 'sv', label: 'Swedish' },
  { value: 'ta', label: 'Tamil' },
  { value: 'te', label: 'Telugu' },
  { value: 'th', label: 'Thai' },
  { value: 'tr', label: 'Turkish' },
  { value: 'uk', label: 'Ukrainian' },
  { value: 'ur', label: 'Urdu' },
  { value: 'vi', label: 'Vietnamese' },
  { value: 'zh', label: 'Chinese (Simplified)' },
];

type EntryViewState = 'auth-loading' | 'signed-out' | 'workspace-loading' | 'workspace-empty' | 'workspace-ready';

function mapLocalDraftsToProjects(drafts: Awaited<ReturnType<typeof storageService.listDrafts>>): Project[] {
  return drafts.map((draft) => ({
    id: draft.projectMetadata.id,
    name: draft.projectMetadata.name,
    sourceLanguage: draft.projectMetadata.sourceLanguage,
    targetLanguage: draft.projectMetadata.targetLanguage,
    status: 'draft',
    createdAt: draft.projectMetadata.createdAt,
    updatedAt: draft.projectMetadata.updatedAt,
  }));
}

function deriveEntryViewState(
  authLoading: boolean,
  authContext: AuthBootstrapResponse | null,
  projectsLoading: boolean,
  projectsInitialized: boolean,
  projects: Project[],
): EntryViewState {
  if (authLoading) {
    return 'auth-loading';
  }

  if (!authContext) {
    return 'signed-out';
  }

  if (projectsLoading || !projectsInitialized) {
    return 'workspace-loading';
  }

  if (projects.length === 0) {
    return 'workspace-empty';
  }

  return 'workspace-ready';
}

export default function ProjectBrowser() {
  const { projects, setProjects, addProject } = useProjectStore();
  const [newProjectName, setNewProjectName] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('es');
  const [languageOptions, setLanguageOptions] = useState<HomeShellLanguageOption[]>(fallbackLanguageOptions);
  const [authContext, setAuthContext] = useState<AuthBootstrapResponse | null>(authService.getCachedContext());
  const [authError, setAuthError] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [languageLoadError, setLanguageLoadError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsInitialized, setProjectsInitialized] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [googleSignInReady, setGoogleSignInReady] = useState(false);
  const signInButtonRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const unsubscribe = authService.subscribeToAuthState((nextContext) => {
      if (!nextContext) {
        return;
      }

      setAuthContext(nextContext);
      setAuthError(null);
      setProjectError(null);
      setProjectsInitialized(false);
      setAuthLoading(false);
      setGoogleSignInReady(false);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function initializeAuth() {
      setAuthLoading(true);
      setAuthError(null);

      try {
        const context = await authService.bootstrap();
        if (!isMounted) {
          return;
        }

        setAuthContext(context);
        setGoogleSignInReady(!context && await authService.isGoogleSignInAvailable().catch(() => false));
      } catch (error) {
        console.error('Failed to initialize auth context:', error);
        if (!isMounted) {
          return;
        }
        setAuthContext(null);
        setAuthError(mapAuthError(error));
        setGoogleSignInReady(await authService.isGoogleSignInAvailable().catch(() => false));
      } finally {
        if (isMounted) {
          setAuthLoading(false);
        }
      }
    }

    async function loadSupportedLanguages() {
      try {
        const response = await apiClient.get<SupportedLanguagesResponse>('/translation/languages');
        const options = response.languages.map((language) => ({
          value: language.code,
          label: language.name,
        }));

        if (!isMounted || options.length === 0) {
          return;
        }

        setLanguageOptions(options);
        setSourceLang((current) => (options.some((option) => option.value === current) ? current : 'en'));
        setTargetLang((current) => {
          if (options.some((option) => option.value === current)) {
            return current;
          }

          return options.some((option) => option.value === 'es') ? 'es' : options[0].value;
        });
      } catch (error) {
        console.warn('Could not load supported languages from API, using fallback list:', error instanceof Error ? error.message : error);
        if (isMounted) {
          setLanguageLoadError(mapLanguageLoadError(error));
        }
      }
    }

    void initializeAuth();
    void loadSupportedLanguages();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadProjects() {
      if (!authContext) {
        setProjects([]);
        setProjectError(null);
        setProjectsLoading(false);
        setProjectsInitialized(false);
        return;
      }

      setProjectsLoading(true);
      setProjectsInitialized(false);
      setProjectError(null);

      try {
        await projectService.bootstrapAuthContext();
        const refreshedContext = authService.getCachedContext();
        if (refreshedContext && isMounted) {
          setAuthContext(refreshedContext);
        }

        const remoteProjects = await projectService.fetchAllProjects();
        if (!isMounted) {
          return;
        }

        setProjects(remoteProjects);
      } catch (remoteError) {
        console.warn('Failed to load backend projects, falling back to local drafts:', remoteError);

        try {
          const drafts = await storageService.listDrafts();
          if (!isMounted) {
            return;
          }

          setProjects(mapLocalDraftsToProjects(drafts));
          setProjectError('We could not refresh your workspace from the cloud just now. Showing any locally saved drafts while you reconnect.');
        } catch (draftError) {
          console.error('Failed to load projects:', draftError);
          if (!isMounted) {
            return;
          }

          setProjects([]);
          setProjectError(mapProjectLoadError(remoteError));
        }
      } finally {
        if (isMounted) {
          setProjectsLoading(false);
          setProjectsInitialized(true);
        }
      }
    }

    void loadProjects();

    return () => {
      isMounted = false;
    };
  }, [authContext, setProjects]);

  useEffect(() => {
    if (!googleSignInReady || authContext || !signInButtonRef.current) {
      return;
    }

    authService.renderGoogleSignInButton(signInButtonRef.current).catch((error) => {
      console.error('Failed to render Google sign-in button:', error);
      setAuthError(mapAuthError(error));
    });
  }, [authContext, googleSignInReady]);

  const handleSignIn = async () => {
    setAuthLoading(true);
    setAuthError(null);
    setProjectError(null);
    setProjectsInitialized(false);

    try {
      const context = await authService.ensureAuthenticatedContext();
      setAuthContext(context);
      setGoogleSignInReady(false);
    } catch (error) {
      console.error('Failed to sign in:', error);
      setAuthError(mapAuthError(error));
      setGoogleSignInReady(await authService.isGoogleSignInAvailable().catch(() => false));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSignOut = () => {
    authService.signOut();
    setAuthContext(null);
    setProjects([]);
    setAuthError(null);
    setProjectError(null);
    setProjectsLoading(false);
    setProjectsInitialized(false);
    setGoogleSignInReady(true);
  };

  const handleCreateProject = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedProjectName = newProjectName.trim();

    if (!trimmedProjectName) {
      return;
    }

    setIsCreatingProject(true);
    setProjectError(null);

    const now = new Date().toISOString();
    const fallbackProjectId = crypto.randomUUID();

    try {
      let newProject: Project;

      if (projectService.hasProjectApiScope()) {
        try {
          await projectService.bootstrapAuthContext();
          newProject = await projectService.createProjectShellWithDraft(trimmedProjectName, sourceLang, targetLang);
        } catch (remoteError) {
          console.warn('Failed to create canonical backend project draft, falling back to local draft:', remoteError);
          newProject = {
            id: fallbackProjectId,
            name: trimmedProjectName,
            sourceLanguage: sourceLang,
            targetLanguage: targetLang,
            status: 'draft',
            createdAt: now,
            updatedAt: now,
          };
          setProjectError('We saved this project locally, but could not sync it to your workspace yet. Keep this tab open and try again shortly.');
        }
      } else {
        newProject = {
          id: fallbackProjectId,
          name: trimmedProjectName,
          sourceLanguage: sourceLang,
          targetLanguage: targetLang,
          status: 'draft',
          createdAt: now,
          updatedAt: now,
        };
      }

      await storageService.saveDraft(projectService.buildLocalDraftFromProject(newProject));
      addProject(newProject);
      setNewProjectName('');
    } catch (error) {
      console.error('Failed to create project:', error);
      setProjectError(mapProjectCreateError(error));
    } finally {
      setIsCreatingProject(false);
    }
  };

  const handleSwapLanguages = () => {
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
  };

  const refreshProjects = async () => {
    const refreshedProjects = await projectService.fetchAllProjects();
    setProjects(refreshedProjects);
  };

  const handleRenameProject = async (projectId: string, name: string) => {
    await projectService.renameProject(projectId, name);
    await refreshProjects();
  };

  const handleArchiveProject = async (projectId: string) => {
    await projectService.archiveProject(projectId);
    await refreshProjects();
  };

  const handleDuplicateProject = async (projectId: string) => {
    await projectService.duplicateProject(projectId);
    await refreshProjects();
  };

  const entryViewState = deriveEntryViewState(
    authLoading,
    authContext,
    projectsLoading,
    projectsInitialized,
    projects,
  );

  if (entryViewState === 'auth-loading') {
    return (
      <WorkspaceLoadingState
        authContext={authContext}
        onSignOut={authContext ? handleSignOut : undefined}
        title="Opening GlobeSync"
        description="Restoring your session and preparing your workspace."
      />
    );
  }

  if (entryViewState === 'signed-out') {
    return (
      <PublicLanding
        signInSlot={googleSignInReady ? (
          <div ref={signInButtonRef} />
        ) : (
          <button
            type="button"
            onClick={handleSignIn}
            className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-200"
          >
            Continue with Google
          </button>
        )}
        authError={authError}
      />
    );
  }

  if (entryViewState === 'workspace-loading' && authContext) {
    return (
      <WorkspaceLoadingState
        authContext={authContext}
        onSignOut={handleSignOut}
        title="Loading your workspace"
        description="Restoring your GlobeSync projects and preparing project creation."
      />
    );
  }

  return authContext ? (
    <WorkspaceHome
      authContext={authContext}
      projects={projects}
      newProjectName={newProjectName}
      sourceLang={sourceLang}
      targetLang={targetLang}
      languageOptions={languageOptions}
      isCreatingProject={isCreatingProject}
      projectError={projectError}
      languageLoadError={languageLoadError}
      onProjectNameChange={setNewProjectName}
      onSourceLangChange={setSourceLang}
      onTargetLangChange={setTargetLang}
      onSwapLanguages={handleSwapLanguages}
      onCreateProject={handleCreateProject}
      onSignOut={handleSignOut}
      onRename={handleRenameProject}
      onArchive={handleArchiveProject}
      onDuplicate={handleDuplicateProject}
    />
  ) : null;
}
