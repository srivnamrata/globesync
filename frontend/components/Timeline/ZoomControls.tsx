'use client';

import React from 'react';

interface ZoomControlsProps {
  zoomLevel: number;
  setZoomLevel: (zoom: number) => void;
  onFit: () => void;
}

export const ZoomControls: React.FC<ZoomControlsProps> = ({
  zoomLevel,
  setZoomLevel,
  onFit,
}) => {
  return (
    <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs select-none">
      <button
        onClick={() => setZoomLevel(zoomLevel - 15)}
        className="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-800 text-slate-300 font-bold transition"
        title="Zoom Out"
      >
        -
      </button>
      <span className="px-1.5 font-mono text-[10px] text-slate-400 min-w-[32px] text-center">
        {zoomLevel}%
      </span>
      <button
        onClick={() => setZoomLevel(zoomLevel + 15)}
        className="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-800 text-slate-300 font-bold transition"
        title="Zoom In"
      >
        +
      </button>
      <div className="border-l border-slate-800 h-4 mx-1" />
      <button
        onClick={onFit}
        className="px-2.5 h-6 flex items-center justify-center rounded hover:bg-slate-800 text-slate-300 transition"
        title="Fit View to Window"
      >
        Fit
      </button>
    </div>
  );
};
export default ZoomControls;
