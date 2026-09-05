import { StatePanel, StatusBadge } from '../ui';

type PipelineStage = 'upload' | 'transcribe' | 'translate' | 'voice' | 'lip_sync' | 'export';

type PipelineStatusProps = {
  mode: 'upstream' | 'dub_only' | 'dub_and_lipsync';
  status: string;
  progressPercent: number;
  currentStage: string;
  lastSuccessfulStage?: string | null;
  errorMessage?: string | null;
  hasMedia: boolean;
  hasTranscript: boolean;
  translationCount: number;
  segmentCount: number;
};

const stages: Array<{ id: PipelineStage; label: string }> = [
  { id: 'upload', label: 'Upload' },
  { id: 'transcribe', label: 'Transcribe' },
  { id: 'translate', label: 'Translate' },
  { id: 'voice', label: 'Voice' },
  { id: 'lip_sync', label: 'Lip-sync' },
  { id: 'export', label: 'Export' },
];

function stageLabel(stage?: string | null): string {
  if (!stage) return 'None yet';
  return stage.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function recoveryMessage(stage?: string | null): string {
  switch (stage) {
    case 'transcribe':
      return 'Check that the source media is available and the source language is correct, then retry transcription. Your project and saved drafts are preserved.';
    case 'translate':
      return 'Check the source transcript and target language, then retry translation. Your transcript and saved drafts are preserved.';
    case 'voice':
      return 'Check the translated segments and voice configuration, then start a new build. Your saved translations are preserved.';
    case 'lip_sync':
      return 'Check that the source has a clear, front-facing speaker and that the lip-sync provider is configured, then start a new build. Your translations and prior outputs are preserved.';
    case 'export':
      return 'The final artifact was not published. Check storage access and try a new build; existing outputs and saved translations are preserved.';
    default:
      return 'Review the project inputs and start a new build when ready. Your saved translations and existing outputs are preserved.';
  }
}

export function PipelineStatus({
  mode,
  status,
  progressPercent,
  currentStage,
  lastSuccessfulStage,
  errorMessage,
  hasMedia,
  hasTranscript,
  translationCount,
  segmentCount,
}: PipelineStatusProps) {
  const normalizedStage = currentStage.replace(/-/g, '_').toLowerCase() as PipelineStage;
  const isFailed = status === 'failed';
  const isCompleted = status === 'completed';
  const progress = Math.max(0, Math.min(100, progressPercent));
  const prerequisites = {
    upload: hasMedia,
    transcribe: hasTranscript && segmentCount > 0,
    translate: segmentCount > 0 && translationCount >= segmentCount,
  };
  const visibleStages = mode === 'dub_only' ? stages.filter((stage) => stage.id !== 'lip_sync') : stages;

  return (
    <section className="gs-panel space-y-4 p-4" aria-labelledby="pipeline-status-heading" aria-live="polite" aria-busy={status === 'queued' || status === 'in_progress' || status === 'processing'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="pipeline-status-heading" className="text-sm font-bold text-white">
            {mode === 'upstream' ? 'Project processing status' : mode === 'dub_only' ? 'Dub build status' : 'Dub + Lip-Sync build status'}
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            {isCompleted ? 'The build is complete.' : isFailed ? `Stopped during ${stageLabel(normalizedStage)}.` : `Currently ${stageLabel(normalizedStage)}.`}
          </p>
        </div>
        <StatusBadge tone={isFailed ? 'error' : isCompleted ? 'success' : 'processing'}>
          {isFailed ? 'Needs attention' : isCompleted ? 'Completed' : `${progress}% in progress`}
        </StatusBadge>
      </div>

      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-label="Build stages">
        {visibleStages.map((stage) => {
          const prerequisiteComplete = prerequisites[stage.id as keyof typeof prerequisites];
          const isCurrent = stage.id === normalizedStage;
          const isComplete = isCompleted || prerequisiteComplete || stages.findIndex((item) => item.id === normalizedStage) > stages.findIndex((item) => item.id === stage.id);
          const tone = isCurrent && isFailed ? 'border-rose-400/50 bg-rose-400/10 text-rose-100' : isCurrent ? 'border-amber-400/50 bg-amber-400/10 text-amber-100' : isComplete ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100' : 'border-slate-800 bg-slate-950/40 text-slate-500';
          return (
            <li key={stage.id} className={`rounded-control border px-3 py-2 text-xs font-semibold ${tone}`}>
              <span className="mr-1.5 text-[10px] uppercase tracking-wide">{isCurrent && !isFailed ? 'Active' : isComplete ? 'Done' : 'Waiting'}</span>
              {stage.label}
            </li>
          );
        })}
      </ol>

      {!isCompleted && !isFailed && (
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-800" role="progressbar" aria-label="Build progress" aria-valuetext={`${progress}% during ${stageLabel(normalizedStage)}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <div className="h-full rounded-full bg-indigo-500 transition-[width] duration-interface ease-interface" style={{ width: `${Math.max(4, progress)}%` }} />
        </div>
      )}

      {isFailed && (
        <StatePanel title={`Safe recovery from ${stageLabel(normalizedStage)}`} tone="error">
          {errorMessage ? `${errorMessage} ` : ''}{recoveryMessage(normalizedStage)}
          {lastSuccessfulStage ? ` Last successful checkpoint: ${stageLabel(lastSuccessfulStage)}.` : ''}
        </StatePanel>
      )}
    </section>
  );
}
