'use client';

import React from 'react';
import { TranscriptSegment } from '../../store/transcriptStore';

interface SegmentMenuProps {
  segment: TranscriptSegment | null;
  onSplit: (id: string, index: number) => void;
  onMerge: (firstId: string, secondId: string) => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
  onToggleLock: (id: string, locked: boolean) => void;
}

export const SegmentMenu: React.FC<SegmentMenuProps> = ({
  segment,
  onSplit,
  onMerge,
  onDelete,
  onDuplicate,
  onToggleLock,
}) => {
  if (!segment) return null;

  return (
    <div className="flex gap-2 p-2 bg-slate-900 border border-slate-800 rounded-lg justify-end text-xs">
      <button
        onClick={() => onToggleLock(segment.id, !segment.locked)}
        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
      >
        {segment.locked ? 'Unlock' : 'Lock'}
      </button>

      <button
        onClick={() => onDuplicate(segment.id)}
        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
      >
        Duplicate
      </button>

      <button
        onClick={() => onSplit(segment.id, Math.floor(segment.words.length / 2))}
        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
        disabled={segment.words.length <= 1}
      >
        Split (Center)
      </button>

      <button
        onClick={() => onDelete(segment.id)}
        className="px-2.5 py-1 rounded bg-red-950 hover:bg-red-900 text-red-400 border border-red-900"
      >
        Delete
      </button>
    </div>
  );
};
export default SegmentMenu;
