'use client';

import React, { useRef, MouseEvent } from 'react';

interface ScrubberProps {
  currentTimeSeconds: number;
  durationSeconds: number;
  zoomLevel: number;
  scrollLeft: number;
  onScrub: (seconds: number) => void;
}

export const Scrubber: React.FC<ScrubberProps> = ({
  currentTimeSeconds,
  durationSeconds,
  zoomLevel,
  scrollLeft,
  onScrub,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playheadX = currentTimeSeconds * zoomLevel;

  const handleMouseDown = (e: MouseEvent<HTMLDivElement>) => {
    e.preventDefault();

    const updatePosition = (clientX: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const relativeX = clientX - rect.left + scrollLeft;
      const seconds = Math.min(durationSeconds, Math.max(0, relativeX / zoomLevel));
      onScrub(seconds);
    };

    updatePosition(e.clientX);

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      updatePosition(moveEvent.clientX);
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 z-20 pointer-events-none cursor-ew-resize"
      style={{ pointerEvents: 'auto' }}
      onMouseDown={handleMouseDown}
    >
      <div
        className="absolute top-0 bottom-0 border-l-2 border-red-500 pointer-events-none"
        style={{ left: `${playheadX - scrollLeft}px` }}
      >
        <div className="w-3 h-3 bg-red-500 rounded-full -ml-[5px] -mt-1 shadow-md shadow-red-500/50" />
      </div>
    </div>
  );
};
export default Scrubber;
