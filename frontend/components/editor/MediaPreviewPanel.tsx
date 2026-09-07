import type { PointerEvent as ReactPointerEvent, RefObject } from 'react';
import WaveformCanvas from '../WaveformRenderer/WaveformCanvas';
import type { TranscriptSegment } from '../../store/mediaStore';
import type { Project } from '../../store/projectStore';
import type { WaveformData } from '../../utils/waveformProcessing';

type MediaPreviewPanelProps = {
    currentProject: Project;
    comparisonMode: 'original' | 'dubbed';
    sourceMediaUrl: string | null;
    renderedVideoUrl: string | null;
    previewUrl: string | null;
    previewDownloadName: string;
    waveformData: WaveformData | null;
    totalDurationSeconds: number;
    segments: TranscriptSegment[];
    selectedSegment: TranscriptSegment | null;
    selectedSegmentId: string | null;
    currentTimeSeconds: number;
    isPlaying: boolean;
    videoRef: RefObject<HTMLVideoElement | null>;
    formatTimecode: (seconds: number) => string;
    onComparisonModeChange: (mode: 'original' | 'dubbed') => void;
    onRefreshSourceMediaUrl: () => void;
    onRefreshRenderedVideoUrl: () => void;
    onSeek: (seconds: number, segmentId?: string) => void;
    onTogglePlayback: () => void;
    onPlaySelectedSegment: () => void;
    onTimelinePointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
    onTimelinePointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void;
    onTimelinePointerUp: (event: ReactPointerEvent<HTMLDivElement>) => void;
    onTimelinePointerCancel: () => void;
};

export default function MediaPreviewPanel({
    currentProject,
    comparisonMode,
    sourceMediaUrl,
    renderedVideoUrl,
    previewUrl,
    previewDownloadName,
    waveformData,
    totalDurationSeconds,
    segments,
    selectedSegment,
    selectedSegmentId,
    currentTimeSeconds,
    isPlaying,
    videoRef,
    formatTimecode,
    onComparisonModeChange,
    onRefreshSourceMediaUrl,
    onRefreshRenderedVideoUrl,
    onSeek,
    onTogglePlayback,
    onPlaySelectedSegment,
    onTimelinePointerDown,
    onTimelinePointerMove,
    onTimelinePointerUp,
    onTimelinePointerCancel,
}: MediaPreviewPanelProps) {
    const previewLabel = comparisonMode === 'original' ? 'original' : 'dubbed';
    const activeVideoUrl = comparisonMode === 'original' ? sourceMediaUrl : (renderedVideoUrl || sourceMediaUrl);

    const handleDownloadPreview = async () => {
        if (!previewUrl) {
            return;
        }

        try {
            const response = await fetch(previewUrl);
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = objectUrl;
            anchor.download = previewDownloadName;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            URL.revokeObjectURL(objectUrl);
        } catch {
            window.open(previewUrl, '_blank');
        }
    };

    return (
        <aside className="order-first flex min-h-0 min-w-0 flex-col overflow-y-auto border-l border-slate-800 bg-slate-950 p-4 md:order-last xl:p-5" aria-label="Media preview and timeline">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                    <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-indigo-400">Media monitor</p>
                    <h2 className="mt-1 text-sm font-semibold text-white">Project preview</h2>
                </div>
                <div className="flex rounded-lg border border-slate-700 bg-slate-900 p-1">
                    <button
                        type="button"
                        onClick={() => onComparisonModeChange('original')}
                        disabled={!sourceMediaUrl?.startsWith('http')}
                        aria-pressed={comparisonMode === 'original'}
                        className={`rounded-md px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${comparisonMode === 'original' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                    >
                        Original
                    </button>
                    <button
                        type="button"
                        onClick={() => onComparisonModeChange('dubbed')}
                        disabled={!renderedVideoUrl}
                        aria-pressed={comparisonMode === 'dubbed'}
                        className={`rounded-md px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${comparisonMode === 'dubbed' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                    >
                        Dubbed
                    </button>
                </div>
            </div>

            <div className="relative flex aspect-video min-h-[240px] w-full shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-700 bg-black text-slate-500 shadow-lg shadow-black/30">
                {comparisonMode === 'dubbed' && !renderedVideoUrl && sourceMediaUrl ? (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/60 p-4 text-center backdrop-blur-[2px]">
                        <p className="text-sm font-semibold text-slate-200">Dubbed preview not ready yet. Click Original to keep reviewing the source video.</p>
                        <p className="mt-2 text-xs text-slate-400">Run Build when you're ready to generate the dubbed preview.</p>
                    </div>
                ) : null}

                {activeVideoUrl ? (
                    <video
                        key={activeVideoUrl}
                        ref={videoRef}
                        src={activeVideoUrl ?? undefined}
                        controls
                        aria-label={`${comparisonMode === 'original' ? currentProject.sourceLanguage.toUpperCase() : currentProject.targetLanguage.toUpperCase()} video preview`}
                        className={`h-full w-full object-contain ${comparisonMode === 'dubbed' && !renderedVideoUrl ? 'opacity-50' : ''}`}
                        onError={() => {
                            if (comparisonMode === 'original') {
                                onRefreshSourceMediaUrl();
                                return;
                            }
                            onRefreshRenderedVideoUrl();
                        }}
                    >
                        Your browser does not support embedded video playback.
                    </video>
                ) : (
                    'Preview Media Player Placeholder'
                )}
            </div>

            <div className="mt-4 shrink-0 rounded-xl border border-slate-700/70 bg-slate-900 p-4">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Export Output</h3>
                        <p className="mt-2 text-sm text-slate-300">
                            {renderedVideoUrl
                                ? comparisonMode === 'original'
                                    ? 'The original source video is selected in Media monitor.'
                                    : `Your ${currentProject.targetLanguage.toUpperCase()} dubbed video preview is ready.`
                                : 'Run Dub only or Dub & Lip-Sync to generate a preview and downloadable output.'}
                        </p>
                    </div>
                    {previewUrl && (
                        <div className="flex shrink-0 gap-2">
                            <a
                                href={previewUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500"
                            >
                                {comparisonMode === 'original' ? 'Open original' : 'Open dubbed'}
                            </a>
                            <button
                                type="button"
                                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                                onClick={() => void handleDownloadPreview()}
                            >
                                {comparisonMode === 'original' ? 'Download original' : 'Download dubbed'}
                            </button>
                        </div>
                    )}
                </div>
                {previewUrl && (
                    <p className="mt-3 text-xs text-slate-500">
                        Downloading {previewLabel} media as `{previewDownloadName}`.
                    </p>
                )}
            </div>

            <div className="mt-4 flex min-h-[310px] flex-1 shrink-0 flex-col justify-between gap-4 rounded-xl border border-slate-700/70 bg-slate-900/70 p-4">
                <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Segment Timeline</h3>
                    <span className="text-xs text-slate-500">Click a segment bar to seek the preview player.</span>
                </div>
                <label className="flex items-center gap-3 text-xs text-slate-500">
                    <span className="shrink-0">Fine seek</span>
                    <input
                        type="range"
                        aria-label="Fine seek preview timeline"
                        min={0}
                        max={totalDurationSeconds || 1}
                        step={0.1}
                        value={Math.min(currentTimeSeconds, totalDurationSeconds || 1)}
                        onChange={(event) => onSeek(Number(event.target.value))}
                        disabled={segments.length === 0 || totalDurationSeconds === 0}
                        className="w-full accent-indigo-500 disabled:opacity-40"
                    />
                </label>
                <div
                    className="relative h-32 rounded-lg border border-slate-800 bg-slate-950 p-3"
                    onPointerDown={onTimelinePointerDown}
                    onPointerMove={onTimelinePointerMove}
                    onPointerUp={onTimelinePointerUp}
                    onPointerCancel={onTimelinePointerCancel}
                >
                    {segments.length === 0 || totalDurationSeconds === 0 ? (
                        <div className="flex h-full items-center justify-center text-xs text-slate-600">
                            Upload media to populate the review timeline.
                        </div>
                    ) : (
                        <div className="relative flex h-full items-end gap-1">
                            <div className="pointer-events-none absolute inset-0 opacity-70">
                                <WaveformCanvas
                                    data={waveformData}
                                    viewStart={0}
                                    viewEnd={totalDurationSeconds}
                                    width={1200}
                                    height={96}
                                />
                            </div>
                            {segments.map((segment) => {
                                const widthPercent = Math.max(8, (segment.durationSeconds / totalDurationSeconds) * 100);
                                const isActive = selectedSegmentId === segment.id;

                                return (
                                    <button
                                        key={segment.id}
                                        type="button"
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            onSeek(segment.startTimeSeconds, segment.id);
                                        }}
                                        aria-label={`Seek to segment ${formatTimecode(segment.startTimeSeconds)} by ${segment.speakerTag}`}
                                        aria-current={isActive ? 'true' : undefined}
                                        title={`${formatTimecode(segment.startTimeSeconds)} • ${segment.speakerTag}`}
                                        className={`min-w-[2rem] rounded-md border transition ${isActive
                                                ? 'border-indigo-400 bg-indigo-500/40'
                                                : 'border-slate-700 bg-slate-800 hover:border-slate-500 hover:bg-slate-700'
                                            }`}
                                        style={{ width: `${widthPercent}%`, height: `${Math.max(30, Math.min(96, 28 + segment.durationSeconds * 18))}px` }}
                                    />
                                );
                            })}
                        </div>
                    )}
                </div>
                <div className="sticky bottom-0 z-10 -mx-3 flex items-center justify-between border-t border-slate-800 bg-slate-900/95 px-3 py-3 backdrop-blur md:static md:mx-0 md:border-0 md:bg-transparent md:px-0 md:py-0 md:backdrop-blur-none">
                    <div>
                        <span className="text-sm font-mono text-slate-400">{formatTimecode(currentTimeSeconds)}</span>
                        {selectedSegment && (
                            <p className="mt-1 text-xs text-slate-500">
                                Focused segment: {selectedSegment.speakerTag} at {formatTimecode(selectedSegment.startTimeSeconds)}
                            </p>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={onTogglePlayback}
                        aria-label={isPlaying ? 'Pause preview' : 'Play preview'}
                        aria-pressed={isPlaying}
                        className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 p-2 text-white transition hover:bg-indigo-700"
                    >
                        {isPlaying ? (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>
                        ) : (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>
                        )}
                    </button>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                        type="button"
                        onClick={onPlaySelectedSegment}
                        disabled={!selectedSegment || (!sourceMediaUrl && !renderedVideoUrl)}
                        className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        Play selected segment
                    </button>
                </div>
            </div>
        </aside>
    );
}
