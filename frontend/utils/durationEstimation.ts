export function estimateTranslationSpeechDuration(
  text: string,
  targetLang: string
): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  if (words === 0) return 0.0;

  // Language specific words-per-minute (WPM) settings
  let wpm = 140; // Default speech rate
  switch (targetLang.toLowerCase()) {
    case 'es': // Spanish is generally spoken faster, but contains more syllables per word
      wpm = 150;
      break;
    case 'de': // German has longer compounds, lower WPM
      wpm = 120;
      break;
    case 'fr':
      wpm = 135;
      break;
    case 'ja': // Japanese characters count
      return Number(((text.length * 0.25)).toFixed(2));
  }

  const durationSec = (words / wpm) * 60;
  return Number(durationSec.toFixed(2));
}
