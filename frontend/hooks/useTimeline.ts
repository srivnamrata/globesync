import { useTimelineStore } from '../store/timelineStore';

export function useTimeline() {
  const timeline = useTimelineStore();

  const secondsToPixels = (seconds: number): number => {
    return seconds * timeline.zoomLevel;
  };

  const pixelsToSeconds = (pixels: number): number => {
    return pixels / timeline.zoomLevel;
  };

  const formatTimecode = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 100);

    const pad = (num: number) => num.toString().padStart(2, '0');
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}.${pad(ms)}`;
  };

  return {
    currentTimeSeconds: timeline.currentTimeSeconds,
    isPlaying: timeline.isPlaying,
    zoomLevel: timeline.zoomLevel,
    selectedSegmentId: timeline.selectedSegmentId,
    setCurrentTimeSeconds: timeline.setCurrentTimeSeconds,
    setPlaying: timeline.setPlaying,
    setZoomLevel: timeline.setZoomLevel,
    setSelectedSegmentId: timeline.setSelectedSegmentId,
    secondsToPixels,
    pixelsToSeconds,
    formatTimecode,
  };
}
