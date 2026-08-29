import { useEffect, useRef } from 'react';
import { useProjectStore } from '../store/projectStore';
import { useMediaStore } from '../store/mediaStore';
import { useTranslationStore } from '../store/translationStore';
import { storageService, HeygenXFile } from '../services/storageService';

export function useProjectAutoSave(syncDraft?: () => Promise<void>) {
  const currentProject = useProjectStore((s) => s.currentProject);
  const segments = useMediaStore((s) => s.segments);
  const translations = useTranslationStore((s) => s.translations);
  const autoSaveIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Stop previous interval if project changes
    if (autoSaveIntervalRef.current) {
      clearInterval(autoSaveIntervalRef.current);
    }

    if (!currentProject) return;

    // Schedule auto-save every 30 seconds
    autoSaveIntervalRef.current = setInterval(async () => {
      try {
        if (syncDraft) {
          await syncDraft();
          console.log(`Auto-saved project: ${currentProject.name} to backend and IndexedDB.`);
          return;
        }

        const fileData: HeygenXFile = {
          version: '1.2.0',
          projectMetadata: {
            id: currentProject.id,
            name: currentProject.name,
            sourceLanguage: currentProject.sourceLanguage,
            targetLanguage: currentProject.targetLanguage,
            createdAt: currentProject.createdAt,
            updatedAt: new Date().toISOString(),
          },
          mediaReferences: {
            videoFilename: currentProject.originalVideoUrl || 'source_video.mp4',
            durationSeconds: segments.reduce((acc, s) => Math.max(acc, s.endTimeSeconds), 0),
            originalTranscriptSegments: segments,
            transcriptId: currentProject.transcriptId,
            mediaId: currentProject.mediaId,
          },
          translations: Object.values(translations),
        };

        await storageService.saveDraft(fileData);
        console.log(`Auto-saved project: ${currentProject.name} to IndexedDB.`);
      } catch (err) {
        console.error('Auto-save failed:', err);
      }
    }, 30000);

    return () => {
      if (autoSaveIntervalRef.current) {
        clearInterval(autoSaveIntervalRef.current);
      }
    };
  }, [currentProject, segments, syncDraft, translations]);
}
  