'use client';

import React from 'react';
import { TranscriptSegment } from '../../store/transcriptStore';

interface TranslatedPaneProps {
  segments: TranscriptSegment[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onTextChange: (id: string, text: string) => void;
  fontSize: number;
}

export const TranslatedPane: React.FC<TranslatedPaneProps> = ({
  segments,
  selectedId,
  onSelect,
  onTextChange,
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
            className={`p-4 border rounded-xl transition ${
              isSelected
                ? 'border-indigo-500 bg-indigo-950/10'
                : 'border-slate-800 bg-slate-900/30'
            }`}
          >
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-slate-500 font-mono">
                Duration: {(seg.end_time - seg.start_time).toFixed(2)}s
              </span>
              <span className="text-[10px] text-slate-500">
                Chars: {seg.translated_text.length}
              </span>
            </div>

            <textarea
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-slate-700 resize-none h-16"
              value={seg.translated_text}
              onChange={(e) => onTextChange(seg.id, e.target.value)}
              disabled={seg.locked}
              placeholder={seg.locked ? "🔓 Segment locked from editing" : "Translated translation text..."}
              spellCheck={true}
            />
          </div>
        );
      })}
    </div>
  );
};
export default TranslatedPane;
