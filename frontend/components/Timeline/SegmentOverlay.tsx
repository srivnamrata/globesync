'use client';

import React, { MouseEvent } from 'react';
import { TranscriptSegment } from '../../store/mediaStore';

interface SegmentOverlayProps {
  segments: TranscriptSegment[];
  zoomLevel: number;
  scrollLeft: number;
  selectedSegmentId: string | null;
  onSelect: (id: string | null) => void;
  onMove: (id: string, newStart: number) => void;
  onResize: (id: string, edge: 'start' | 'end', newTime: number) => void;
}

export const SegmentOverlay: React.FC<SegmentOverlayProps> = ({
  segments,
  zoomLevel,
  scrollLeft,
  selectedSegmentId,
  onSelect,
  onMove,
  onResize,
}) => {
  const handleDragStart = (e: MouseEvent<HTMLDivElement>, seg: TranscriptSegment, type: 'move' | 'left' | 'right') => {
    e.preventDefault();
    e.stopPropagation();

    const startX = e.clientX;
    const initialStart = seg.startTimeSeconds;
    const initialEnd = seg.endTimeSeconds;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaSeconds = deltaX / zoomLevel;

      if (type === 'move') {
        onMove(seg.id, initialStart + deltaSeconds);
      } else if (type === 'left') {
        onResize(seg.id, 'start', initialStart + deltaSeconds);
      } else if (type === 'right') {
        onResize(seg.id, 'end', initialEnd + deltaSeconds);
      }
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
      className="absolute inset-0 pointer-events-none"
      style={{ transform: `translateX(-${scrollLeft}px)` }}
    >
      {segments.map((seg) => {
        const left = seg.startTimeSeconds * zoomLevel;
        const width = seg.durationSeconds * zoomLevel;
        const isSelected = seg.id === selectedSegmentId;

        return (
          <div
            key={seg.id}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(seg.id);
            }}
            className={`absolute top-0 bottom-0 pointer-events-auto border-x select-none flex justify-between ${
              isSelected
                ? 'bg-indigo-500/10 border-indigo-500 z-10'
                : 'bg-transparent border-slate-800 hover:bg-slate-800/10'
            }`}
            style={{ left: `${left}px`, width: `${width}px` }}
          >
            {/* Left Resize Anchor */}
            <div
              className={`w-1.5 h-full cursor-ew-resize hover:bg-indigo-500/80 transition-colors ${
                isSelected ? 'bg-indigo-500/30' : 'bg-transparent'
              }`}
              onMouseDown={(e) => handleDragStart(e, seg, 'left')}
            />

            {/* Middle Drag Body */}
            <div
              className="flex-1 h-full cursor-grab active:cursor-grabbing"
              onMouseDown={(e) => handleDragStart(e, seg, 'move')}
            />

            {/* Right Resize Anchor */}
            <div
              className={`w-1.5 h-full cursor-ew-resize hover:bg-indigo-500/80 transition-colors ${
                isSelected ? 'bg-indigo-500/30' : 'bg-transparent'
              }`}
              onMouseDown={(e) => handleDragStart(e, seg, 'right')}
            />
          </div>
        );
      })}
    </div>
  );
};
export default SegmentOverlay;
