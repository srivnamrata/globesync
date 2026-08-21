'use client';

import React, { useRef, useEffect } from 'react';
import { WaveformData, generatePeaks } from '../../utils/waveformProcessing';

interface WaveformCanvasProps {
  data: WaveformData | null;
  viewStart: number;
  viewEnd: number;
  width: number;
  height: number;
}

export const WaveformCanvas: React.FC<WaveformCanvasProps> = ({
  data,
  viewStart,
  viewEnd,
  width,
  height,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    if (!data) {
      // Draw flat mock audio line if no data is provided
      ctx.strokeStyle = '#475569';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      return;
    }

    const peaks = generatePeaks(data, width);
    const midY = height / 2;

    ctx.fillStyle = '#38bdf8'; // Mono Cyan highlight
    ctx.beginPath();

    for (let x = 0; x < width; x++) {
      const peak = peaks[x] || 0.05;
      const barHeight = peak * (height * 0.45);
      
      // Draw symmetrical bars centered vertically
      ctx.fillRect(x, midY - barHeight, 1.5, barHeight * 2);
    }
  }, [data, viewStart, viewEnd, width, height]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className="w-full h-full bg-slate-950/40 rounded-lg"
    />
  );
};
export default WaveformCanvas;
