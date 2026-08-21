import { useTranscriptStore } from '../store/transcriptStore';

export function useWordTiming() {
  const store = useTranscriptStore();

  const adjustTimingPrecision = (
    segmentId: string,
    wordIndex: number,
    field: 'start_time' | 'end_time',
    deltaSeconds: number
  ) => {
    const seg = store.segments.find((s) => s.id === segmentId);
    if (!seg) return;

    const word = seg.words[wordIndex];
    if (!word) return;

    let nextStart = word.start_time;
    let nextEnd = word.end_time;

    if (field === 'start_time') {
      nextStart = Math.max(0.0, Number((word.start_time + deltaSeconds).toFixed(3)));
      // Ensure start time doesn't cross end time
      if (nextStart >= nextEnd) nextStart = nextEnd - 0.01;
    } else {
      nextEnd = Number((word.end_time + deltaSeconds).toFixed(3));
      if (nextEnd <= nextStart) nextEnd = nextStart + 0.01;
    }

    store.updateWordTiming(segmentId, wordIndex, nextStart, nextEnd);
  };

  return {
    adjustTimingPrecision,
  };
}
