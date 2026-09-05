export function sanitizeSegmentText(text: string): string {
  // Strips double whitespace, removes unsupported layout tabs/newlines
  return text.trim().replace(/\s+/g, ' ');
}

export function generateSrtTimings(
  startSeconds: number,
  endSeconds: number
): string {
  const format = (sec: number) => {
    const totalMilliseconds = Math.round(sec * 1000);
    const hrs = Math.floor(totalMilliseconds / 3_600_000);
    const mins = Math.floor((totalMilliseconds % 3_600_000) / 60_000);
    const secs = Math.floor((totalMilliseconds % 60_000) / 1000);
    const ms = totalMilliseconds % 1000;
    const pad = (n: number, l: number) => n.toString().padStart(l, '0');
    return `${pad(hrs, 2)}:${pad(mins, 2)}:${pad(secs, 2)},${pad(ms, 3)}`;
  };
  return `${format(startSeconds)} --> ${format(endSeconds)}`;
}
