'use client';

import React from 'react';

interface ConfidenceIndicatorProps {
  score: number; // 0.0 to 1.0
}

export const ConfidenceIndicator: React.FC<ConfidenceIndicatorProps> = ({ score }) => {
  const percent = Math.round(score * 100);
  let colorClass = 'bg-red-950 text-red-400 border-red-900';
  
  if (percent >= 90) {
    colorClass = 'bg-green-950 text-green-400 border-green-900';
  } else if (percent >= 70) {
    colorClass = 'bg-yellow-950 text-yellow-400 border-yellow-900';
  }

  return (
    <div
      className={`text-[10px] font-bold border px-1.5 py-0.5 rounded flex items-center gap-1 select-none ${colorClass}`}
      title={`Diarization confidence: ${percent}%`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {percent}%
    </div>
  );
};
export default ConfidenceIndicator;
