import { useTranscriptStore, TranscriptSegment } from '../store/transcriptStore';

export function useTranscriptEditor() {
  const store = useTranscriptStore();

  const getSpeakerStatistics = () => {
    const stats: Record<string, { lineCount: number; totalDurationSec: number }> = {};
    store.segments.forEach((seg) => {
      const dur = seg.end_time - seg.start_time;
      if (!stats[seg.speaker]) {
        stats[seg.speaker] = { lineCount: 0, totalDurationSec: 0 };
      }
      stats[seg.speaker].lineCount += 1;
      stats[seg.speaker].totalDurationSec += dur;
    });
    return stats;
  };

  const renameSpeakerBatch = (oldName: string, newName: string) => {
    const updated = store.segments.map((seg) =>
      seg.speaker === oldName ? { ...seg, speaker: newName, edited: true } : seg
    );
    store.setSegments(updated);
  };

  return {
    segments: store.segments,
    selectedSegmentId: store.selectedSegmentId,
    setSelectedSegmentId: store.setSelectedSegmentId,
    updateSegmentText: store.updateSegmentText,
    splitSegment: store.splitSegment,
    mergeSegments: store.mergeSegments,
    deleteSegment: store.deleteSegment,
    duplicateSegment: store.duplicateSegment,
    setSegmentLock: store.setSegmentLock,
    renameSpeakerBatch,
    getSpeakerStatistics,
  };
}
