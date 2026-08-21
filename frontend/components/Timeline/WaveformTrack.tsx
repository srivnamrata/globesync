'use client';

import React from 'react';
import WaveformCanvas from '../WaveformRenderer/WaveformCanvas';
import { WaveformData } from '../../utils/waveformProcessing';

interface WaveformTrackProps {
  data: WaveformData | null;
  durationSeconds: number;
  zoomLevel: number;
  scrollLeft: number;
}

export const WaveformTrack: React.FC<WaveformTrackProps> = ({
  data,
  durationSeconds,
  zoomLevel,
  scrollLeft,
}) => {
  const width = durationSeconds * zoomLevel;
  return (
    <div className="h-20 bg-slate-950/20 border-b border-slate-800 relative overflow-hidden">
      <div
        className="absolute inset-y-0 left-0 h-full"
        style={{ width: `${width}px`, transform: `translateX(-${scrollLeft}px)` }}
      >
        <WaveformCanvas
          data={data}
          viewStart={scrollLeft / zoomLevel}
          viewEnd={(scrollLeft + 1200) / zoomLevel}
          width={width}
          height={80}
        />
      </div>
    </div>
  );
};
export default WaveformTrack;
