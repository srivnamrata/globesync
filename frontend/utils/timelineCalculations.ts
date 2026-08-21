export function secondsToPixels(seconds: number, zoomLevel: number): number {
  return seconds * zoomLevel;
}

export function pixelsToSeconds(pixels: number, zoomLevel: number): number {
  return pixels / zoomLevel;
}

export function formatTimecode(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);

  const pad = (num: number) => num.toString().padStart(2, '0');
  return `${pad(hrs)}:${pad(mins)}:${pad(secs)}.${pad(ms)}`;
}

export function snapToGrid(seconds: number, interval: number = 0.1): number {
  return Math.round(seconds / interval) * interval;
}
