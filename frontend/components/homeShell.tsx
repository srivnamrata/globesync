import Link from 'next/link';
import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { AuthBootstrapResponse, WorkspaceContext, WorkspaceMember } from '../services/authService';
import type { Project } from '../store/projectStore';
import { Button, StatePanel, StatusBadge } from './ui';
import { formatDate } from '../utils/formatDateTime';
import { getTextDirection } from '../utils/textDirection';

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
  onSwapLanguages: () => void;
  onCreateProject: (event: React.FormEvent<HTMLFormElement>) => void;
  onSignOut: () => void;
  onRename: (projectId: string, name: string) => Promise<void>;
  onArchive: (projectId: string) => Promise<void>;
  onDuplicate: (projectId: string) => Promise<void>;
  availableWorkspaces: WorkspaceContext[];
  onWorkspaceChange: (workspaceId: string) => Promise<void>;
  workspaceMembers: WorkspaceMember[];
};

const productHighlights = [
  { icon: 'languages', heading: 'Speaker-aware transcription', body: 'Turn speech into timestamped, speaker-separated segments that stay connected to the source video.' },
  { icon: 'edit', heading: 'Review before you render', body: 'Edit every transcript and translation segment before generating the localized voice track.' },
  { icon: 'export', heading: 'One controlled workflow', body: 'Track transcription, translation, dubbing, synchronization, lip-sync, and export in one project.' },
] as const;

const workflowSteps = [
  { number: '01', heading: 'Upload', body: 'Add your source video and choose the language you want to reach.' },
  { number: '02', heading: 'Review', body: 'Check speaker labels, transcript timing, and segment-level translations.' },
  { number: '03', heading: 'Generate', body: 'Create localized speech and synchronize it to the original timeline.' },
  { number: '04', heading: 'Export', body: 'Download the finished video and timestamped subtitle files.' },
] as const;

function FeatureIcon({ name }: { name: (typeof productHighlights)[number]['icon'] }) {
  const shared = {
    width: 24,
    height: 24,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };

  if (name === 'languages') {
    return <svg {...shared}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z" /></svg>;
  }

  if (name === 'edit') {
    return <svg {...shared}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></svg>;
  }

  return <svg {...shared}><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></svg>;
}

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
      return 'Planning';
  }
}

type StatusTone = 'neutral' | 'processing' | 'success' | 'error';

function getProjectStatusTone(status: Project['status']): StatusTone {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'processing':
      return 'processing';
    case 'archived':
      return 'neutral';
    case 'draft':
    default:
      return 'neutral';
  }
}

function formatProjectDate(value: string): string {
  return formatDate(value);
}

function StatusBanner({ tone, message }: { tone: 'warning' | 'info'; message: string }) {
  return (
    <StatePanel tone={tone} title={tone === 'warning' ? 'Action needed' : 'Workspace update'}>
      {message}
    </StatePanel>
  );
}

function formatDuration(seconds?: number): string | null {
  if (!seconds || seconds <= 0) {
    return null;
  }

  const wholeSeconds = Math.round(seconds);
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const remainingSeconds = wholeSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  }

  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

function formatPipelineStage(stage?: string): string {
  if (!stage) {
    return 'Preparing project';
  }

  return stage.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const languagePillRow = ['Hindi', 'Spanish', 'French', 'Arabic', 'Japanese', 'Portuguese', 'German', 'Korean', 'Italian', 'Turkish', 'Dutch', 'Russian'];

export function PublicLanding({ signInSlot, authError }: PublicLandingProps) {
  return (
    <div className="min-h-screen overflow-hidden bg-[#f8f9ff] text-slate-950">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[760px] bg-[radial-gradient(circle_at_12%_18%,rgba(99,102,241,0.13),transparent_32%),radial-gradient(circle_at_88%_10%,rgba(14,165,233,0.1),transparent_30%)]" />

      <div className="relative mx-auto max-w-7xl px-5 sm:px-8 lg:px-10">
        <nav aria-label="Main navigation" className="flex h-20 items-center justify-between">
          <a href="#" aria-label="GlobeSync home" className="text-xl font-extrabold tracking-tight text-slate-950">
            Globe<span className="text-indigo-600">Sync</span>
          </a>
          <div className="hidden items-center gap-8 text-sm font-semibold text-slate-600 md:flex">
            <a href="#how-it-works" className="transition hover:text-indigo-600">How it works</a>
            <a href="#features" className="transition hover:text-indigo-600">Features</a>
            <a href="#security" className="transition hover:text-indigo-600">Security</a>
          </div>
          <a href="#get-started" className="rounded-full bg-slate-950 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600">
            Start free
          </a>
        </nav>

        <main>
          <section className="grid min-h-[680px] items-center gap-14 py-16 lg:grid-cols-[0.86fr_1.14fr] lg:py-20">
            <div className="text-center lg:text-left">
              <span className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-white/80 px-4 py-2 text-xs font-bold uppercase tracking-[0.12em] text-indigo-700 shadow-sm backdrop-blur">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Video localization with human control
              </span>
              <h1 className="mt-7 text-4xl font-extrabold leading-[1.04] tracking-[-0.04em] text-slate-950 sm:text-6xl lg:text-7xl">
                Translate one video.
                <span className="mt-2 block bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-transparent">
                  Reach every audience.
                </span>
              </h1>
              <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-slate-600 lg:mx-0">
                Transcribe, translate, review, dub, synchronize, and export multilingual video from one controlled workspace.
              </p>

              <div id="get-started" className="mt-9 flex flex-col items-center gap-4 lg:items-start">
                <div className="flex min-h-[56px] items-center rounded-2xl bg-white p-2 shadow-xl shadow-indigo-500/10 ring-1 ring-slate-900/10">
                  {signInSlot}
                </div>
                {authError ? (
                  <p role="alert" className="max-w-md rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700">{authError}</p>
                ) : (
                  <p className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                    <span aria-hidden="true" className="text-emerald-600">✓</span>
                    Free to start
                    <span aria-hidden="true">·</span>
                    No credit card required
                  </p>
                )}
              </div>

              <div className="mt-10 flex flex-wrap justify-center gap-x-6 gap-y-3 text-sm font-semibold text-slate-600 lg:justify-start">
                <span className="flex items-center gap-2"><span className="text-indigo-600">✓</span> 30+ languages</span>
                <span className="flex items-center gap-2"><span className="text-indigo-600">✓</span> Editable transcripts</span>
                <span className="flex items-center gap-2"><span className="text-indigo-600">✓</span> Export-ready video</span>
              </div>
            </div>

            <div aria-label="GlobeSync editor preview" className="relative mx-auto w-full max-w-3xl">
              <div className="absolute -inset-6 rounded-[2.5rem] bg-gradient-to-br from-indigo-300/35 via-violet-200/20 to-sky-200/30 blur-2xl" />
              <div className="relative overflow-hidden rounded-[1.75rem] border border-white/80 bg-slate-950 p-2 shadow-[0_32px_80px_-28px_rgba(30,41,59,0.48)]">
                <div className="overflow-hidden rounded-[1.35rem] bg-slate-900">
                  <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
                      <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
                      <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                    </div>
                    <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400">
                      Product launch · English to Spanish
                      <span className="rounded-full bg-emerald-400/10 px-2 py-1 text-emerald-300">Saved</span>
                    </div>
                  </div>

                  <div className="grid min-h-[430px] lg:grid-cols-[0.88fr_1.12fr]">
                    <div className="border-b border-white/10 bg-slate-950/70 p-4 lg:border-b-0 lg:border-r">
                      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-[radial-gradient(circle_at_50%_30%,#334155,#0f172a_62%)]">
                        <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-slate-950 to-transparent" />
                        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white shadow-xl backdrop-blur">
                          <svg aria-hidden="true" viewBox="0 0 24 24" className="ml-1 h-7 w-7 fill-current"><path d="M8 5v14l11-7z" /></svg>
                        </div>
                        <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-slate-950/75 px-3 py-2 text-center text-[11px] font-medium text-white backdrop-blur">
                          Build products that speak to everyone.
                        </div>
                      </div>

                      <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="flex items-center justify-between text-[11px] font-semibold">
                          <span className="text-white">Localization progress</span>
                          <span className="text-indigo-300">68%</span>
                        </div>
                        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                          <div className="h-full w-[68%] rounded-full bg-gradient-to-r from-indigo-500 to-violet-400" />
                        </div>
                        <div className="mt-3 grid grid-cols-4 gap-1 text-center text-[9px] text-slate-500">
                          <span className="text-emerald-300">Upload</span>
                          <span className="text-emerald-300">Transcript</span>
                          <span className="text-indigo-300">Translation</span>
                          <span>Export</span>
                        </div>
                      </div>
                    </div>

                    <div className="p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-300">Segment review</p>
                          <h2 className="mt-1 text-sm font-bold text-white">Transcript and translation</h2>
                        </div>
                        <span className="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-slate-400">3 speakers</span>
                      </div>

                      <div className="mt-4 space-y-3">
                        {[
                          { speaker: 'Speaker 1', time: '00:04.2', source: 'Welcome to our product launch.', translated: 'Bienvenidos al lanzamiento de nuestro producto.', active: false },
                          { speaker: 'Speaker 2', time: '00:08.7', source: 'Today, we are sharing a simpler way to work.', translated: 'Hoy compartimos una forma más sencilla de trabajar.', active: true },
                          { speaker: 'Speaker 1', time: '00:14.1', source: 'Built for teams around the world.', translated: 'Creado para equipos de todo el mundo.', active: false },
                        ].map((segment) => (
                          <div key={segment.time} className={`rounded-xl border p-3 ${segment.active ? 'border-indigo-400/50 bg-indigo-500/10' : 'border-white/10 bg-white/[0.025]'}`}>
                            <div className="flex items-center justify-between text-[10px]">
                              <span className="font-bold text-indigo-300">{segment.speaker}</span>
                              <span className="font-mono text-slate-500">{segment.time}</span>
                            </div>
                            <p className="mt-2 text-[11px] leading-5 text-slate-400">{segment.source}</p>
                            <p className="mt-1 text-[11px] font-medium leading-5 text-white">{segment.translated}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 border-t border-white/10 px-4 py-3">
                    <div className="h-8 w-8 rounded-lg bg-indigo-500/15 p-2 text-indigo-300">
                      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h3l3-9 4 18 3-9h5" /></svg>
                    </div>
                    <div className="flex h-8 flex-1 items-center gap-1 overflow-hidden">
                      {[40, 65, 35, 78, 52, 85, 45, 70, 34, 62, 82, 48, 72, 38, 58, 76, 46, 68, 32, 55, 80, 44, 66, 36, 60].map((height, index) => (
                        <span key={index} className="w-1 flex-none rounded-full bg-indigo-400/70" style={{ height: `${height}%` }} />
                      ))}
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">00:18 / 01:42</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section aria-label="Supported languages" className="border-y border-slate-200/80 py-7">
            <div className="flex flex-col items-center gap-4 lg:flex-row lg:justify-between">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">Localize for audiences worldwide</p>
              <div className="flex flex-wrap justify-center gap-2 lg:justify-end">
                {languagePillRow.slice(0, 8).map((lang) => (
                  <span key={lang} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm">{lang}</span>
                ))}
                <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">+ 22 more</span>
              </div>
            </div>
          </section>

          <section id="how-it-works" className="py-24">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-600">How it works</p>
              <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-slate-950 sm:text-4xl">From source video to global-ready media</h2>
              <p className="mt-4 text-base leading-7 text-slate-600">Automation handles the repetitive work. You keep control of every word and every output.</p>
            </div>
            <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {workflowSteps.map((step) => (
                <article key={step.number} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                  <span className="font-mono text-xs font-bold text-indigo-600">{step.number}</span>
                  <h3 className="mt-5 text-lg font-bold text-slate-950">{step.heading}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{step.body}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="features" className="grid gap-4 pb-24 sm:grid-cols-3">
            {productHighlights.map((item) => (
              <article key={item.heading} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><FeatureIcon name={item.icon} /></div>
                <h3 className="text-base font-bold text-slate-950">{item.heading}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.body}</p>
              </article>
            ))}
          </section>

          <section id="security" className="mb-24 overflow-hidden rounded-[2rem] bg-slate-950 px-6 py-10 text-white sm:px-10 lg:flex lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-300">Private by design</p>
              <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">Your media stays scoped to your workspace.</h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">Google-backed sign-in, workspace authorization, secured cloud storage, and auditable processing keep every project organized and protected.</p>
            </div>
            <a href="#get-started" className="mt-7 inline-flex rounded-full bg-white px-6 py-3 text-sm font-bold text-slate-950 transition hover:bg-indigo-100 lg:mt-0">
              Create your workspace
            </a>
          </section>
        </main>

        <footer className="flex flex-col gap-4 border-t border-slate-200 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 GlobeSync. Built for multilingual teams.</p>
          <div className="flex gap-5">
            <a href="#how-it-works" className="hover:text-indigo-600">How it works</a>
            <a href="#features" className="hover:text-indigo-600">Features</a>
            <a href="#security" className="hover:text-indigo-600">Security</a>
          </div>
        </footer>
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

        <div className="flex flex-1 items-center justify-center" role="status" aria-live="polite">
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
type StatusFilter = 'all' | 'draft' | 'processing' | 'completed' | 'failed';

type ProjectActionsMenuProps = {
  projectId: string;
  projectName: string;
  onRename: (projectId: string, name: string) => Promise<void>;
  onArchive: (projectId: string) => Promise<void>;
  onDuplicate: (projectId: string) => Promise<void>;
};

function ProjectActionsMenu({ projectId, projectName, onRename, onArchive, onDuplicate }: ProjectActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const handleRename = async () => {
    const newName = window.prompt(`Rename "${projectName}":`, projectName);
    if (!newName || newName.trim() === projectName) return;
    setOpen(false);
    setBusy('rename');
    try {
      await onRename(projectId, newName.trim());
    } catch {
      window.alert('Could not rename project. Please try again.');
    } finally {
      setBusy(null);
    }
  };

  const handleDuplicate = async () => {
    setOpen(false);
    setBusy('duplicate');
    try {
      await onDuplicate(projectId);
    } catch {
      window.alert('Could not duplicate project. Please try again.');
    } finally {
      setBusy(null);
    }
  };

  const handleArchive = async () => {
    if (!window.confirm(`Archive "${projectName}"? It will be hidden from your workspace.`)) return;
    setOpen(false);
    setBusy('archive');
    try {
      await onArchive(projectId);
    } catch {
      window.alert('Could not archive project. Please try again.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!!busy}
        className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-white/10 hover:text-slate-300 disabled:opacity-40"
        aria-label="Project actions"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={`project-actions-${projectId}`}
      >
        {busy ? (
          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
          </svg>
        )}
      </button>
      {open && (
        <div id={`project-actions-${projectId}`} className="absolute right-0 top-9 z-50 min-w-[160px] rounded-2xl border border-white/10 bg-slate-900 py-1 shadow-2xl shadow-black/40" role="menu">
          <button
            type="button"
            role="menuitem"
            autoFocus
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
            onClick={() => void handleRename()}
          >
            Rename
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
            onClick={() => void handleDuplicate()}
          >
            Duplicate
          </button>
          <div className="my-1 border-t border-white/10" />
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-rose-400 transition hover:bg-rose-500/10 hover:text-rose-300"
            onClick={() => void handleArchive()}
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
  onSwapLanguages,
  onCreateProject,
  onSignOut,
  onRename,
  onArchive,
  onDuplicate,
  availableWorkspaces,
  onWorkspaceChange,
  workspaceMembers,
}: WorkspaceHomeProps) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('updatedAt');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const visibleProjects = projects
    .filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
    .filter((p) => statusFilter === 'all' || p.status === statusFilter)
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
          <Link href="/" aria-current="page" className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            Home
          </Link>
          <button type="button" disabled title="Open a project to upload media" className="flex w-full cursor-not-allowed items-center gap-3 rounded-xl px-4 py-2.5 text-left text-sm font-medium text-slate-600 opacity-70">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Uploads
          </button>
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
                <p className="truncate text-[11px] capitalize text-slate-500">{authContext.membership.role}</p>
                {availableWorkspaces.length > 1 ? (
                  <select aria-label="Switch workspace" value={authContext.workspace.id} onChange={(event) => void onWorkspaceChange(event.target.value)} className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950/70 px-2 py-1 text-xs text-slate-300">
                    {availableWorkspaces.map(({ workspace }) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
                  </select>
                ) : null}
              </div>
            </div>
            {workspaceMembers.length > 1 ? (
              <div className="mb-4 rounded-xl border border-white/10 bg-slate-950/40 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Workspace members</p>
                <p className="mt-1 text-xs text-slate-400">{workspaceMembers.length} people with access to this workspace</p>
              </div>
            ) : null}
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
            <div className="min-w-0">
              <span className="block text-xl font-bold tracking-tight text-white">Globe<span className="text-indigo-400">Sync</span></span>
              <span className="mt-1 block truncate text-xs text-slate-500">{authContext.workspace.name} · <span className="capitalize">{authContext.membership.role}</span></span>
              {availableWorkspaces.length > 1 ? (
                <select aria-label="Switch workspace" value={authContext.workspace.id} onChange={(event) => void onWorkspaceChange(event.target.value)} className="mt-2 max-w-[12rem] rounded-lg border border-white/10 bg-slate-950/70 px-2 py-1 text-xs text-slate-300">
                  {availableWorkspaces.map(({ workspace }) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
                </select>
              ) : null}
            </div>
            <button type="button" onClick={onSignOut} className="shrink-0 text-sm text-slate-400">Sign out</button>
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
                      aria-label="Project name"
                      placeholder="Project name"
                      className="gs-field"
                      value={newProjectName}
                      onChange={(e) => onProjectNameChange(e.target.value)}
                    />
                    <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_auto_1fr]">
                      <select
                        aria-label="Source language"
                        dir={getTextDirection(sourceLang)}
                        className="gs-field px-2 py-2 text-xs text-slate-300"
                        value={sourceLang}
                        onChange={(e) => onSourceLangChange(e.target.value)}
                      >
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                      <button
                        type="button"
                        onClick={onSwapLanguages}
                        className="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 text-sm text-slate-400 transition hover:border-indigo-400 hover:text-indigo-200"
                        aria-label="Swap source and target languages"
                        title="Swap languages"
                      >
                        &#8646;
                      </button>
                      <select
                        aria-label="Target language"
                        dir={getTextDirection(targetLang)}
                        className="gs-field px-2 py-2 text-xs text-slate-300"
                        value={targetLang}
                        onChange={(e) => onTargetLangChange(e.target.value)}
                      >
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <Button
                      type="submit"
                      disabled={isCreatingProject || !newProjectName.trim()}
                      variant="primary"
                      loading={isCreatingProject}
                      className="w-full"
                    >
                      {isCreatingProject ? 'Creating...' : 'Start Upload'}
                    </Button>
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
                <form onSubmit={onCreateProject} className="grid gap-4 sm:grid-cols-[1fr_auto_auto_auto_auto] items-end">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Project name</label>
                      <input type="text" placeholder="e.g. Product Launch Hindi Dub" className="gs-field px-4 py-2.5" value={newProjectName} onChange={(e) => onProjectNameChange(e.target.value)} />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Source</label>
                      <select aria-label="Source language" dir={getTextDirection(sourceLang)} className="gs-field px-4 py-2.5 text-slate-300" value={sourceLang} onChange={(e) => onSourceLangChange(e.target.value)}>
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={onSwapLanguages}
                      className="mb-0.5 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-sm text-slate-400 transition hover:border-indigo-400 hover:text-indigo-200"
                      aria-label="Swap source and target languages"
                      title="Swap languages"
                    >
                      &#8646;
                    </button>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">Target</label>
                      <select aria-label="Target language" dir={getTextDirection(targetLang)} className="gs-field px-4 py-2.5 text-slate-300" value={targetLang} onChange={(e) => onTargetLangChange(e.target.value)}>
                        {languageOptions.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                      </select>
                    </div>
                    <Button type="submit" disabled={isCreatingProject || !newProjectName.trim()} loading={isCreatingProject} className="px-6 py-2.5">
                      {isCreatingProject ? 'Creating...' : '+ New Project'}
                    </Button>
                </form>
             </section>
          )}

          {hasProjects && (
            <section>
              <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Filter projects by status">
                {(['all', 'draft', 'processing', 'completed', 'failed'] as StatusFilter[]).map((f) => {
                  const labels: Record<StatusFilter, string> = { all: 'All', draft: 'Planning', processing: 'Processing', completed: 'Complete', failed: 'Needs attention' };
                  const active = statusFilter === f;
                  return (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setStatusFilter(f)}
                      aria-pressed={active}
                      className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                        active
                          ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200'
                          : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-white'
                      }`}
                    >
                      {labels[f]}
                      {f !== 'all' && (
                        <span className="ml-1.5 opacity-60">{projects.filter((p) => p.status === f).length}</span>
                      )}
                    </button>
                  );
                })}
              </div>
              <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="text-xl font-semibold text-white">
                  {statusFilter === 'all' ? 'All Projects' : ({ draft: 'Planning', processing: 'Processing', completed: 'Complete', failed: 'Needs attention' } as Record<StatusFilter, string>)[statusFilter]}
                </h2>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M10 6.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0ZM9.5 10.207l3.146 3.147a.5.5 0 0 0 .708-.708L10.207 9.5A4.5 4.5 0 1 0 9.5 10.207Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"/></svg>
                    <input type="text" aria-label="Search projects by name" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-full rounded-full border border-white/10 bg-slate-900/60 py-1.5 pl-8 pr-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-indigo-400 sm:w-48" />
                  </div>
                  <select aria-label="Sort projects" value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="rounded-full border border-white/10 bg-slate-900/60 px-3 py-1.5 text-sm text-slate-300 outline-none focus:border-indigo-400">
                    <option value="updatedAt">Last updated</option>
                    <option value="createdAt">Date created</option>
                    <option value="name">Name</option>
                  </select>
                </div>
              </div>

              {visibleProjects.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-sm text-slate-400">No projects match the current search and filters.</p>
                  <button
                    type="button"
                    onClick={() => {
                      setSearch('');
                      setStatusFilter('all');
                    }}
                    className="mt-3 rounded-control border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-white/30 hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                  >
                    Clear search and filters
                  </button>
                </div>
              ) : (
                <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                  {visibleProjects.map((project) => {
                    const isProcessing = project.status === 'processing';
                    const isFailed = project.status === 'failed';
                    const progress = Math.max(0, Math.min(100, project.pipelineProgressPercent ?? 0));

                    return (
                    <article key={project.id} className="group relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/60 transition duration-interface ease-interface hover:-translate-y-0.5 hover:border-white/20 hover:bg-slate-800/80 hover:shadow-panel motion-reduce:transform-none">
                      {/* HeyGen style Thumbnail Area */}
                      <div className="relative aspect-video w-full bg-slate-950/80">
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-600">
                          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                          {!project.mediaId ? <span className="text-xs font-medium">No media yet</span> : null}
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
                              <ProjectActionsMenu
                                projectId={project.id}
                                projectName={project.name}
                                onRename={onRename}
                                onArchive={onArchive}
                                onDuplicate={onDuplicate}
                              />
                           </div>
                        </div>

                        {/* Bottom Left Badges */}
                        <div className="absolute bottom-2 left-2 flex gap-2">
                           <span className="flex items-center gap-1.5 rounded-lg bg-black/70 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-md">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/></svg>
                              {project.mediaId ? 'Translation' : 'Setup'}
                           </span>
                           <StatusBadge tone={getProjectStatusTone(project.status)} className="rounded-lg bg-black/55 px-2 py-1 text-[10px] uppercase tracking-wider backdrop-blur-md">
                             {formatProjectStatus(project.status)}
                           </StatusBadge>
                        </div>
                        
                        {/* Bottom Right Duration Badge */}
                        <div className="absolute bottom-2 right-2 flex gap-2">
                           {formatDuration(project.mediaDurationSeconds) ? (
                             <span className="flex items-center gap-1 rounded-lg bg-black/70 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-md">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                                {formatDuration(project.mediaDurationSeconds)}
                             </span>
                           ) : null}
                        </div>
                      </div>

                      {/* Card Content */}
                      <div className="p-4">
                        <Link href={`/editor/${project.id}`} className="block">
                          <h3 className="truncate text-base font-semibold text-white group-hover:text-indigo-300 transition">{project.name}</h3>
                        </Link>
                        <p className="hidden">
                          {formatProjectDate(project.createdAt)} • {project.sourceLanguage.toUpperCase()} → {project.targetLanguage.toUpperCase()}
                        </p>
                        <p className="gs-meta mt-1">
                          Updated {formatProjectDate(project.updatedAt)} | {project.sourceLanguage.toUpperCase()} to {project.targetLanguage.toUpperCase()}
                        </p>
                        {isProcessing ? (
                          <div className="mt-4 rounded-control border border-amber-400/20 bg-amber-400/5 p-3">
                            <div className="flex items-center justify-between gap-3 text-xs">
                              <span className="font-semibold text-amber-100">{formatPipelineStage(project.pipelineStage)}</span>
                              <span className="shrink-0 text-amber-200">{project.pipelineProgressPercent !== undefined ? `${progress}%` : 'In progress'}</span>
                            </div>
                            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-amber-950/70" role="progressbar" aria-label={`${formatPipelineStage(project.pipelineStage)} progress`} aria-valuetext={`${formatPipelineStage(project.pipelineStage)}: ${project.pipelineProgressPercent !== undefined ? `${progress}%` : 'in progress'}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={project.pipelineProgressPercent !== undefined ? progress : undefined}>
                              <div className="h-full rounded-full bg-amber-400 transition-[width] duration-interface ease-interface" style={{ width: `${project.pipelineProgressPercent !== undefined ? progress : 20}%` }} />
                            </div>
                          </div>
                        ) : null}
                        {isFailed ? (
                          <div className="mt-4 flex items-start justify-between gap-3 rounded-control border border-rose-400/20 bg-rose-400/5 p-3">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-rose-100">Needs attention</p>
                              <p className="mt-1 line-clamp-2 text-xs leading-5 text-rose-200/80" title={project.pipelineErrorMessage}>
                                {project.pipelineErrorMessage || 'Open the project to review the failed stage and recover safely.'}
                              </p>
                            </div>
                            <Link href={`/editor/${project.id}`} className="shrink-0 text-xs font-semibold text-rose-100 underline decoration-rose-300/50 underline-offset-4 transition hover:text-white">
                              Review
                            </Link>
                          </div>
                        ) : null}
                      </div>
                    </article>
                    );
                  })}
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
