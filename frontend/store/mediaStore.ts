import { create } from 'zustand';

export interface VideoMetadata {
  width: number;
  height: number;
  fps: number;
  durationSeconds: number;
  filename: string;
  filesizeBytes: number;
}

export interface TranscriptSegment {
  id: string;
  sequenceOrder: number;
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  speakerTag: string;
  text: string;
  confidence: number;
}

interface MediaState {
  metadata: VideoMetadata | null;
  segments: TranscriptSegment[];
  isLoading: boolean;
  setMetadata: (metadata: VideoMetadata) => void;
  setSegments: (segments: TranscriptSegment[]) => void;
  updateSegmentText: (segmentId: string, text: string) => void;
  splitSegment: (segmentId: string, splitPointSeconds: number, firstText: string, secondText: string) => void;
  setLoading: (isLoading: boolean) => void;
}

export const useMediaStore = create<MediaState>((set) => ({
  metadata: null,
  segments: [],
  isLoading: false,

  setMetadata: (metadata) => set({ metadata }),
  setSegments: (segments) => set({ segments: segments.sort((a, b) => a.sequenceOrder - b.sequenceOrder) }),
  updateSegmentText: (segmentId, text) => set((state) => ({
    segments: state.segments.map((seg) =>
      seg.id === segmentId ? { ...seg, text } : seg
    )
  })),
  splitSegment: (segmentId, splitPointSeconds, firstText, secondText) => set((state) => {
    const targetIdx = state.segments.findIndex((s) => s.id === segmentId);
    if (targetIdx === -1) return {};

    const target = state.segments[targetIdx];
    const firstSeg: TranscriptSegment = {
      ...target,
      id: `${target.id}_split1`,
      endTimeSeconds: splitPointSeconds,
      durationSeconds: splitPointSeconds - target.startTimeSeconds,
      text: firstText,
    };

    const secondSeg: TranscriptSegment = {
      ...target,
      id: `${target.id}_split2`,
      startTimeSeconds: splitPointSeconds,
      durationSeconds: target.endTimeSeconds - splitPointSeconds,
      text: secondText,
      sequenceOrder: target.sequenceOrder + 1,
    };

    const updated = [...state.segments];
    // Increment sequence orders for all subsequent segments
    for (let i = targetIdx + 1; i < updated.length; i++) {
      updated[i] = { ...updated[i], sequenceOrder: updated[i].sequenceOrder + 1 };
    }

    updated.splice(targetIdx, 1, firstSeg, secondSeg);
    return { segments: updated };
  }),
  setLoading: (isLoading) => set({ isLoading }),
}));
