'use client';

import React, { useState } from 'react';
import { TranscriptSegment } from '../../store/transcriptStore';
import { useWordTiming } from '../../hooks/useWordTiming';

interface WordTimingControlProps {
  segment: TranscriptSegment | null;
}

export const WordTimingControl: React.FC<WordTimingControlProps> = ({ segment }) => {
  const { adjustTimingPrecision } = useWordTiming();
  const [selectedWordIndex, setSelectedWordIndex] = useState<number | null>(null);

  if (!segment || !segment.words || segment.words.length === 0) {
    return (
      <div className="h-20 bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-center text-slate-500 text-xs select-none">
        Select a segment to inspect word-level timestamp alignments (±10ms).
      </div>
    );
  }

  const selectedWord = selectedWordIndex !== null ? segment.words[selectedWordIndex] : null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3 shadow-lg select-none">
      <div className="flex justify-between items-center pb-2 border-b border-slate-800">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Word-Level Timestamps</h4>
        {selectedWord && (
          <span className="text-xs text-indigo-400 font-mono">
            Selected: &quot;{selectedWord.text}&quot; ({selectedWord.start_time.toFixed(2)}s - {selectedWord.end_time.toFixed(2)}s)
          </span>
        )}
      </div>

      {/* Render clickable word spans */}
      <div className="flex flex-wrap gap-2 py-1">
        {segment.words.map((w, idx) => {
          const isWordSelected = idx === selectedWordIndex;
          return (
            <button
              key={idx}
              onClick={() => setSelectedWordIndex(idx)}
              className={`text-xs px-2.5 py-1 rounded-md font-mono border transition ${
                isWordSelected
                  ? 'bg-indigo-600 border-indigo-500 text-white font-semibold'
                  : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
              }`}
            >
              {w.text}
            </button>
          );
        })}
      </div>

      {/* Adjust offsets by ±10ms */}
      {selectedWordIndex !== null && selectedWord && (
        <div className="flex items-center gap-6 bg-slate-950/40 p-3 rounded-lg border border-slate-850">
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 font-medium">Start:</span>
            <button
              onClick={() => adjustTimingPrecision(segment.id, selectedWordIndex, 'start_time', -0.01)}
              className="bg-slate-800 hover:bg-slate-700 px-2 py-0.5 rounded text-xs"
            >
              -10ms
            </button>
            <span className="text-xs font-mono font-bold text-slate-200">{selectedWord.start_time.toFixed(2)}s</span>
            <button
              onClick={() => adjustTimingPrecision(segment.id, selectedWordIndex, 'start_time', 0.01)}
              className="bg-slate-800 hover:bg-slate-700 px-2 py-0.5 rounded text-xs"
            >
              +10ms
            </button>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 font-medium">End:</span>
            <button
              onClick={() => adjustTimingPrecision(segment.id, selectedWordIndex, 'end_time', -0.01)}
              className="bg-slate-800 hover:bg-slate-700 px-2 py-0.5 rounded text-xs"
            >
              -10ms
            </button>
            <span className="text-xs font-mono font-bold text-slate-200">{selectedWord.end_time.toFixed(2)}s</span>
            <button
              onClick={() => adjustTimingPrecision(segment.id, selectedWordIndex, 'end_time', 0.01)}
              className="bg-slate-800 hover:bg-slate-700 px-2 py-0.5 rounded text-xs"
            >
              +10ms
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
export default WordTimingControl;
