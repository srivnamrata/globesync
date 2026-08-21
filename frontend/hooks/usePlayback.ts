import { useEffect, useCallback, useRef } from 'react';
import { useTimelineStore } from '../store/timelineStore';

export function usePlayback(audioDuration: number) {
  const isPlaying = useTimelineStore((s) => s.isPlaying);
  const setPlaying = useTimelineStore((s) => s.setPlaying);
  const currentTime = useTimelineStore((s) => s.currentTimeSeconds);
  const setCurrentTime = useTimelineStore((s) => s.setCurrentTimeSeconds);

  const playbackRateRef = useRef<number>(1.0);
  const frameIntervalRef = useRef<number | null>(null);

  const togglePlay = useCallback(() => {
    setPlaying(!isPlaying);
  }, [isPlaying, setPlaying]);

  const stepFrames = useCallback(
    (direction: 'forward' | 'backward', stepSec: number = 0.04) => {
      // 0.04s ~ 25 FPS frame step
      const delta = direction === 'forward' ? stepSec : -stepSec;
      setCurrentTime(Math.min(audioDuration, Math.max(0, currentTime + delta)));
    },
    [currentTime, setCurrentTime, audioDuration]
  );

  // Playback timer ticker loop (60 FPS rendering schedule)
  useEffect(() => {
    if (!isPlaying) {
      if (frameIntervalRef.current) {
        cancelAnimationFrame(frameIntervalRef.current);
        frameIntervalRef.current = null;
      }
      return;
    }

    let lastTimestamp = performance.now();

    const tick = () => {
      const now = performance.now();
      const deltaSec = (now - lastTimestamp) / 1000.0;
      lastTimestamp = now;

      const prevTime = useTimelineStore.getState().currentTimeSeconds;
      const nextTime = (() => {
        const updatedTime = prevTime + deltaSec * playbackRateRef.current;
        if (updatedTime >= audioDuration) {
          setPlaying(false);
          return audioDuration;
        }
        return updatedTime;
      })();
      setCurrentTime(nextTime);

      frameIntervalRef.current = requestAnimationFrame(tick);
    };

    frameIntervalRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameIntervalRef.current) {
        cancelAnimationFrame(frameIntervalRef.current);
      }
    };
  }, [isPlaying, audioDuration, setPlaying, setCurrentTime]);

  // Keyboard Shortcuts Hook
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) {
        return; // Ignore inside input fields
      }

      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        stepFrames('forward');
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        stepFrames('backward');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [togglePlay, stepFrames]);

  return {
    isPlaying,
    currentTime,
    togglePlay,
    stepFrames,
    setPlaybackRate: (rate: number) => {
      playbackRateRef.current = rate;
    },
  };
}
