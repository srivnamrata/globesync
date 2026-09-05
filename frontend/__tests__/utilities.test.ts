import { describe, expect, it } from 'vitest';
import { estimateTranslationSpeechDuration } from '../utils/durationEstimation';
import {
  formatTimecode,
  pixelsToSeconds,
  secondsToPixels,
  snapToGrid,
} from '../utils/timelineCalculations';
import { sanitizeSegmentText, generateSrtTimings } from '../utils/transcriptFormatting';
import { generatePeaks, type WaveformData } from '../utils/waveformProcessing';

describe('editor and timeline utilities', () => {
  it('estimates speech duration using language-specific rates', () => {
    expect(estimateTranslationSpeechDuration(
      'Hola y bienvenidos a la conferencia de traducción automatizada.',
      'es',
    )).toBe(3.6);
    expect(estimateTranslationSpeechDuration('', 'en')).toBe(0);
  });

  it('sanitizes transcript text and formats SRT timings', () => {
    expect(sanitizeSegmentText('   This   has   too   many   spaces.  '))
      .toBe('This has too many spaces.');
    expect(generateSrtTimings(125.405, 130.98))
      .toBe('00:02:05,405 --> 00:02:10,980');
  });

  it('converts, snaps, and formats timeline values', () => {
    expect(secondsToPixels(5.5, 100)).toBe(550);
    expect(pixelsToSeconds(450, 150)).toBe(3);
    expect(snapToGrid(1.234, 0.1)).toBeCloseTo(1.2);
    expect(formatTimecode(3665.25)).toBe('01:01:05.25');
  });

  it('normalizes waveform peaks', () => {
    const waveform: WaveformData = {
      channels: [new Float32Array([0.1, -0.5, 0.9, -0.2, 0, 0.4])],
      sampleRate: 16_000,
      duration: 6,
    };

    const peaks = generatePeaks(waveform, 3);
    expect(peaks[0]).toBeCloseTo(0.555556);
    expect(peaks[1]).toBe(1);
    expect(peaks[2]).toBeCloseTo(0.444444);
  });
});
