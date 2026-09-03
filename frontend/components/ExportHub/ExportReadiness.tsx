import type { TranscriptSegment } from '../../store/mediaStore';
import type { TranslatedSegment } from '../../store/translationStore';
import { StatePanel, StatusBadge } from '../ui';

type ExportReadinessProps = {
  hasDraftConflict: boolean;
  hasMedia: boolean;
  hasTranscript: boolean;
  dirtySegmentCount: number;
  segments: TranscriptSegment[];
  translations: Record<string, TranslatedSegment>;
};

type ReadinessIssue = {
  count: number;
  label: string;
  severity: 'blocker' | 'warning';
};

function formatIssue(issue: ReadinessIssue): string {
  if (issue.count === 1) return issue.label;
  return `${issue.count} ${issue.label.replace('segment ', 'segments ')}`;
}

export function ExportReadiness({
  hasDraftConflict,
  hasMedia,
  hasTranscript,
  dirtySegmentCount,
  segments,
  translations,
}: ExportReadinessProps) {
  const missingTranslations = segments.filter((segment) => !translations[segment.id]).length;
  const timingRisks = segments.filter((segment) => {
    const translation = translations[segment.id];
    return translation && (translation.durationRatio > 1.15 || translation.durationRatio < 0.75);
  }).length;
  const confidenceRisks = segments.filter((segment) => {
    const translation = translations[segment.id];
    return translation && translation.qualityScore < 0.5;
  }).length;
  const missingAudio = segments.filter((segment) => {
    const translation = translations[segment.id];
    return translation && translation.generatedAudioStatus !== 'ready';
  }).length;

  const blockers: ReadinessIssue[] = [
    ...(!hasMedia ? [{ count: 1, label: 'Source media is required', severity: 'blocker' as const }] : []),
    ...(!hasTranscript || segments.length === 0 ? [{ count: 1, label: 'A completed transcript is required', severity: 'blocker' as const }] : []),
    ...(missingTranslations > 0 ? [{ count: missingTranslations, label: 'segment has no translation', severity: 'blocker' as const }] : []),
    ...(hasDraftConflict ? [{ count: 1, label: 'draft conflict needs review before rendering', severity: 'blocker' as const }] : []),
  ];
  const warnings: ReadinessIssue[] = [
    ...(dirtySegmentCount > 0 ? [{ count: dirtySegmentCount, label: 'edited segments have not been saved', severity: 'warning' as const }] : []),
    ...(timingRisks > 0 ? [{ count: timingRisks, label: 'segment needs timing-fit review', severity: 'warning' as const }] : []),
    ...(confidenceRisks > 0 ? [{ count: confidenceRisks, label: 'segment has low translation confidence', severity: 'warning' as const }] : []),
    ...(missingAudio > 0 ? [{ count: missingAudio, label: 'segment audio will be synthesized during build', severity: 'warning' as const }] : []),
  ];
  const isReady = blockers.length === 0;

  return (
    <section className="gs-panel space-y-4 p-5" aria-labelledby="export-readiness-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h2 id="export-readiness-heading" className="text-sm font-bold text-white">Export readiness</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">Review requirements and quality signals before starting a render.</p>
        </div>
        <StatusBadge tone={isReady ? 'success' : 'error'}>{isReady ? 'Ready to build' : 'Action required'}</StatusBadge>
      </div>

      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-control border border-white/10 bg-slate-950/50 p-3">
          <p className="text-lg font-semibold text-white">{segments.length}</p>
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Transcript segments</p>
        </div>
        <div className="rounded-control border border-white/10 bg-slate-950/50 p-3">
          <p className="text-lg font-semibold text-white">{segments.length - missingTranslations}/{segments.length}</p>
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Translated</p>
        </div>
      </div>

      {blockers.length > 0 ? (
        <StatePanel title="Resolve before rendering" tone="error">
          <ul className="mt-1 list-disc space-y-1 pl-4">
            {blockers.map((issue) => <li key={issue.label}>{formatIssue(issue)}</li>)}
          </ul>
        </StatePanel>
      ) : null}

      {warnings.length > 0 ? (
        <StatePanel title="Quality checks recommended" tone="warning">
          <ul className="mt-1 list-disc space-y-1 pl-4">
            {warnings.map((issue) => <li key={issue.label}>{formatIssue(issue)}</li>)}
          </ul>
        </StatePanel>
      ) : null}

      {isReady && warnings.length === 0 ? (
        <StatePanel title="All checks passed" tone="success">The available media, transcript, translations, and save state are ready for a build.</StatePanel>
      ) : null}
    </section>
  );
}
