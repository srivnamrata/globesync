export function sanitizeSegmentText(text: string): string {
  // Strips double whitespace, removes unsupported layout tabs/newlines
  return text.trim().replace(/\s+/g, ' ');
}

export function generateSrtTimings(
  startSeconds: number,
  endSeconds: number
): string {
  const format = (sec: number) => {
    const hrs = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const secs = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 1000);
    const pad = (n: number, l: number) => n.toString().padStart(l, '0');
    return `${pad(hrs, 2)}:${pad(mins, 2)}:${pad(secs, 2)},${pad(ms, 3)}`;
  };
  return `${format(startSeconds)} --> ${format(endSeconds)}`;
}
