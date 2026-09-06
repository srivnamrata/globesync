import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authContextFixture, draftFixture, projectFixture } from '../test/fixtures';
import { useProjectStore } from '../store/projectStore';

const auth = vi.hoisted(() => ({
  getCachedContext: vi.fn(),
  subscribeToAuthState: vi.fn(),
  bootstrap: vi.fn(),
  listAvailableWorkspaces: vi.fn(),
  listWorkspaceMembers: vi.fn(),
  isGoogleSignInAvailable: vi.fn(),
  renderGoogleSignInButton: vi.fn(),
  ensureAuthenticatedContext: vi.fn(),
  signOut: vi.fn(),
  switchWorkspace: vi.fn(),
}));
const projectApi = vi.hoisted(() => ({
  bootstrapAuthContext: vi.fn(),
  fetchAllProjects: vi.fn(),
  hasProjectApiScope: vi.fn(),
  createProjectShellWithDraft: vi.fn(),
  buildLocalDraftFromProject: vi.fn(),
  renameProject: vi.fn(),
  archiveProject: vi.fn(),
  duplicateProject: vi.fn(),
}));
const storage = vi.hoisted(() => ({
  listDrafts: vi.fn(),
  saveDraft: vi.fn(),
}));
const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../services/authService', () => ({ authService: auth }));
vi.mock('../services/projectService', () => ({ projectService: projectApi }));
vi.mock('../services/storageService', () => ({ storageService: storage }));
vi.mock('../services/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/apiClient')>();
  return { ...actual, apiClient: api };
});
vi.mock('../components/homeShell', () => ({
  PublicLanding: ({ signInSlot, authError }: {
    signInSlot: React.ReactNode;
    authError: string | null;
  }) => <div data-testid="public-landing">{signInSlot}{authError}</div>,
  WorkspaceLoadingState: ({ title }: { title: string }) => <div>{title}</div>,
  WorkspaceHome: (props: {
    projects: Array<{ name: string }>;
    newProjectName: string;
    projectError: string | null;
    languageLoadError: string | null;
    onProjectNameChange: (value: string) => void;
    onCreateProject: (event: React.FormEvent<HTMLFormElement>) => void;
    onRename: (id: string, name: string) => Promise<void>;
    onArchive: (id: string) => Promise<void>;
    onDuplicate: (id: string) => Promise<void>;
    onWorkspaceChange: (id: string) => Promise<void>;
    onSwapLanguages: () => void;
    onSignOut: () => void;
  }) => (
    <div data-testid="workspace-home">
      <span>{props.projects.map((project) => project.name).join(',')}</span>
      <span>{props.projectError}</span>
      <span>{props.languageLoadError}</span>
      <form onSubmit={props.onCreateProject}>
        <input
          aria-label="Project name"
          value={props.newProjectName}
          onChange={(event) => props.onProjectNameChange(event.target.value)}
        />
        <button type="submit">Create</button>
      </form>
      <button onClick={props.onSwapLanguages}>Swap</button>
      <button onClick={() => void props.onRename(projectFixture.id, 'Renamed')}>Rename</button>
      <button onClick={() => void props.onArchive(projectFixture.id)}>Archive</button>
      <button onClick={() => void props.onDuplicate(projectFixture.id)}>Duplicate</button>
      <button onClick={() => void props.onWorkspaceChange('workspace-2')}>Workspace</button>
      <button onClick={props.onSignOut}>Sign out</button>
    </div>
  ),
}));

import ProjectBrowser from '../app/page';

describe('ProjectBrowser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({ projects: [], currentProject: null, isLoading: false, error: null });
    auth.getCachedContext.mockReturnValue(null);
    auth.subscribeToAuthState.mockReturnValue(vi.fn());
    auth.bootstrap.mockResolvedValue(null);
    auth.listAvailableWorkspaces.mockResolvedValue([]);
    auth.listWorkspaceMembers.mockResolvedValue([]);
    auth.isGoogleSignInAvailable.mockResolvedValue(false);
    auth.renderGoogleSignInButton.mockResolvedValue(undefined);
    auth.ensureAuthenticatedContext.mockResolvedValue(authContextFixture);
    auth.switchWorkspace.mockResolvedValue({
      ...authContextFixture,
      workspace: { ...authContextFixture.workspace, id: 'workspace-2' },
    });
    projectApi.bootstrapAuthContext.mockResolvedValue({
      workspaceId: 'workspace-1',
      actorUserId: 'user-1',
    });
    projectApi.fetchAllProjects.mockResolvedValue([projectFixture]);
    projectApi.hasProjectApiScope.mockReturnValue(true);
    projectApi.createProjectShellWithDraft.mockResolvedValue(projectFixture);
    projectApi.buildLocalDraftFromProject.mockReturnValue(draftFixture);
    projectApi.renameProject.mockResolvedValue(projectFixture);
    projectApi.archiveProject.mockResolvedValue(projectFixture);
    projectApi.duplicateProject.mockResolvedValue(projectFixture);
    storage.listDrafts.mockResolvedValue([]);
    storage.saveDraft.mockResolvedValue(undefined);
    api.get.mockResolvedValue({
      languages: [
        { code: 'en', name: 'English', native_name: 'English' },
        { code: 'es', name: 'Spanish', native_name: 'Español' },
      ],
    });
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('renders the public landing after unauthenticated bootstrap', async () => {
    render(<ProjectBrowser />);

    expect(screen.getByText('Opening GlobeSync')).toBeInTheDocument();
    expect(await screen.findByTestId('public-landing')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue with Google' })).toBeInTheDocument();
    expect(auth.listAvailableWorkspaces).not.toHaveBeenCalled();
    expect(auth.listWorkspaceMembers).not.toHaveBeenCalled();
  });

  it('signs in from the public landing and loads remote projects', async () => {
    const user = userEvent.setup();
    render(<ProjectBrowser />);
    await user.click(await screen.findByRole('button', { name: 'Continue with Google' }));

    expect(await screen.findByTestId('workspace-home')).toHaveTextContent('Launch film');
    expect(auth.ensureAuthenticatedContext).toHaveBeenCalled();
    expect(projectApi.fetchAllProjects).toHaveBeenCalled();
  });

  it('loads workspace context, projects, members, and language metadata', async () => {
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    render(<ProjectBrowser />);

    expect(await screen.findByTestId('workspace-home')).toHaveTextContent('Launch film');
    expect(projectApi.bootstrapAuthContext).toHaveBeenCalled();
    expect(auth.listAvailableWorkspaces).toHaveBeenCalled();
    expect(auth.listWorkspaceMembers).toHaveBeenCalled();
    expect(api.get).toHaveBeenCalledWith('/translation/languages');
  });

  it('recovers workspace projects from IndexedDB when cloud loading fails', async () => {
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    projectApi.fetchAllProjects.mockRejectedValue(new Error('network error'));
    storage.listDrafts.mockResolvedValue([draftFixture]);

    render(<ProjectBrowser />);

    const workspace = await screen.findByTestId('workspace-home');
    expect(workspace).toHaveTextContent('Launch film');
    expect(workspace).toHaveTextContent('Showing any locally saved drafts');
  });

  it('surfaces workspace load failure when local recovery also fails', async () => {
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    projectApi.fetchAllProjects.mockRejectedValue(new Error('network error'));
    storage.listDrafts.mockRejectedValue(new Error('IndexedDB unavailable'));

    render(<ProjectBrowser />);

    expect(await screen.findByText(/GlobeSync could not reach the service/))
      .toBeInTheDocument();
  });

  it('uses fallback languages and reports language API failures', async () => {
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    api.get.mockRejectedValue(new Error('network error'));

    render(<ProjectBrowser />);

    expect(await screen.findByText(/GlobeSync could not reach the service/))
      .toBeInTheDocument();
  });

  it('creates a canonical project and caches its draft', async () => {
    const user = userEvent.setup();
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    render(<ProjectBrowser />);
    await screen.findByTestId('workspace-home');

    await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'Launch');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(projectApi.createProjectShellWithDraft)
      .toHaveBeenCalledWith('Launch', 'en', 'es'));
    expect(storage.saveDraft).toHaveBeenCalledWith(draftFixture);
  });

  it('falls back to a recoverable local project when canonical creation fails', async () => {
    const user = userEvent.setup();
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    projectApi.createProjectShellWithDraft.mockRejectedValue(new Error('cloud unavailable'));
    projectApi.buildLocalDraftFromProject.mockImplementation((project) => ({
      ...draftFixture,
      projectMetadata: { ...draftFixture.projectMetadata, id: project.id, name: project.name },
    }));
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('22222222-2222-4222-8222-222222222222');
    render(<ProjectBrowser />);
    await screen.findByTestId('workspace-home');

    await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'Offline draft');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText(/saved this project locally/)).toBeInTheDocument();
    expect(storage.saveDraft).toHaveBeenCalledWith(expect.objectContaining({
      projectMetadata: expect.objectContaining({
        id: '22222222-2222-4222-8222-222222222222',
        name: 'Offline draft',
      }),
    }));
  });

  it('supports local-only creation when project scope is unavailable', async () => {
    const user = userEvent.setup();
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    projectApi.hasProjectApiScope.mockReturnValue(false);
    render(<ProjectBrowser />);
    await screen.findByTestId('workspace-home');

    await user.type(screen.getByRole('textbox', { name: 'Project name' }), 'Local');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(projectApi.createProjectShellWithDraft).not.toHaveBeenCalled();
    expect(storage.saveDraft).toHaveBeenCalled();
  });

  it('wires project actions, workspace switching, swapping, and sign out', async () => {
    const user = userEvent.setup();
    auth.getCachedContext.mockReturnValue(authContextFixture);
    auth.bootstrap.mockResolvedValue(authContextFixture);
    render(<ProjectBrowser />);
    await screen.findByTestId('workspace-home');

    await user.click(screen.getByRole('button', { name: 'Rename' }));
    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Duplicate' }));
    await user.click(screen.getByRole('button', { name: 'Workspace' }));
    await user.click(screen.getByRole('button', { name: 'Swap' }));
    await user.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(projectApi.renameProject).toHaveBeenCalledWith(projectFixture.id, 'Renamed');
    expect(projectApi.archiveProject).toHaveBeenCalledWith(projectFixture.id);
    expect(projectApi.duplicateProject).toHaveBeenCalledWith(projectFixture.id);
    expect(auth.switchWorkspace).toHaveBeenCalledWith('workspace-2');
    expect(auth.signOut).toHaveBeenCalled();
    expect(await screen.findByTestId('public-landing')).toBeInTheDocument();
  });

  it('reacts to a later authenticated subscription update', async () => {
    let listener!: (context: typeof authContextFixture) => void;
    auth.subscribeToAuthState.mockImplementation((callback) => {
      listener = callback;
      return vi.fn();
    });
    render(<ProjectBrowser />);
    await screen.findByTestId('public-landing');

    listener(authContextFixture);

    expect(await screen.findByTestId('workspace-home')).toHaveTextContent('Launch film');
  });
});
