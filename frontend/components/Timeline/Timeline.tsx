'use client';

import React, { useState, useRef, UIEvent } from 'react';
import TimelineHeader from './TimelineHeader';
import VideoTrack from './VideoTrack';
import WaveformTrack from './WaveformTrack';
import Scrubber from './Scrubber';
import SegmentOverlay from './SegmentOverlay';
import ZoomControls from './ZoomControls';
import { useMediaStore } from '../../store/mediaStore';
import { useTimelineStore } from '../../store/timelineStore';
import { usePlayback } from '../../hooks/usePlayback';
import { useSegmentManipulation } from '../../hooks/useSegmentManipulation';
import { WaveformData } from '../../utils/waveformProcessing';

interface TimelineProps {
  audioData: WaveformData | null;
  durationSeconds: number;
}

export const Timeline: React.FC<TimelineProps> = ({
  audioData,
  durationSeconds,
}) => {
  const [scrollLeft, setScrollLeft] = useState(0);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  const segments = useMediaStore((s) => s.segments);
  const zoomLevel = useTimelineStore((s) => s.zoomLevel);
  const setZoomLevel = useTimelineStore((s) => s.setZoomLevel);
  const currentTime = useTimelineStore((s) => s.currentTimeSeconds);
  const setCurrentTime = useTimelineStore((s) => s.setCurrentTimeSeconds);

  const playback = usePlayback(durationSeconds);
  const manipulation = useSegmentManipulation();

  const handleScroll = (e: UIEvent<HTMLDivElement>) => {
    setScrollLeft(e.currentTarget.scrollLeft);
  };

  const handleFit = () => {
    if (scrollContainerRef.current) {
      const containerWidth = scrollContainerRef.current.clientWidth;
      const fitZoom = Math.floor((containerWidth - 20) / durationSeconds);
      setZoomLevel(Math.max(10, Math.min(500, fitZoom)));
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col h-full select-none shadow-2xl">
      {/* Top controls layout */}
      <div className="h-12 border-b border-slate-800 bg-slate-950/40 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={playback.togglePlay}
            className="w-8 h-8 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center transition text-sm"
          >
            {playback.isPlaying ? '⏸' : '▶'}
          </button>
          <div className="flex gap-1">
            <button
              onClick={() => playback.stepFrames('backward')}
              className="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs flex items-center justify-center"
              title="Step Backward (Left Arrow)"
            >
              &larr;
            </button>
            <button
              onClick={() => playback.stepFrames('forward')}
              className="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs flex items-center justify-center"
              title="Step Forward (Right Arrow)"
            >
              &rarr;
            </button>
          </div>
        </div>

        {/* Center zoom controls */}
        <ZoomControls zoomLevel={zoomLevel} setZoomLevel={setZoomLevel} onFit={handleFit} />
      </div>

      {/* Main Ruler & Tracks Scroll Area */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        {/* Fixed Tick Ruler */}
        <TimelineHeader
          durationSeconds={durationSeconds}
          zoomLevel={zoomLevel}
          scrollLeft={scrollLeft}
        />

        {/* Scrollable Tracks Panel */}
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-x-auto overflow-y-hidden relative select-none"
          onScroll={handleScroll}
        >
          <div
            className="h-full relative"
            style={{ width: `${durationSeconds * zoomLevel}px` }}
          >
            {/* Video Track Component */}
            <VideoTrack
              segments={segments}
              zoomLevel={zoomLevel}
              scrollLeft={0} // Handled inside parent translate transform
            />

            {/* Audio Waveform Canvas Component */}
            <WaveformTrack
              data={audioData}
              durationSeconds={durationSeconds}
              zoomLevel={zoomLevel}
              scrollLeft={0}
            />

            {/* Interactive Segment Drag Overlay */}
            <SegmentOverlay
              segments={segments}
              zoomLevel={zoomLevel}
              scrollLeft={0}
              selectedSegmentId={manipulation.selectedSegmentId}
              onSelect={manipulation.selectSegment}
              onMove={manipulation.moveSegment}
              onResize={manipulation.resizeSegment}
            />

            {/* Draggable Playhead Scrubber Layer */}
            <Scrubber
              currentTimeSeconds={currentTime}
              durationSeconds={durationSeconds}
              zoomLevel={zoomLevel}
              scrollLeft={0}
              onScrub={setCurrentTime}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
export default Timeline;
