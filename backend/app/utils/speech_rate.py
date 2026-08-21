import re
from typing import Tuple
from app.utils.language_configs import get_language_spec


class SpeechRateEstimator:
    """Estimates spoken audio duration in milliseconds across different languages and phonetic structures."""

    @classmethod
    def estimate_speech_duration_ms(
        cls,
        text: str,
        language_code: str,
        speed_factor: float = 1.0,
    ) -> int:
        """
        Estimates the speaking duration of text in milliseconds.
        Duration = (Phonetic Units / Unit Rate) + Punctuation Pauses.
        """
        if not text or not text.strip():
            return 0

        spec = get_language_spec(language_code)
        clean_text = text.strip()

        # 1. Calculate base speech duration from phonetic units (syllables or characters)
        if spec.rate_type == "characters":
            # Strip whitespace and count non-punctuation characters
            char_count = len(re.findall(r"[\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", clean_text))
            if char_count == 0:
                char_count = len(clean_text)
            phonetic_units = max(1, char_count)
        else:
            # Count syllables heuristic
            words = re.findall(r"\b\w+\b", clean_text)
            syllable_count = sum(cls._estimate_syllables_in_word(w, spec.code) for w in words)
            phonetic_units = max(1, syllable_count)

        raw_duration_sec = phonetic_units / (spec.base_rate_per_second * speed_factor)

        # 2. Add natural punctuation pauses
        comma_count = len(re.findall(r"[,;:\-–—、，]", clean_text))
        period_count = len(re.findall(r"[.!?。！？]", clean_text))
        ellipsis_count = len(re.findall(r"(\.\.\.|…)", clean_text))

        pause_ms = (
            (comma_count * spec.pause_comma_ms)
            + (period_count * spec.pause_period_ms)
            + (ellipsis_count * spec.pause_period_ms * 1.5)
        )

        total_duration_ms = int((raw_duration_sec * 1000.0) + pause_ms)
        return max(300, total_duration_ms)  # Minimum 300ms for single word

    @classmethod
    def calculate_duration_delta(
        cls,
        original_duration_ms: int,
        estimated_duration_ms: int,
        tolerance: float = 0.10,
    ) -> Tuple[float, str]:
        """
        Calculates ratio and status:
        Ratio = estimated / original
        Status: 'within_tolerance', 'too_long', 'too_short'
        """
        if original_duration_ms <= 0:
            return 1.0, "within_tolerance"

        ratio = round(estimated_duration_ms / original_duration_ms, 3)
        delta_pct = (estimated_duration_ms - original_duration_ms) / original_duration_ms

        if abs(delta_pct) <= tolerance:
            status = "within_tolerance"
        elif delta_pct > tolerance:
            status = "too_long"
        else:
            status = "too_short"

        return ratio, status

    @staticmethod
    def _estimate_syllables_in_word(word: str, lang: str) -> int:
        """Heuristic syllable counter based on vowel clusters and diphthongs."""
        w = word.lower()
        if len(w) <= 2:
            return 1

        # Romance languages (Spanish, Italian, Portuguese) - vowel counting
        if lang in ["es", "it", "pt"]:
            vowels = len(re.findall(r"[aeiouáéíóúüãõàèìòù]", w))
            diphthongs = len(re.findall(r"(ai|ei|oi|ui|au|eu|ou|ia|ie|io|iu|ua|ue|uo)", w))
            return max(1, vowels - diphthongs)

        # German / Dutch / Polish
        if lang in ["de", "nl", "pl"]:
            vowels = len(re.findall(r"[aeiouyäöüëąęó]", w))
            diphthongs = len(re.findall(r"(ei|eu|au|äu|ie|ij|oe|ui)", w))
            return max(1, vowels - diphthongs)

        # English standard heuristic
        vowels = len(re.findall(r"[aeiouy]", w))
        if w.endswith("e") and not w.endswith("le") and not w.endswith("ee"):
            vowels -= 1
        diphthongs = len(re.findall(r"(ai|ay|ea|ee|ei|ey|oa|oe|oi|oo|ou|oy|au|aw)", w))
        syllables = vowels - diphthongs

        return max(1, syllables)


speech_rate_estimator = SpeechRateEstimator()
