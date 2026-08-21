'use client';

import React from 'react';
import { TranscriptSegment } from '../../store/transcriptStore';
import ConfidenceIndicator from './ConfidenceIndicator';

interface OriginalPaneProps {
  segments: TranscriptSegment[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  fontSize: number;
}

export const OriginalPane: React.FC<OriginalPaneProps> = ({
  segments,
  selectedId,
  onSelect,
  fontSize,
}) => {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ fontSize: `${fontSize}px` }}>
      {segments.map((seg) => {
        const isSelected = seg.id === selectedId;
        return (
          <div
            key={seg.id}
            onClick={() => onSelect(seg.id)}
            className={`p-4 border rounded-xl transition cursor-pointer ${
              isSelected
                ? 'border-indigo-500 bg-indigo-950/10'
                : 'border-slate-800 bg-slate-900/30 hover:border-slate-700'
            }`}
          >
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] bg-slate-800 text-slate-300 font-bold px-2 py-0.5 rounded font-mono uppercase">
                  {seg.speaker}
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  {seg.start_time.toFixed(2)}s - {seg.end_time.toFixed(2)}s
                </span>
              </div>
              <ConfidenceIndicator score={seg.confidence} />
            </div>

            <p className="text-slate-100 leading-relaxed">{seg.original_text}</p>
          </div>
        );
      })}
    </div>
  );
};
export default OriginalPane;
