'use client';

import React from 'react';
import { formatTimecode } from '../../utils/timelineCalculations';

interface TimelineHeaderProps {
  durationSeconds: number;
  zoomLevel: number;
  scrollLeft: number;
}

export const TimelineHeader: React.FC<TimelineHeaderProps> = ({
  durationSeconds,
  zoomLevel,
  scrollLeft,
}) => {
  const width = durationSeconds * zoomLevel;
  const majorTickInterval = 1.0; // seconds
  const minorTickInterval = 0.1; // seconds

  const ticks: React.ReactNode[] = [];
  const totalTicks = Math.ceil(durationSeconds / minorTickInterval);

  for (let i = 0; i <= totalTicks; i++) {
    const time = i * minorTickInterval;
    const xPos = time * zoomLevel;
    const isMajor = i % 10 === 0;

    if (isMajor) {
      ticks.push(
        <div
          key={`major-${i}`}
          className="absolute border-l border-slate-700 h-5"
          style={{ left: `${xPos}px` }}
        >
          <span className="absolute left-1 top-1 text-[10px] font-mono text-slate-500 whitespace-nowrap">
            {formatTimecode(time).split('.')[0]}
          </span>
        </div>
      );
    } else if (zoomLevel > 150) {
      ticks.push(
        <div
          key={`minor-${i}`}
          className="absolute border-l border-slate-800 h-2.5 top-2.5"
          style={{ left: `${xPos}px` }}
        />
      );
    }
  }

  return (
    <div className="h-8 bg-slate-900 border-b border-slate-800 relative select-none w-full overflow-hidden">
      <div
        className="absolute inset-0"
        style={{ width: `${width}px`, transform: `translateX(-${scrollLeft}px)` }}
      >
        {ticks}
      </div>
    </div>
  );
};
export default TimelineHeader;
