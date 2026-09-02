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
    <div className="flex min-h-screen bg-slate-950 text-white">
      {/* Sidebar Layout */}
      <aside className="hidden w-[260px] shrink-0 flex-col border-r border-white/5 bg-slate-900/40 p-6 lg:flex">
        <div className="mb-10">
          <span className="text-xl font-bold tracking-tight text-white">Globe<span className="text-indigo-400">Sync</span></span>
        </div>
        
        <nav className="space-y-1.5">
          <Link href="#" className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            Home
          </Link>
          <Link href="#" className="flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Uploads
          </Link>
        </nav>

        {projects.length > 0 && (
          <div className="mt-10">
            <div className="mb-3 px-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Recents</div>
            <ul className="space-y-0.5">
              {projects.slice(0, 5).map((p) => (
                <li key={p.id}>
                  <Link href={`/editor/${p.id}`} className="block truncate rounded-lg px-2 py-2 text-sm text-slate-400 transition hover:bg-white/5 hover:text-slate-200">
                    {p.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-auto pt-6 border-t border-white/5">
          <div className="rounded-2xl p-2 text-sm">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-300 font-bold">
                {(authContext.user.display_name || authContext.user.email)[0].toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate font-medium text-white">{authContext.user.display_name || authContext.user.email}</p>
                <p className="truncate text-xs text-slate-400">{authContext.workspace.name}</p>
              </div>
            </div>
            <button
              onClick={onSignOut}
              className="w-full flex justify-center rounded-xl border border-white/10 px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 relative overflow-y-auto">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(99,102,241,0.15),_transparent_40%)] pointer-events-none" />
        
        <div className="relative mx-auto max-w-6xl p-6 lg:p-12">
          {/* Mobile Header (only visible on small screens) */}
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <span className="text-xl font-bold tracking-tight text-white">Globe<span className="text-indigo-400">Sync</span></span>
            <button onClick={onSignOut} className="text-sm text-slate-400">Sign out</button>
          </div>

          <header className="mb-12">
            <h1 className="text-4xl font-bold tracking-tight text-white">
              Welcome, <span className="text-indigo-100">{authContext.user.display_name?.split(' ')[0] || 'User'}</span>
            </h1>
          </header>

          {/* Onboarding Tracker or Project Creation */}
          {!hasProjects ? (
            <section className="mb-12">
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-lg font-semibold text-white">Finish your account setup</h2>
                <span className="rounded-full bg-indigo-500/20 px-2.5 py-0.5 text-xs font-bold text-indigo-300">0/4</span>
              </div>
              
              <div className="grid gap-4 sm:grid-cols-4">
                {/* Active Step */}
                <div className="rounded-2xl border border-indigo-500/50 bg-indigo-500/10 p-5 shadow-[0_0_20px_rgba(99,102,241,0.1)]">
                  <div className="flex items-center justify-between mb-3 text-xs font-semibold tracking-wider text-indigo-300">
                    <span className="h-4 w-4 rounded-full border-2 border-indigo-400" />
                    STEP 1
                  </div>
                  <h3 className="font-semibold text-white mb-2">Create a project</h3>
                  <p className="text-xs text-slate-300 mb-4">Start your first translation run by uploading a video.</p>
                  
                  {languageLoadError ? <div className="mb-3"><StatusBanner tone="info" message={languageLoadError} /></div> : null}
                  {projectError ? <div className="mb-3"><StatusBanner tone="warning" message={projectError} /></div> : null}

                  <form onSubmit={onCreateProject} className="space-y-3">
                    <input
                      type="text"
                      placeholder="Project name"
                      className="w-full rounded-xl border border-white/20 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-indigo-400"
                      value={newProjectName}
                      onChange={(e) => onProjectNameChange(e.target.value)}
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        className="w-full rounded-xl border border-white/20 bg-slate-950 px-2 py-2 text-xs text-slate-300 outline-none transition focus:border-indigo-400"
                        value={sourceLang}
                        onChange={(e) => onSourceLangChange(e.target.value)}
                      >
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                      <select
                        className="w-full rounded-xl border border-white/20 bg-slate-950 px-2 py-2 text-xs text-slate-300 outline-none transition focus:border-indigo-400"
                        value={targetLang}
                        onChange={(e) => onTargetLangChange(e.target.value)}
                      >
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={isCreatingProject || !newProjectName.trim()}
                      className="w-full rounded-xl bg-white px-3 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-200 disabled:opacity-50"
                    >
                      {isCreatingProject ? 'Creating...' : 'Start Upload'}
                    </button>
                  </form>
                </div>
                
                {/* Inactive Steps */}
                {['Transcribe & Translate', 'Review & Edit', 'Generate Dub'].map((step, i) => (
                  <div key={step} className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 opacity-60 grayscale">
                    <div className="flex items-center justify-between mb-3 text-xs font-semibold tracking-wider text-slate-500">
                      <span className="h-4 w-4 rounded-full border-2 border-slate-700" />
                      STEP {i + 2}
                    </div>
                    <h3 className="font-semibold text-slate-300 mb-2">{step}</h3>
                    <p className="text-xs text-slate-500">Unlocks after step {i + 1}</p>
                  </div>
                ))}
              </div>
            </section>
          ) : (
             <section className="mb-12 rounded-2xl border border-white/5 bg-white/5 p-6 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Create a new project</h2>
                    <p className="text-sm text-slate-400">Start another translation workflow</p>
                  </div>
                </div>
                <form onSubmit={onCreateProject} className="grid gap-4 sm:grid-cols-[1fr_auto_auto_auto] items-end">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Project name</label>
                      <input type="text" placeholder="e.g. Product Launch Hindi Dub" className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-400" value={newProjectName} onChange={(e) => onProjectNameChange(e.target.value)} />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Source</label>
                      <select className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-2.5 text-sm text-slate-300 outline-none focus:border-indigo-400" value={sourceLang} onChange={(e) => onSourceLangChange(e.target.value)}>
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Target</label>
                      <select className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-2.5 text-sm text-slate-300 outline-none focus:border-indigo-400" value={targetLang} onChange={(e) => onTargetLangChange(e.target.value)}>
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <button type="submit" disabled={isCreatingProject || !newProjectName.trim()} className="rounded-xl bg-indigo-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50">
                      {isCreatingProject ? 'Creating...' : '+ New Project'}
                    </button>
                </form>
             </section>
          )}

          {hasProjects && (
            <section>
              <div className="mb-6 flex items-center justify-between">
                <h2 className="text-xl font-semibold text-white">All Projects</h2>
                <div className="flex gap-2">
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M10 6.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0ZM9.5 10.207l3.146 3.147a.5.5 0 0 0 .708-.708L10.207 9.5A4.5 4.5 0 1 0 9.5 10.207Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"/></svg>
                    <input type="text" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-48 rounded-full border border-white/10 bg-slate-900/60 py-1.5 pl-8 pr-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-indigo-400" />
                  </div>
                  <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="rounded-full border border-white/10 bg-slate-900/60 px-3 py-1.5 text-sm text-slate-300 outline-none focus:border-indigo-400">
                    <option value="updatedAt">Last updated</option>
                    <option value="createdAt">Date created</option>
                    <option value="name">Name</option>
                  </select>
                </div>
              </div>

              {visibleProjects.length === 0 ? (
                <div className="py-12 text-center text-sm text-slate-500">No projects match your search.</div>
              ) : (
                <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                  {visibleProjects.map((project) => (
                    <article key={project.id} className="group relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/60 transition hover:border-white/20 hover:bg-slate-800/80">
                      {/* HeyGen style Thumbnail Area */}
                      <div className="relative aspect-video w-full bg-slate-950/80">
                        {/* Mock Image / Placeholder */}
                        <div className="absolute inset-0 flex items-center justify-center text-slate-700">
                          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                        </div>
                        
                        {/* Play button overlay on hover */}
                        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition group-hover:opacity-100">
                           <Link href={`/editor/${project.id}`} className="flex h-12 w-12 items-center justify-center rounded-full bg-white/20 text-white backdrop-blur-md transition hover:bg-white hover:text-slate-900">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4l15 8-15 8z"/></svg>
                           </Link>
                        </div>

                        {/* Top Right Actions */}
                        <div className="absolute right-2 top-2 z-10 flex gap-1">
                           <div className="rounded-full bg-black/60 p-1 text-white backdrop-blur-md">
                              <ProjectActionsMenu projectId={project.id} projectName={project.name} />
                           </div>
                        </div>

                        {/* Bottom Left Badges */}
                        <div className="absolute bottom-2 left-2 flex gap-2">
                           <span className="flex items-center gap-1.5 rounded-lg bg-black/70 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-md">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/></svg>
                              Translation
                           </span>
                           <span className={`rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-wider backdrop-blur-md ${getProjectStatusClasses(project.status)}`}>
                             {formatProjectStatus(project.status)}
                           </span>
                        </div>
                        
                        {/* Bottom Right Duration Badge */}
                        <div className="absolute bottom-2 right-2 flex gap-2">
                           <span className="flex items-center gap-1 rounded-lg bg-black/70 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-md">
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                              1m 30s
                           </span>
                        </div>
                      </div>

                      {/* Card Content */}
                      <div className="p-4">
                        <Link href={`/editor/${project.id}`} className="block">
                          <h3 className="truncate text-base font-semibold text-white group-hover:text-indigo-300 transition">{project.name}</h3>
                        </Link>
                        <p className="mt-1 text-xs text-slate-400">
                          {formatProjectDate(project.createdAt)} • {project.sourceLanguage.toUpperCase()} → {project.targetLanguage.toUpperCase()}
                        </p>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
