import { useState } from 'react';
import { useTranscriptStore } from '../store/transcriptStore';
import { projectService } from '../services/projectService';

export function useReTranslation() {
  const store = useTranscriptStore();
  const [isTranslating, setIsTranslating] = useState(false);
  const [showOverrideConfirm, setShowOverrideConfirm] = useState(false);
  const [pendingTextChange, setPendingTextChange] = useState<{ segmentId: string; text: string } | null>(null);

  const requestReTranslation = async (segmentId: string, sourceText: string, targetLang: string) => {
    setIsTranslating(true);
    try {
      // In a real application, call the backend GPT-4o translation service
      // For this implementation, simulate translation delay and return suggested translation text
      await new Promise((resolve) => setTimeout(resolve, 800));
      const simulatedTranslation = `[Translated] ${sourceText}`;
      
      // Update target segment translation text
      store.updateSegmentText(segmentId, 'translated', simulatedTranslation);
    } catch (err) {
      console.error('Re-translation request failed:', err);
    } finally {
      setIsTranslating(false);
    }
  };

  const queueManualOverride = (segmentId: string, text: string) => {
    setPendingTextChange({ segmentId, text });
    setShowOverrideConfirm(true);
  };

  const confirmOverride = () => {
    if (pendingTextChange) {
      store.updateSegmentText(pendingTextChange.segmentId, 'translated', pendingTextChange.text);
      setPendingTextChange(null);
    }
    setShowOverrideConfirm(false);
  };

  return {
    isTranslating,
    showOverrideConfirm,
    setShowOverrideConfirm,
    requestReTranslation,
    queueManualOverride,
    confirmOverride,
  };
}
