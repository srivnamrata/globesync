import { estimateTranslationSpeechDuration } from '../utils/durationEstimation';
import { sanitizeSegmentText, generateSrtTimings } from '../utils/transcriptFormatting';

describe('Transcript Editor Utilities & Calculations', () => {
  test('estimates speech duration based on language words-per-minute (WPM)', () => {
    const text = "Hola y bienvenidos a la conferencia de traducción automatizada.";
    // Spanish (~150 WPM) -> 9 words -> (9 / 150) * 60 = 3.60 seconds
    const duration = estimateTranslationSpeechDuration(text, 'es');
    assert(duration === 3.60);
  });

  test('cleans duplicate spaces and formats clean paragraph sentences', () => {
    const rawText = "   This   has   too   many   spaces.  ";
    const cleaned = sanitizeSegmentText(rawText);
    assert(cleaned === "This has too many spaces.");
  });

  test('generates clean SRT timings formatted for media containers', () => {
    const srtTime = generateSrtTimings(125.405, 130.980);
    assert(srtTime === "00:02:05,405 --> 00:02:10,980");
  });
});

function assert(condition: boolean, message?: string) {
  if (!condition) {
    throw new Error(message || 'Assertion failed');
  }
}
