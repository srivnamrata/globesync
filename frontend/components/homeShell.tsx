import Link from 'next/link';
import React, { useState, useRef, useEffect } from 'react';
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
  authContext?: AuthBootstrapResponse | null;
  onSignOut?: () => void;
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
  { icon: '🌍', heading: 'Reach 20+ languages', body: 'Translate and dub your videos into over 20 languages — without hiring studios or managing multiple vendors.' },
  { icon: '✂️', heading: 'Edit every word', body: 'Review and fix each transcript line and translation before it goes to voice. Full control, no black boxes.' },
  { icon: '🚀', heading: 'Upload, translate, export', body: 'From raw video to dubbed output in a few clicks. Track every stage and download when it\'s ready.' },
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

const languagePillRow = ['Hindi', 'Spanish', 'French', 'Arabic', 'Japanese', 'Portuguese', 'German', 'Korean', 'Italian', 'Turkish', 'Dutch', 'Russian'];

export function PublicLanding({ signInSlot, authError }: PublicLandingProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Background glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_40%_at_50%_-10%,rgba(99,102,241,0.25),transparent),radial-gradient(ellipse_60%_40%_at_80%_100%,rgba(14,165,233,0.12),transparent)]" />

      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-6 lg:px-10">

        {/* Nav — wordmark only; sign-in lives in the hero CTA so the Google SDK mounts once */}
        <nav className="flex items-center justify-between py-6">
          <span className="text-lg font-bold tracking-tight text-white">Globe<span className="text-indigo-400">Sync</span></span>
          <span className="hidden text-sm text-slate-500 lg:inline">Translate · Dub · Export</span>
        </nav>

        {/* Hero */}
        <main className="flex flex-1 flex-col items-center justify-center pb-16 pt-12 text-center">

          {/* Eyebrow */}
          <span className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-400/30 bg-indigo-400/10 px-4 py-1.5 text-sm font-medium text-indigo-200">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            20+ languages · AI dubbing · Segment-level review
          </span>

          {/* Headline */}
          <h1 className="mx-auto max-w-4xl text-5xl font-bold leading-tight tracking-tight text-white sm:text-6xl lg:text-7xl">
            If language is the barrier,<br />
            <span className="text-indigo-400">GlobeSync</span> breaks it.
          </h1>

          {/* Sub-headline */}
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            Translate your videos into 20+ languages in a few clicks — with AI dubbing, editable transcripts, and full control at every step. No studios. No back-and-forth. Just reach.
          </p>

          {/* Primary CTA — single mount point for the Google SDK button */}
          <div className="mt-10 flex flex-col items-center gap-3">
            <div className="flex min-h-[52px] items-center">{signInSlot}</div>
            {authError ? (
              <p className="max-w-sm rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">{authError}</p>
            ) : (
              <p className="text-xs text-slate-500">Free to start · No credit card required · Your workspace is ready in seconds</p>
            )}
          </div>

          {/* Language pills */}
          <div className="mt-12 flex flex-wrap justify-center gap-2">
            {languagePillRow.map((lang) => (
              <span key={lang} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                {lang}
              </span>
            ))}
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-400">+ more</span>
          </div>

          {/* Feature cards */}
          <div className="mt-16 grid w-full gap-4 sm:grid-cols-3">
            {productHighlights.map((item) => (
              <div key={item.heading} className="rounded-3xl border border-white/10 bg-slate-900/70 p-6 text-left backdrop-blur">
                <div className="mb-3 text-2xl">{item.icon}</div>
                <h3 className="text-base font-semibold text-white">{item.heading}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-400">{item.body}</p>
              </div>
            ))}
          </div>

          {/* Social proof strip */}
          <p className="mt-16 text-xs uppercase tracking-[0.2em] text-slate-600">
            Built for creators, educators, and global teams who need real control — not a black box
          </p>

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
          {authContext ? (
            <div className="text-right">
              <p className="text-sm font-semibold text-white">{authContext.user.display_name || authContext.user.email}</p>
              <p className="mt-1 text-xs text-slate-400">{authContext.workspace.name}</p>
              {onSignOut ? (
                <button
                  type="button"
                  onClick={onSignOut}
                  className="mt-3 rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:text-white"
                >
                  Sign out
                </button>
              ) : null}
            </div>
          ) : (
            <div className="text-right text-sm text-slate-400">
              Restoring session state
            </div>
          )}
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

type SortKey = 'updatedAt' | 'createdAt' | 'name';

function ProjectActionsMenu({ projectId, projectName }: { projectId: string; projectName: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-white/10 hover:text-slate-300"
        aria-label="Project actions"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 min-w-[160px] rounded-2xl border border-white/10 bg-slate-900 py-1 shadow-2xl shadow-black/40">
          <button
            type="button"
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
            onClick={() => { setOpen(false); alert(`Rename "${projectName}" — wire to rename handler`); }}
          >
            Rename
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
            onClick={() => { setOpen(false); alert(`Duplicate "${projectName}" — wire to duplicate handler`); }}
          >
            Duplicate
          </button>
          <div className="my-1 border-t border-white/10" />
          <button
            type="button"
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-rose-400 transition hover:bg-rose-500/10 hover:text-rose-300"
            onClick={() => { setOpen(false); alert(`Archive "${projectName}" — wire to archive handler`); }}
          >
            Archive
          </button>
        </div>
      )}
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
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('updatedAt');

  const visibleProjects = projects
    .filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      return new Date(b[sortKey]).getTime() - new Date(a[sortKey]).getTime();
    });

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
            {/* Section header */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">Your workspace</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white">Projects ready for review</h2>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                {projects.length} {projects.length === 1 ? 'project' : 'projects'}
              </div>
            </div>

            {/* Search + sort toolbar */}
            {hasProjects && (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="relative flex-1">
                  <svg className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" width="15" height="15" viewBox="0 0 15 15" fill="none">
                    <path d="M10 6.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0ZM9.5 10.207l3.146 3.147a.5.5 0 0 0 .708-.708L10.207 9.5A4.5 4.5 0 1 0 9.5 10.207Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"/>
                  </svg>
                  <input
                    type="text"
                    placeholder="Search projects…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full rounded-2xl border border-white/10 bg-slate-900/80 py-2.5 pl-9 pr-4 text-sm text-white outline-none placeholder:text-slate-500 transition focus:border-indigo-400"
                  />
                </div>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  className="rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-2.5 text-sm text-slate-300 outline-none transition focus:border-indigo-400"
                >
                  <option value="updatedAt">Sort: Last updated</option>
                  <option value="createdAt">Sort: Date created</option>
                  <option value="name">Sort: Name A–Z</option>
                </select>
              </div>
            )}

            {projectError ? <StatusBanner tone="warning" message={projectError} /> : null}

            {!hasProjects ? (
              <div className="rounded-3xl border border-dashed border-white/15 bg-slate-900/60 p-12 text-center">
                <h3 className="text-2xl font-semibold text-white">Create your first project</h3>
                <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">
                  GlobeSync is ready for a new upload-to-export workflow. Start by naming the project and choosing the source and target languages.
                </p>
              </div>
            ) : visibleProjects.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-white/15 bg-slate-900/60 p-10 text-center">
                <p className="text-sm text-slate-400">No projects match <span className="text-white">"{search}"</span>.</p>
              </div>
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {visibleProjects.map((project) => (
                  <article key={project.id} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-xl shadow-slate-950/25 transition hover:border-white/20">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h3 className="truncate text-xl font-semibold text-white">{project.name}</h3>
                        <p className="mt-1.5 text-sm text-slate-400">
                          <span className="font-mono text-slate-300">{project.sourceLanguage.toUpperCase()}</span>
                          <span className="mx-1.5 text-slate-600">→</span>
                          <span className="font-mono text-slate-300">{project.targetLanguage.toUpperCase()}</span>
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${getProjectStatusClasses(project.status)}`}>
                          {formatProjectStatus(project.status)}
                        </span>
                        <ProjectActionsMenu projectId={project.id} projectName={project.name} />
                      </div>
                    </div>

                    <div className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                      <div className="rounded-2xl bg-white/5 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Updated</p>
                        <p className="mt-1.5 text-white">{formatProjectDate(project.updatedAt)}</p>
                      </div>
                      <div className="rounded-2xl bg-white/5 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Created</p>
                        <p className="mt-1.5 text-white">{formatProjectDate(project.createdAt)}</p>
                      </div>
                    </div>

                    <div className="mt-5 flex items-center justify-end">
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
