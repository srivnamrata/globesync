'use client';

import React from 'react';
import { TranscriptSegment } from '../../store/mediaStore';

interface VideoTrackProps {
  segments: TranscriptSegment[];
  zoomLevel: number;
  scrollLeft: number;
}

export const VideoTrack: React.FC<VideoTrackProps> = ({
  segments,
  zoomLevel,
  scrollLeft,
}) => {
  return (
    <div className="h-12 bg-slate-900/40 border-b border-slate-800 relative overflow-hidden select-none">
      <div
        className="absolute inset-y-0 left-0"
        style={{ transform: `translateX(-${scrollLeft}px)` }}
      >
        {segments.map((seg) => {
          const width = seg.durationSeconds * zoomLevel;
          const left = seg.startTimeSeconds * zoomLevel;
          return (
            <div
              key={seg.id}
              className="absolute top-1 bottom-1 border-r border-indigo-950 bg-indigo-950/20 rounded-md p-1.5 flex items-center overflow-hidden"
              style={{ left: `${left}px`, width: `${width}px` }}
            >
              <div className="flex gap-2 items-center">
                <span className="text-[10px] bg-indigo-900/60 text-indigo-300 font-bold px-1.5 rounded-sm whitespace-nowrap uppercase tracking-wider">
                  {seg.speakerTag}
                </span>
                <span className="text-[10px] text-slate-400 truncate max-w-[120px]">
                  {seg.text}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
export default VideoTrack;
