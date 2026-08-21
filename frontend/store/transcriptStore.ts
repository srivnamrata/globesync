import { create } from 'zustand';

export interface WordTiming {
  text: string;
  start_time: number;  // seconds
  end_time: number;
  confidence: number;  // 0-1.0
}

export interface TranscriptSegment {
  id: string;
  original_text: string;
  translated_text: string;
  start_time: number;  // seconds
  end_time: number;
  speaker: string;
  confidence: number;  // 0-1.0
  words: WordTiming[];
  locked: boolean;
  edited: boolean;
}

interface TranscriptStore {
  segments: TranscriptSegment[];
  selectedSegmentId: string | null;
  setSegments: (segments: TranscriptSegment[]) => void;
  setSelectedSegmentId: (id: string | null) => void;
  updateSegmentText: (id: string, field: 'original' | 'translated', text: string) => void;
  updateWordTiming: (segmentId: string, wordIndex: number, start: number, end: number) => void;
  splitSegment: (id: string, wordIndex: number) => void;
  mergeSegments: (firstId: string, secondId: string) => void;
  deleteSegment: (id: string) => void;
  duplicateSegment: (id: string) => void;
  setSegmentLock: (id: string, locked: boolean) => void;
}

export const useTranscriptStore = create<TranscriptStore>((set) => ({
  segments: [],
  selectedSegmentId: null,

  setSegments: (segments) => set({ segments }),
  setSelectedSegmentId: (selectedSegmentId) => set({ selectedSegmentId }),

  updateSegmentText: (id, field, text) => set((state) => ({
    segments: state.segments.map((seg) => {
      if (seg.id === id) {
        if (field === 'original') {
          return { ...seg, original_text: text, edited: true };
        } else {
          return { ...seg, translated_text: text, edited: true };
        }
      }
      return seg;
    })
  })),

  updateWordTiming: (segmentId, wordIndex, start, end) => set((state) => ({
    segments: state.segments.map((seg) => {
      if (seg.id === segmentId) {
        const nextWords = [...seg.words];
        nextWords[wordIndex] = { ...nextWords[wordIndex], start_time: start, end_time: end };
        
        // Re-calculate segment start/end times based on words
        const start_time = Math.min(...nextWords.map((w) => w.start_time));
        const end_time = Math.max(...nextWords.map((w) => w.end_time));

        return { ...seg, words: nextWords, start_time, end_time, edited: true };
      }
      return seg;
    })
  })),

  splitSegment: (id, wordIndex) => set((state) => {
    const idx = state.segments.findIndex((s) => s.id === id);
    if (idx === -1) return {};

    const seg = state.segments[idx];
    if (wordIndex <= 0 || wordIndex >= seg.words.length) return {};

    const leftWords = seg.words.slice(0, wordIndex);
    const rightWords = seg.words.slice(wordIndex);

    const firstSeg: TranscriptSegment = {
      ...seg,
      id: `${seg.id}_s1`,
      words: leftWords,
      start_time: seg.start_time,
      end_time: leftWords[leftWords.length - 1].end_time,
      original_text: leftWords.map((w) => w.text).join(' '),
      translated_text: '', // Requires re-translation
      edited: true,
    };

    const secondSeg: TranscriptSegment = {
      ...seg,
      id: `${seg.id}_s2`,
      words: rightWords,
      start_time: rightWords[0].start_time,
      end_time: seg.end_time,
      original_text: rightWords.map((w) => w.text).join(' '),
      translated_text: '',
      edited: true,
    };

    const updated = [...state.segments];
    updated.splice(idx, 1, firstSeg, secondSeg);
    return { segments: updated };
  }),

  mergeSegments: (firstId, secondId) => set((state) => {
    const idx1 = state.segments.findIndex((s) => s.id === firstId);
    const idx2 = state.segments.findIndex((s) => s.id === secondId);
    if (idx1 === -1 || idx2 === -1) return {};

    const s1 = state.segments[idx1];
    const s2 = state.segments[idx2];

    const merged: TranscriptSegment = {
      ...s1,
      id: `${s1.id}_merged`,
      start_time: s1.start_time,
      end_time: s2.end_time,
      original_text: `${s1.original_text} ${s2.original_text}`,
      translated_text: `${s1.translated_text} ${s2.translated_text}`,
      words: [...s1.words, ...s2.words],
      edited: true,
    };

    const updated = [...state.segments];
    // Remove both and insert merged
    const lowIdx = Math.min(idx1, idx2);
    const highIdx = Math.max(idx1, idx2);
    updated.splice(highIdx, 1);
    updated.splice(lowIdx, 1, merged);
    return { segments: updated };
  }),

  deleteSegment: (id) => set((state) => ({
    segments: state.segments.filter((s) => s.id !== id)
  })),

  duplicateSegment: (id) => set((state) => {
    const idx = state.segments.findIndex((s) => s.id === id);
    if (idx === -1) return {};

    const orig = state.segments[idx];
    const copy: TranscriptSegment = {
      ...orig,
      id: `${orig.id}_copy_${Math.random().toString(36).substring(5)}`,
      start_time: orig.end_time,
      end_time: orig.end_time + (orig.end_time - orig.start_time),
      edited: true,
    };

    const updated = [...state.segments];
    updated.splice(idx + 1, 0, copy);
    return { segments: updated };
  }),

  setSegmentLock: (id, locked) => set((state) => ({
    segments: state.segments.map((s) => s.id === id ? { ...s, locked } : s)
  })),
}));
export default useTranscriptStore;
