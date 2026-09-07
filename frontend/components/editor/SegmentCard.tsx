import React from 'react';
import type { TranscriptSegment } from '../../store/mediaStore';
import type { Project } from '../../store/projectStore';
import type { TranslatedSegment } from '../../store/translationStore';
import { getTextDirection, normalizeLanguageTag } from '../../utils/textDirection';

type SegmentBusyState = 'retranslating' | 'synthesizing';

type SegmentCardProps = {
    currentProject: Project;
    segment: TranscriptSegment;
    translation?: TranslatedSegment;
    lipSyncStatus?: string;
    isDirty: boolean;
    isLooping: boolean;
    isSelected: boolean;
    isActionMenuOpen: boolean;
    isBusy?: SegmentBusyState;
    canResetTranslation: boolean;
    formatTimecode: (seconds: number) => string;
    actionMenuContainerRef: (element: HTMLDivElement | null) => void;
    onSelect: () => void;
    onSeek: () => void;
    onPlay: () => void;
    onToggleLoop: () => void;
    onSourceTextChange: (text: string) => void;
    onTranslationTextChange: (text: string) => void;
    onToggleActionMenu: () => void;
    onRetranslate: () => void;
    onSynthesize: () => void;
    onResetTranslation: () => void;
};

export default function SegmentCard({
    currentProject,
    segment,
    translation,
    lipSyncStatus,
    isDirty,
    isLooping,
    isSelected,
    isActionMenuOpen,
    isBusy,
    canResetTranslation,
    formatTimecode,
    actionMenuContainerRef,
    onSelect,
    onSeek,
    onPlay,
    onToggleLoop,
    onSourceTextChange,
    onTranslationTextChange,
    onToggleActionMenu,
    onRetranslate,
    onSynthesize,
    onResetTranslation,
}: SegmentCardProps) {
    const isMissingTranslation = !translation;
    const isDurationOverflow = Boolean(translation && translation.durationRatio > 1.15);
    const isDurationUnderflow = Boolean(translation && translation.durationRatio < 0.75);
    const isLowConfidence = Boolean(translation && translation.qualityScore < 0.5);
    const isMissingGeneratedAudio = Boolean(translation && translation.generatedAudioStatus !== 'ready');
    const hasLipSyncFailure = lipSyncStatus === 'failed';
    const hasRisk = isMissingTranslation || isDurationOverflow || isDurationUnderflow || isLowConfidence || isMissingGeneratedAudio || hasLipSyncFailure;

    return (
        <div
            data-segment-id={segment.id}
            onClick={onSelect}
            role="group"
            aria-label={`Segment by ${segment.speakerTag} at ${formatTimecode(segment.startTimeSeconds)}`}
            className={`border rounded-xl p-4 transition grid grid-cols-1 gap-4 cursor-pointer md:grid-cols-2 ${isSelected
                    ? 'border-indigo-500 bg-indigo-950/20 shadow-[0_0_15px_rgba(99,102,241,0.1)]'
                    : isDirty
                        ? 'border-amber-500/50 bg-amber-950/20'
                        : hasRisk
                            ? 'border-red-800/50 bg-red-950/10'
                            : 'border-slate-800 bg-slate-900/30 hover:border-slate-700 hover:bg-slate-900/50'
                }`}
        >
            <div>
                <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={(event) => {
                                event.stopPropagation();
                                onPlay();
                            }}
                            className="flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-indigo-300 transition hover:bg-indigo-500 hover:text-white"
                        >
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>
                            Play
                        </button>
                        <button
                            type="button"
                            onClick={(event) => {
                                event.stopPropagation();
                                onToggleLoop();
                            }}
                            className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider transition ${isLooping
                                    ? 'bg-amber-500/30 text-amber-200'
                                    : 'bg-slate-800 text-slate-500 hover:bg-slate-700 hover:text-slate-200'
                                }`}
                            aria-pressed={isLooping}
                            title="Loop this segment"
                        >
                            Loop
                        </button>
                        <span className="text-xs font-bold uppercase text-slate-500">{segment.speakerTag}</span>
                        <span className="text-[10px] text-slate-600">{segment.durationSeconds.toFixed(1)}s</span>
                    </div>
                    <button
                        type="button"
                        onClick={(event) => {
                            event.stopPropagation();
                            onSeek();
                        }}
                        className="text-xs font-mono text-slate-500 transition hover:text-white"
                    >
                        {formatTimecode(segment.startTimeSeconds)}
                    </button>
                </div>
                <textarea
                    lang={normalizeLanguageTag(currentProject.sourceLanguage)}
                    dir={getTextDirection(currentProject.sourceLanguage)}
                    aria-label={`Source transcript for ${segment.speakerTag} at ${formatTimecode(segment.startTimeSeconds)}`}
                    className="h-16 w-full resize-none rounded-lg border border-slate-800 bg-slate-950 p-2 text-sm text-white break-words focus:border-indigo-700 focus:outline-none"
                    value={segment.text}
                    onChange={(event) => onSourceTextChange(event.target.value)}
                />
            </div>

            <div>
                <div className="mb-2 flex items-center justify-between">
                    <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-bold uppercase text-indigo-400">Translation ({currentProject.targetLanguage})</span>
                        {isMissingTranslation && (
                            <span className="rounded bg-red-950 px-1.5 py-0.5 text-[10px] font-semibold text-red-400">Missing</span>
                        )}
                        {isDurationOverflow && translation && (
                            <span className="rounded bg-red-950 px-1.5 py-0.5 text-[10px] font-semibold text-red-400" title="Translation is too long — will be sped up">
                                Too long · {translation.durationRatio.toFixed(2)}x
                            </span>
                        )}
                        {isDurationUnderflow && translation && (
                            <span className="rounded bg-amber-950 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400" title="Translation is too short — may have silence gaps">
                                Too short · {translation.durationRatio.toFixed(2)}x
                            </span>
                        )}
                        {isLowConfidence && !isMissingTranslation && (
                            <span className="rounded bg-amber-950 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400" title="Low translation confidence score">
                                Low confidence
                            </span>
                        )}
                        {hasLipSyncFailure && (
                            <span className="rounded bg-red-950 px-1.5 py-0.5 text-[10px] font-semibold text-red-400" title="Lip-sync rendering failed for this segment">
                                Lip-sync failed
                            </span>
                        )}
                        {isMissingGeneratedAudio && (
                            <span className="rounded bg-red-950 px-1.5 py-0.5 text-[10px] font-semibold text-red-400" title="Generated dubbed audio is not ready for this segment">
                                No audio
                            </span>
                        )}
                        {translation && !hasRisk && (
                            <span className="rounded bg-green-950 px-1.5 py-0.5 text-[10px] font-semibold text-green-400">OK</span>
                        )}
                    </div>

                    <div ref={actionMenuContainerRef} className="relative" onClick={(event) => event.stopPropagation()}>
                        <button
                            type="button"
                            onClick={onToggleActionMenu}
                            disabled={Boolean(isBusy)}
                            className="rounded px-1.5 py-0.5 text-sm text-slate-500 transition hover:text-white disabled:opacity-40"
                            aria-label="Segment actions"
                            aria-haspopup="menu"
                            aria-expanded={isActionMenuOpen}
                            aria-controls={`segment-actions-${segment.id}`}
                            title="Segment actions"
                        >
                            {isBusy === 'retranslating' ? 'Translating…' : isBusy === 'synthesizing' ? 'Synthesizing…' : '⋯'}
                        </button>
                        {isActionMenuOpen && (
                            <div id={`segment-actions-${segment.id}`} className="absolute right-0 top-6 z-20 w-44 rounded-xl border border-slate-700 bg-slate-900 py-1 text-sm shadow-xl" role="menu">
                                <button
                                    type="button"
                                    role="menuitem"
                                    onClick={onRetranslate}
                                    className="w-full px-3 py-2 text-left text-slate-200 transition hover:bg-slate-800"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5" /><path d="M20 4v7h-7" /></svg>
                                    Retranslate
                                </button>
                                <button
                                    type="button"
                                    role="menuitem"
                                    onClick={onSynthesize}
                                    disabled={!translation?.id}
                                    className="w-full px-3 py-2 text-left text-slate-200 transition hover:bg-slate-800 disabled:opacity-40"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 5.5a9 9 0 0 1 0 13" /></svg>
                                    Regenerate audio
                                </button>
                                <div className="my-1 border-t border-slate-800" />
                                <button
                                    type="button"
                                    role="menuitem"
                                    onClick={onResetTranslation}
                                    disabled={!canResetTranslation}
                                    className="w-full px-3 py-2 text-left text-red-400 transition hover:bg-slate-800 disabled:opacity-40"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
                                    Reset to original
                                </button>
                            </div>
                        )}
                    </div>
                </div>
                <textarea
                    lang={normalizeLanguageTag(currentProject.targetLanguage)}
                    dir={getTextDirection(currentProject.targetLanguage)}
                    aria-label={`Translation in ${currentProject.targetLanguage.toUpperCase()} for ${segment.speakerTag} at ${formatTimecode(segment.startTimeSeconds)}`}
                    className={`h-16 w-full resize-none rounded-lg border bg-slate-950 p-2 text-sm text-indigo-100 break-words focus:outline-none ${isDirty ? 'border-amber-600/60 focus:border-amber-500' : 'border-slate-800 focus:border-indigo-700'
                        }`}
                    value={translation?.translatedText || ''}
                    onChange={(event) => onTranslationTextChange(event.target.value)}
                    placeholder={isMissingTranslation ? 'No translation yet — use ⋯ to retranslate' : 'Edit translation…'}
                />
            </div>
        </div>
    );
}
