import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  PublicLanding,
  WorkspaceHome,
  WorkspaceLoadingState,
  type HomeShellLanguageOption,
} from '../components/homeShell';
import { authContextFixture } from '../test/fixtures';
import type { Project } from '../store/projectStore';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>{children}</a>
  ),
}));

const languages: HomeShellLanguageOption[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'ar', label: 'Arabic' },
];

const projects: Project[] = [
  {
    id: 'project-complete',
    name: 'Alpha launch',
    sourceLanguage: 'en',
    targetLanguage: 'es',
    status: 'completed',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-04T00:00:00.000Z',
    mediaId: 'media-1',
    mediaFilename: 'alpha.mp4',
    mediaDurationSeconds: 65,
  },
  {
    id: 'project-processing',
    name: 'Beta launch',
    sourceLanguage: 'ar',
    targetLanguage: 'en',
    status: 'processing',
    createdAt: '2026-01-02T00:00:00.000Z',
    updatedAt: '2026-01-03T00:00:00.000Z',
    pipelineStage: 'translation',
    pipelineProgressPercent: 130,
  },
  {
    id: 'project-failed',
    name: 'Gamma launch',
    sourceLanguage: 'en',
    targetLanguage: 'ar',
    status: 'failed',
    createdAt: '2026-01-03T00:00:00.000Z',
    updatedAt: '2026-01-02T00:00:00.000Z',
    pipelineErrorMessage: 'Translation worker stopped.',
  },
];

function workspaceProps(overrides: Partial<React.ComponentProps<typeof WorkspaceHome>> = {}) {
  return {
    authContext: authContextFixture,
    projects,
    newProjectName: '',
    sourceLang: 'en',
    targetLang: 'es',
    languageOptions: languages,
    isCreatingProject: false,
    projectError: null,
    languageLoadError: null,
    onProjectNameChange: vi.fn(),
    onSourceLangChange: vi.fn(),
    onTargetLangChange: vi.fn(),
    onSwapLanguages: vi.fn(),
    onCreateProject: vi.fn((event: React.FormEvent) => event.preventDefault()),
    onSignOut: vi.fn(),
    onRename: vi.fn().mockResolvedValue(undefined),
    onArchive: vi.fn().mockResolvedValue(undefined),
    onDuplicate: vi.fn().mockResolvedValue(undefined),
    availableWorkspaces: [],
    onWorkspaceChange: vi.fn().mockResolvedValue(undefined),
    workspaceMembers: [],
    ...overrides,
  };
}

describe('PublicLanding', () => {
  it('exposes navigation, product content, and sign-in controls accessibly', () => {
    render(<PublicLanding signInSlot={<button>Sign in securely</button>} authError={null} />);

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Translate one video');
    expect(screen.getByRole('button', { name: 'Sign in securely' })).toBeInTheDocument();
    expect(screen.getByLabelText('GlobeSync editor preview')).toBeInTheDocument();
    expect(screen.getByText('Speaker-aware transcription')).toBeInTheDocument();
  });

  it('announces authentication errors', () => {
    render(
      <PublicLanding
        signInSlot={<button>Try sign in</button>}
        authError="Sign-in is temporarily unavailable."
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-in is temporarily unavailable.');
  });
});

describe('WorkspaceLoadingState', () => {
  it('identifies the signed-in workspace and permits sign out', async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();
    render(
      <WorkspaceLoadingState
        authContext={authContextFixture}
        onSignOut={onSignOut}
        title="Loading your workspace"
        description="Restoring projects."
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Preparing your projects');
    expect(screen.getByText('Editor')).toBeInTheDocument();
    expect(screen.getByText('Studio')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(onSignOut).toHaveBeenCalled();
  });

  it('shows session restoration before a user is known', () => {
    render(
      <WorkspaceLoadingState
        title="Opening GlobeSync"
        description="Restoring."
      />,
    );
    expect(screen.getByText('Restoring session state')).toBeInTheDocument();
  });
});

describe('WorkspaceHome', () => {
  it('renders project cards with status, progress, duration, and recovery links', () => {
    render(<WorkspaceHome {...workspaceProps()} />);

    expect(screen.getByRole('heading', { name: /Welcome, Editor/ })).toBeInTheDocument();
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Alpha launch' }))
      .toHaveAttribute('href', '/editor/project-complete');
    expect(screen.getByText('1:05')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Translation progress' }))
      .toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('Translation worker stopped.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review' }))
      .toHaveAttribute('href', '/editor/project-failed');
  });

  it('supports search, status filters, sorting, and reset', async () => {
    const user = userEvent.setup();
    render(<WorkspaceHome {...workspaceProps()} />);
    const main = screen.getByRole('main');

    await user.type(screen.getByRole('textbox', { name: 'Search projects by name' }), 'Gamma');
    expect(within(main).queryByRole('link', { name: 'Alpha launch' })).not.toBeInTheDocument();
    expect(within(main).getByRole('link', { name: 'Gamma launch' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Complete/ }));
    expect(screen.getByText('No projects match the current search and filters.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear search and filters' }));
    expect(within(main).getByRole('link', { name: 'Alpha launch' })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort projects' }), 'name');
    const cards = screen.getAllByRole('article');
    expect(within(cards[0]).getByText('Alpha launch')).toBeInTheDocument();
  });

  it('wires project creation and language controls', async () => {
    const user = userEvent.setup();
    const props = workspaceProps({ projects: [], newProjectName: 'New launch' });
    render(<WorkspaceHome {...props} />);

    await user.type(screen.getByRole('textbox', { name: 'Project name' }), '!');
    expect(props.onProjectNameChange).toHaveBeenCalled();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Source language' }), 'ar');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Target language' }), 'en');
    await user.click(screen.getByRole('button', { name: 'Swap source and target languages' }));
    await user.click(screen.getByRole('button', { name: 'Start Upload' }));

    expect(props.onSourceLangChange).toHaveBeenCalledWith('ar');
    expect(props.onTargetLangChange).toHaveBeenCalledWith('en');
    expect(props.onSwapLanguages).toHaveBeenCalled();
    expect(props.onCreateProject).toHaveBeenCalled();
  });

  it('disables project creation for blank names and displays workspace messages', () => {
    render(<WorkspaceHome {...workspaceProps({
      projects: [],
      newProjectName: '   ',
      projectError: 'Using a local recovery copy.',
      languageLoadError: 'Using default languages.',
      isCreatingProject: true,
    })} />);

    expect(screen.getByRole('button', { name: 'Creating...' })).toBeDisabled();
    expect(screen.getByText('Using a local recovery copy.').closest('[role="alert"]')).toBeInTheDocument();
    expect(screen.getByText('Using default languages.').closest('[role="status"]')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Uploads' })).toBeDisabled();
  });

  it('switches workspaces and shows membership context', async () => {
    const user = userEvent.setup();
    const secondWorkspace = {
      workspace: { ...authContextFixture.workspace, id: 'workspace-2', name: 'Agency' },
      membership: { ...authContextFixture.membership, workspace_id: 'workspace-2', role: 'editor' as const },
    };
    const props = workspaceProps({
      availableWorkspaces: [
        { workspace: authContextFixture.workspace, membership: authContextFixture.membership },
        secondWorkspace,
      ],
      workspaceMembers: [
        { user_id: 'user-1', display_name: 'Editor', email: 'editor@example.com', role: 'owner' },
        { user_id: 'user-2', display_name: 'Reviewer', email: 'reviewer@example.com', role: 'viewer' },
      ],
    });
    render(<WorkspaceHome {...props} />);

    const workspaceSelectors = screen.getAllByRole('combobox', { name: 'Switch workspace' });
    await user.selectOptions(workspaceSelectors[0], 'workspace-2');
    expect(props.onWorkspaceChange).toHaveBeenCalledWith('workspace-2');
    expect(screen.getByText('2 people with access to this workspace')).toBeInTheDocument();
  });

  it('executes rename, duplicate, and archive actions from accessible menus', async () => {
    const user = userEvent.setup();
    const props = workspaceProps({ projects: [projects[0]] });
    vi.spyOn(window, 'prompt').mockReturnValue('Renamed launch');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<WorkspaceHome {...props} />);

    const menuButton = screen.getByRole('button', { name: 'Project actions' });
    await user.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('menuitem', { name: 'Rename' }));
    expect(props.onRename).toHaveBeenCalledWith('project-complete', 'Renamed launch');

    await user.click(menuButton);
    await user.click(screen.getByRole('menuitem', { name: 'Duplicate' }));
    expect(props.onDuplicate).toHaveBeenCalledWith('project-complete');

    await user.click(menuButton);
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));
    expect(props.onArchive).toHaveBeenCalledWith('project-complete');
  });

  it('closes the project action menu on Escape', async () => {
    const user = userEvent.setup();
    render(<WorkspaceHome {...workspaceProps({ projects: [projects[0]] })} />);
    const menuButton = screen.getByRole('button', { name: 'Project actions' });

    await user.click(menuButton);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});
