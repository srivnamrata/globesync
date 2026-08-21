export interface WaveformData {
  channels: Float32Array[];
  sampleRate: number;
  duration: number;
}

export function generatePeaks(
  data: WaveformData,
  width: number
): number[] {
  const peaks: number[] = [];
  const channel = data.channels[0]; // Extract mono channel
  if (!channel) return peaks;

  const step = Math.floor(channel.length / width);
  for (let i = 0; i < width; i++) {
    const start = i * step;
    let max = 0;
    for (let j = 0; j < step; j++) {
      const val = Math.abs(channel[start + j] || 0);
      if (val > max) max = val;
    }
    peaks.push(max);
  }

  // Normalize peaks
  const maxPeak = Math.max(...peaks) || 1.0;
  return peaks.map((p) => p / maxPeak);
}
