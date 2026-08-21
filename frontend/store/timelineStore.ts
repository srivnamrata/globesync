import { create } from 'zustand';

interface TimelineState {
  currentTimeSeconds: number;
  isPlaying: boolean;
  zoomLevel: number; // Pixels per second (e.g. 50 to 500)
  selectedSegmentId: string | null;
  setCurrentTimeSeconds: (time: number) => void;
  setPlaying: (isPlaying: boolean) => void;
  setZoomLevel: (zoomLevel: number) => void;
  setSelectedSegmentId: (id: string | null) => void;
}

export const useTimelineStore = create<TimelineState>((set) => ({
  currentTimeSeconds: 0.0,
  isPlaying: false,
  zoomLevel: 100,
  selectedSegmentId: null,

  setCurrentTimeSeconds: (time) => set({ currentTimeSeconds: Math.max(0, time) }),
  setPlaying: (isPlaying) => set({ isPlaying }),
  setZoomLevel: (zoomLevel) => set({ zoomLevel: Math.max(10, Math.min(1000, zoomLevel)) }),
  setSelectedSegmentId: (id) => set({ selectedSegmentId: id }),
}));
