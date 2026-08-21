import { snapToGrid, formatTimecode, secondsToPixels, pixelsToSeconds } from '../utils/timelineCalculations';
import { generatePeaks, WaveformData } from '../utils/waveformProcessing';

describe('Timeline Utility Math Calculations', () => {
  test('converts seconds to pixels based on zoom level', () => {
    // 5.5 seconds at 100px/s zoom -> 550px
    const px = secondsToPixels(5.5, 100);
    assert(px === 550);
  });

  test('converts pixels back to seconds based on zoom level', () => {
    const sec = pixelsToSeconds(450, 150);
    assert(sec === 3.0);
  });

  test('snaps times to grid increments', () => {
    // Snapping 1.234s to 0.1s increments -> 1.2s
    const snapped = snapToGrid(1.234, 0.1);
    assert(snapped === 1.2);
  });

  test('formats seconds to video-grade timecodes', () => {
    const formatted = formatTimecode(3665.25);
    assert(formatted === '01:01:05.25');
  });
});

describe('Waveform Processing and Peak Extraction', () => {
  test('generates normalized peaks from audio buffer sample', () => {
    const mockChannel = new Float32Array([0.1, -0.5, 0.9, -0.2, 0.0, 0.4]);
    const mockData: WaveformData = {
      channels: [mockChannel],
      sampleRate: 16000,
      duration: 6.0,
    };

    const peaks = generatePeaks(mockData, 3);
    assert(peaks.length === 3);
    // Highest peak in section 1 (index 0..1): 0.5 -> normalized
    // Section 2 (index 2..3): 0.9 (max overall peak -> 1.0)
    assert(peaks[1] === 1.0);
  });
});

function assert(condition: boolean, message?: string) {
  if (!condition) {
    throw new Error(message || 'Assertion failed');
  }
}
