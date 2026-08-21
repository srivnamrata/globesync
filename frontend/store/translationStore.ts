import { create } from 'zustand';

export interface TranslatedSegment {
  id: string;
  transcriptSegmentId: string;
  translatedText: string;
  originalDurationMs: number;
  estimatedDurationMs: number;
  durationRatio: number;
  speedAdjustmentFactor: number;
  qualityScore: number;
  status: 'pending' | 'completed' | 'failed';
}

interface TranslationState {
  translations: Record<string, TranslatedSegment>; // Keyed by transcriptSegmentId
  targetLanguage: string;
  isLoading: boolean;
  setTranslations: (translations: TranslatedSegment[]) => void;
  setTargetLanguage: (targetLanguage: string) => void;
  updateTranslationText: (segmentId: string, text: string) => void;
  setLoading: (isLoading: boolean) => void;
}

export const useTranslationStore = create<TranslationState>((set) => ({
  translations: {},
  targetLanguage: 'es',
  isLoading: false,

  setTranslations: (translations) => set(() => {
    const map: Record<string, TranslatedSegment> = {};
    translations.forEach((t) => {
      map[t.transcriptSegmentId] = t;
    });
    return { translations: map };
  }),
  setTargetLanguage: (targetLanguage) => set({ targetLanguage }),
  updateTranslationText: (segmentId, text) => set((state) => {
    const target = state.translations[segmentId];
    if (!target) return {};
    return {
      translations: {
        ...state.translations,
        [segmentId]: { ...target, translatedText: text }
      }
    };
  }),
  setLoading: (isLoading) => set({ isLoading }),
}));
