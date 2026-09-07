import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import type { TranscriptSegment } from '../store/mediaStore';
import type { Project } from '../store/projectStore';
import type { TranslatedSegment } from '../store/translationStore';
import { projectService } from '../services/projectService';
import { mapUserFacingError } from '../services/userFacingErrors';

type SegmentBusyState = Record<string, 'retranslating' | 'synthesizing'>;

type UseSegmentActionsOptions = {
    currentProject: Project | null;
    segments: TranscriptSegment[];
    translations: Record<string, TranslatedSegment>;
    originalTranslations: Record<string, string>;
    setTranslations: (translations: TranslatedSegment[]) => void;
    getLatestTranslations: () => Record<string, TranslatedSegment>;
    updateTranslationText: (segmentId: string, text: string) => void;
    setDirtySegments: Dispatch<SetStateAction<Set<string>>>;
    setUploadMessage: (message: string | null) => void;
};

export function useSegmentActions({
    currentProject,
    segments,
    translations,
    originalTranslations,
    setTranslations,
    getLatestTranslations,
    updateTranslationText,
    setDirtySegments,
    setUploadMessage,
}: UseSegmentActionsOptions) {
    const [activeActionMenu, setActiveActionMenu] = useState<string | null>(null);
    const [segmentBusy, setSegmentBusy] = useState<SegmentBusyState>({});
    const actionMenuContainersRef = useRef<Record<string, HTMLDivElement | null>>({});

    const closeActionMenu = useCallback(() => {
        setActiveActionMenu(null);
    }, []);

    const toggleActionMenu = useCallback((segmentId: string) => {
        setActiveActionMenu((current) => (current === segmentId ? null : segmentId));
    }, []);

    const clearBusyState = useCallback((segmentId: string) => {
        setSegmentBusy((previous) => {
            const next = { ...previous };
            delete next[segmentId];
            return next;
        });
    }, []);

    const registerActionMenuContainer = useCallback(
        (segmentId: string) => (element: HTMLDivElement | null) => {
            if (element) {
                actionMenuContainersRef.current[segmentId] = element;
                return;
            }

            delete actionMenuContainersRef.current[segmentId];
        },
        [],
    );

    const handleRetranslateSegment = useCallback(async (segmentId: string) => {
        if (!currentProject) return;

        const segmentIndex = segments.findIndex((segment) => segment.id === segmentId);
        if (segmentIndex === -1) return;

        const segment = segments[segmentIndex];
        setSegmentBusy((previous) => ({ ...previous, [segmentId]: 'retranslating' }));
        closeActionMenu();
        setUploadMessage('Retranslating segment…');

        try {
            const result = await projectService.retranslateSegment({
                segmentId: segment.id,
                sourceText: segment.text,
                originalDurationMs: Math.round(segment.durationSeconds * 1000),
                sourceLanguage: currentProject.sourceLanguage,
                targetLanguage: currentProject.targetLanguage,
                speakerTag: segment.speakerTag,
                previousContext: segmentIndex > 0 ? segments[segmentIndex - 1].text : undefined,
                nextContext: segmentIndex < segments.length - 1 ? segments[segmentIndex + 1].text : undefined,
            });

            const latestTranslations = getLatestTranslations();
            setTranslations(Object.values({
                ...latestTranslations,
                [segmentId]: { ...result, generatedAudioStatus: undefined },
            }));
            setDirtySegments((previous) => new Set(previous).add(segmentId));
            setUploadMessage('Segment retranslated. Regenerate its audio before export.');
        } catch (error) {
            console.error('Retranslate failed:', error);
            setUploadMessage(mapUserFacingError(error, 'Unable to retranslate this segment.'));
        } finally {
            clearBusyState(segmentId);
        }
    }, [clearBusyState, closeActionMenu, currentProject, getLatestTranslations, segments, setDirtySegments, setTranslations, setUploadMessage]);

    const handleSynthesizeSegment = useCallback(async (segmentId: string) => {
        const translation = translations[segmentId];
        if (!translation?.id) return;

        setSegmentBusy((previous) => ({ ...previous, [segmentId]: 'synthesizing' }));
        closeActionMenu();

        try {
            await projectService.synthesizeSegment(translation.id);
            const latestTranslations = getLatestTranslations();
            const latestTranslation = latestTranslations[segmentId] ?? translation;
            setTranslations(Object.values({
                ...latestTranslations,
                [segmentId]: { ...latestTranslation, generatedAudioStatus: 'ready' },
            }));
            setUploadMessage('Segment audio regenerated successfully.');
        } catch (error) {
            console.error('Synthesize segment failed:', error);
            setUploadMessage(mapUserFacingError(error, 'Unable to regenerate audio for this segment.'));
        } finally {
            clearBusyState(segmentId);
        }
    }, [clearBusyState, closeActionMenu, getLatestTranslations, setTranslations, setUploadMessage, translations]);

    const handleResetTranslation = useCallback((segmentId: string) => {
        const original = originalTranslations[segmentId];
        if (original !== undefined) {
            updateTranslationText(segmentId, original);
            setDirtySegments((previous) => {
                const next = new Set(previous);
                next.delete(segmentId);
                return next;
            });
        }
        closeActionMenu();
    }, [closeActionMenu, originalTranslations, setDirtySegments, updateTranslationText]);

    useEffect(() => {
        if (!activeActionMenu) return;

        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                closeActionMenu();
            }
        };
        const handlePointerDown = (event: PointerEvent) => {
            const activeContainer = actionMenuContainersRef.current[activeActionMenu];
            if (activeContainer && event.target instanceof Node && activeContainer.contains(event.target)) {
                return;
            }
            closeActionMenu();
        };

        window.addEventListener('keydown', handleEscape);
        window.addEventListener('pointerdown', handlePointerDown, true);
        return () => {
            window.removeEventListener('keydown', handleEscape);
            window.removeEventListener('pointerdown', handlePointerDown, true);
        };
    }, [activeActionMenu, closeActionMenu]);

    return {
        activeActionMenu,
        closeActionMenu,
        handleResetTranslation,
        handleRetranslateSegment,
        handleSynthesizeSegment,
        registerActionMenuContainer,
        segmentBusy,
        toggleActionMenu,
    };
}
