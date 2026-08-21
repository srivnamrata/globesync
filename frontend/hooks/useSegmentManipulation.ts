import { useCallback } from 'react';
import { useMediaStore, TranscriptSegment } from '../store/mediaStore';
import { useTimelineStore } from '../store/timelineStore';
import { snapToGrid } from '../utils/timelineCalculations';

export function useSegmentManipulation() {
  const segments = useMediaStore((s) => s.segments);
  const setSegments = useMediaStore((s) => s.setSegments);
  const selectedId = useTimelineStore((s) => s.selectedSegmentId);
  const setSelectedId = useTimelineStore((s) => s.setSelectedSegmentId);

  const moveSegment = useCallback(
    (segmentId: string, newStartSeconds: number) => {
      const snappedStart = snapToGrid(newStartSeconds, 0.05);
      const updated = segments.map((seg) => {
        if (seg.id === segmentId) {
          const duration = seg.endTimeSeconds - seg.startTimeSeconds;
          return {
            ...seg,
            startTimeSeconds: snappedStart,
            endTimeSeconds: snappedStart + duration,
          };
        }
        return seg;
      });
      setSegments(updated);
    },
    [segments, setSegments]
  );

  const resizeSegment = useCallback(
    (segmentId: string, edge: 'start' | 'end', newTimeSeconds: number) => {
      const snappedTime = snapToGrid(newTimeSeconds, 0.05);
      const updated = segments.map((seg) => {
        if (seg.id === segmentId) {
          if (edge === 'start') {
            const nextStart = Math.min(seg.endTimeSeconds - 0.2, snappedTime);
            return {
              ...seg,
              startTimeSeconds: nextStart,
              durationSeconds: seg.endTimeSeconds - nextStart,
            };
          } else {
            const nextEnd = Math.max(seg.startTimeSeconds + 0.2, snappedTime);
            return {
              ...seg,
              endTimeSeconds: nextEnd,
              durationSeconds: nextEnd - seg.startTimeSeconds,
            };
          }
        }
        return seg;
      });
      setSegments(updated);
    },
    [segments, setSegments]
  );

  return {
    selectedSegmentId: selectedId,
    selectSegment: setSelectedId,
    moveSegment,
    resizeSegment,
  };
}
