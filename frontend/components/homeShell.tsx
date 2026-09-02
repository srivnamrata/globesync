import Link from 'next/link';
import React from 'react';
import type { AuthBootstrapResponse } from '../services/authService';
import type { Project } from '../store/projectStore';

export type HomeShellLanguageOption = {
  value: string;
  label: string;
};

type PublicLandingProps = {
  signInSlot: React.ReactNode;
  authError: string | null;
};

type WorkspaceLoadingStateProps = {
  authContext: AuthBootstrapResponse;
  onSignOut: () => void;
  title: string;
  description: string;
};

type WorkspaceHomeProps = {
  authContext: AuthBootstrapResponse;
  projects: Project[];
  newProjectName: string;
  sourceLang: string;
  targetLang: string;
  languageOptions: HomeShellLanguageOption[];
  isCreatingProject: boolean;
  projectError: string | null;
  languageLoadError: string | null;
  onProjectNameChange: (value: string) => void;
  onSourceLangChange: (value: string) => void;
  onTargetLangChange: (value: string) => void;
  onCreateProject: (event: React.FormEvent<HTMLFormElement>) => void;
  onSignOut: () => void;
};

const productHighlights = [
  'Translate and dub multilingual video projects with a clear stage-by-stage workflow.',
  'Review transcript, translation, and generated outputs with segment-level control.',
  'Resume work confidently with visible project status, recovery cues, and export readiness.',
];

function formatProjectStatus(status: Project['status']): string {
  switch (status) {
    case 'processing':
      return 'Processing';
    case 'completed':
      return 'Complete';
    case 'failed':
      return 'Needs attention';
    case 'archived':
      return 'Archived';
    case 'draft':
    default:
      return 'Draft';
  }
}

function getProjectStatusClasses(status: Project['status']): string {
  switch (status) {
    case 'completed':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
    case 'failed':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
    case 'processing':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
    case 'archived':
      return 'border-slate-600/60 bg-slate-800/80 text-slate-300';
    case 'draft':
    default:
      return 'border-indigo-500/30 bg-indigo-500/10 text-indigo-200';
  }
}

function formatProjectDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function StatusBanner({ tone, message }: { tone: 'warning' | 'info'; message: string }) {
  const toneClasses = tone === 'warning'
    ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
    : 'border-sky-500/30 bg-sky-500/10 text-sky-100';

  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${toneClasses}`}>
      {message}
    </div>
  );
}

export function PublicLanding({ signInSlot, authError }: PublicLandingProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(99,102,241,0.2),_transparent_38%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.16),_transparent_30%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 lg:px-10">
        <header className="flex items-center justify-between gap-6 border-b border-white/10 pb-6">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-indigo-300">GlobeSync</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Video translation workflows built for operational clarity.</h1>
          </div>
          <div className="hidden text-right text-sm text-slate-300 lg:block">
            <p>Global dubbing, transcript review, and export delivery.</p>
            <p className="mt-1 text-slate-400">Sign in to open your workspace.</p>
          </div>
        </header>

        <main className="grid flex-1 gap-12 py-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <section className="space-y-8">
            <div className="space-y-5">
              <span className="inline-flex rounded-full border border-indigo-400/30 bg-indigo-400/10 px-4 py-1 text-sm font-medium text-indigo-100">
                Production-ready multilingual video localization
              </span>
              <div className="space-y-4">
                <h2 className="max-w-3xl text-5xl font-semibold tracking-tight text-white sm:text-6xl">
                  Launch, review, and ship translated video projects without losing control.
                </h2>
                <p className="max-w-2xl text-lg leading-8 text-slate-300">
                  GlobeSync gives teams a clear path from upload to export with segment-level review, reliable recovery states, and workspace-aware project management.
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {productHighlights.map((highlight) => (
                <div key={highlight} className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm leading-6 text-slate-200 backdrop-blur">
                  {highlight}
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl shadow-indigo-950/30 backdrop-blur">
            <div className="space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">Open your workspace</p>
              <h3 className="text-2xl font-semibold text-white">Start with Google sign-in</h3>
              <p className="text-sm leading-6 text-slate-300">
                New users are provisioned automatically, and returning users restore their workspace session on reload.
              </p>
            </div>

            <div className="mt-8 space-y-4">
              <div className="flex min-h-[44px] items-center">{signInSlot}</div>
              {authError ? <StatusBanner tone="warning" message={authError} /> : null}
            </div>

            <dl className="mt-8 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <dt className="text-slate-400">Workspace separation</dt>
                <dd className="mt-2 text-white">Signed-out visitors see a product landing page, while signed-in users enter a dedicated workspace home.</dd>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <dt className="text-slate-400">Segment-level control</dt>
                <dd className="mt-2 text-white">Review transcript, translation, dubbing, and export state without relying on opaque generation flows.</dd>
              </div>
            </dl>
          </section>
        </main>
      </div>
    </div>
  );
}

export function WorkspaceLoadingState({ authContext, onSignOut, title, description }: WorkspaceLoadingStateProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8 lg:px-10">
        <header className="flex items-center justify-between gap-6 border-b border-white/10 pb-6">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-indigo-300">GlobeSync Workspace</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
            <p className="mt-2 text-sm text-slate-400">{description}</p>
          </div>
          <div className="text-right">
            <p className="text-sm font-semibold text-white">{authContext.user.display_name || authContext.user.email}</p>
            <p className="mt-1 text-xs text-slate-400">{authContext.workspace.name}</p>
            <button
              type="button"
              onClick={onSignOut}
              className="mt-3 rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:text-white"
            >
              Sign out
            </button>
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xl rounded-3xl border border-white/10 bg-slate-900/80 p-10 text-center shadow-2xl shadow-slate-950/40">
            <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-slate-700 border-t-indigo-400" />
            <h2 className="mt-6 text-2xl font-semibold text-white">Preparing your projects</h2>
            <p className="mt-3 text-sm leading-6 text-slate-300">GlobeSync is restoring your session, loading project state, and preparing the next action.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function WorkspaceHome({
  authContext,
  projects,
  newProjectName,
  sourceLang,
  targetLang,
  languageOptions,
  isCreatingProject,
  projectError,
  languageLoadError,
  onProjectNameChange,
  onSourceLangChange,
  onTargetLangChange,
  onCreateProject,
  onSignOut,
}: WorkspaceHomeProps) {
  const hasProjects = projects.length > 0;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.12),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.1),_transparent_28%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 lg:px-10">
        <header className="flex flex-col gap-6 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-indigo-300">GlobeSync Workspace</p>
            <div>
              <h1 className="text-4xl font-semibold tracking-tight text-white">Welcome back{authContext.user.display_name ? `, ${authContext.user.display_name}` : ''}.</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
                Manage multilingual video projects, monitor progress, and jump back into review without losing your place.
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 px-5 py-4 text-sm text-slate-200 backdrop-blur">
            <p className="font-semibold text-white">{authContext.user.display_name || authContext.user.email}</p>
            <p className="mt-1 text-slate-400">{authContext.workspace.name}</p>
            <button
              type="button"
              onClick={onSignOut}
              className="mt-4 rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:text-white"
            >
              Sign out
            </button>
          </div>
        </header>

        <main className="grid flex-1 gap-8 py-10 lg:grid-cols-[360px_minmax(0,1fr)]">
          <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-2xl shadow-slate-950/30 backdrop-blur">
            <div className="space-y-3">
              <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">Create a project</p>
              <h2 className="text-2xl font-semibold text-white">Start a new localization run</h2>
              <p className="text-sm leading-6 text-slate-300">
                Create a project shell first, then move into transcript, translation, dubbing, and export review.
              </p>
            </div>

            {languageLoadError ? <div className="mt-6"><StatusBanner tone="info" message={languageLoadError} /></div> : null}

            <form onSubmit={onCreateProject} className="mt-6 space-y-5">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Project name</label>
                <input
                  type="text"
                  placeholder="e.g. Product Launch Hindi Dub"
                  className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none transition focus:border-indigo-400"
                  value={newProjectName}
                  onChange={(event) => onProjectNameChange(event.target.value)}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Source language</label>
                  <select
                    className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none transition focus:border-indigo-400"
                    value={sourceLang}
                    onChange={(event) => onSourceLangChange(event.target.value)}
                  >
                    {languageOptions.map((language) => (
                      <option key={language.value} value={language.value}>
                        {language.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Target language</label>
                  <select
                    className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none transition focus:border-indigo-400"
                    value={targetLang}
                    onChange={(event) => onTargetLangChange(event.target.value)}
                  >
                    {languageOptions.map((language) => (
                      <option key={language.value} value={language.value}>
                        {language.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <button
                type="submit"
                disabled={isCreatingProject || newProjectName.trim().length === 0}
                className="w-full rounded-2xl bg-indigo-500 px-4 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-300"
              >
                {isCreatingProject ? 'Creating project…' : 'Create project'}
              </button>
            </form>
          </section>

          <section className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">Your workspace</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white">Projects ready for review</h2>
                <p className="mt-2 text-sm text-slate-300">
                  Reopen active work, track its current status, and move straight into the editor.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                {projects.length} {projects.length === 1 ? 'project' : 'projects'}
              </div>
            </div>

            {projectError ? <StatusBanner tone="warning" message={projectError} /> : null}

            {!hasProjects ? (
              <div className="rounded-3xl border border-dashed border-white/15 bg-slate-900/60 p-12 text-center">
                <h3 className="text-2xl font-semibold text-white">Create your first project</h3>
                <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">
                  GlobeSync is ready for a new upload-to-export workflow. Start by naming the project and choosing the source and target languages.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {projects.map((project) => (
                  <article key={project.id} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-xl shadow-slate-950/25 transition hover:border-white/20">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-xl font-semibold text-white">{project.name}</h3>
                        <p className="mt-2 text-sm text-slate-400">{project.sourceLanguage} to {project.targetLanguage}</p>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${getProjectStatusClasses(project.status)}`}>
                        {formatProjectStatus(project.status)}
                      </span>
                    </div>

                    <div className="mt-6 grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
                      <div className="rounded-2xl bg-white/5 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Updated</p>
                        <p className="mt-2 text-white">{formatProjectDate(project.updatedAt)}</p>
                      </div>
                      <div className="rounded-2xl bg-white/5 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Created</p>
                        <p className="mt-2 text-white">{formatProjectDate(project.createdAt)}</p>
                      </div>
                    </div>

                    <div className="mt-6 flex items-center justify-between gap-4">
                      <p className="text-sm text-slate-400">Open the editor to continue transcript, translation, dubbing, and export review.</p>
                      <Link
                        href={`/editor/${project.id}`}
                        className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-slate-200"
                      >
                        Open editor
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
