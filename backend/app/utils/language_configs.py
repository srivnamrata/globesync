from typing import Dict, List, Optional
from pydantic import BaseModel


class LanguageSpec(BaseModel):
    code: str
    name: str
    native_name: str
    rate_type: str  # "syllables" or "characters" or "words"
    base_rate_per_second: float  # average syllables/chars per second
    words_per_minute: int
    pause_comma_ms: int
    pause_period_ms: int
    formality_supported: bool = True


SUPPORTED_LANGUAGES: Dict[str, LanguageSpec] = {
    "en": LanguageSpec(code="en", name="English", native_name="English", rate_type="syllables", base_rate_per_second=4.4, words_per_minute=150, pause_comma_ms=200, pause_period_ms=400),
    "es": LanguageSpec(code="es", name="Spanish", native_name="Español", rate_type="syllables", base_rate_per_second=6.8, words_per_minute=180, pause_comma_ms=180, pause_period_ms=380),
    "fr": LanguageSpec(code="fr", name="French", native_name="Français", rate_type="syllables", base_rate_per_second=6.2, words_per_minute=160, pause_comma_ms=190, pause_period_ms=390),
    "de": LanguageSpec(code="de", name="German", native_name="Deutsch", rate_type="syllables", base_rate_per_second=5.2, words_per_minute=135, pause_comma_ms=220, pause_period_ms=420),
    "it": LanguageSpec(code="it", name="Italian", native_name="Italiano", rate_type="syllables", base_rate_per_second=6.6, words_per_minute=170, pause_comma_ms=180, pause_period_ms=380),
    "pt": LanguageSpec(code="pt", name="Portuguese", native_name="Português", rate_type="syllables", base_rate_per_second=6.4, words_per_minute=165, pause_comma_ms=190, pause_period_ms=390),
    "ru": LanguageSpec(code="ru", name="Russian", native_name="Русский", rate_type="syllables", base_rate_per_second=5.4, words_per_minute=130, pause_comma_ms=220, pause_period_ms=430),
    "zh": LanguageSpec(code="zh", name="Chinese (Simplified)", native_name="中文", rate_type="characters", base_rate_per_second=4.2, words_per_minute=220, pause_comma_ms=250, pause_period_ms=450),
    "ja": LanguageSpec(code="ja", name="Japanese", native_name="日本語", rate_type="characters", base_rate_per_second=7.4, words_per_minute=300, pause_comma_ms=220, pause_period_ms=420),
    "ko": LanguageSpec(code="ko", name="Korean", native_name="한국어", rate_type="syllables", base_rate_per_second=5.8, words_per_minute=140, pause_comma_ms=210, pause_period_ms=400),
    "ar": LanguageSpec(code="ar", name="Arabic", native_name="العربية", rate_type="syllables", base_rate_per_second=5.0, words_per_minute=130, pause_comma_ms=240, pause_period_ms=450),
    "hi": LanguageSpec(code="hi", name="Hindi", native_name="हिन्दी", rate_type="syllables", base_rate_per_second=5.6, words_per_minute=145, pause_comma_ms=200, pause_period_ms=400),
    "nl": LanguageSpec(code="nl", name="Dutch", native_name="Nederlands", rate_type="syllables", base_rate_per_second=5.1, words_per_minute=140, pause_comma_ms=210, pause_period_ms=410),
    "pl": LanguageSpec(code="pl", name="Polish", native_name="Polski", rate_type="syllables", base_rate_per_second=5.5, words_per_minute=135, pause_comma_ms=220, pause_period_ms=420),
    "tr": LanguageSpec(code="tr", name="Turkish", native_name="Türkçe", rate_type="syllables", base_rate_per_second=6.0, words_per_minute=155, pause_comma_ms=190, pause_period_ms=390),
    "sv": LanguageSpec(code="sv", name="Swedish", native_name="Svenska", rate_type="syllables", base_rate_per_second=5.0, words_per_minute=140, pause_comma_ms=210, pause_period_ms=400),
    "vi": LanguageSpec(code="vi", name="Vietnamese", native_name="Tiếng Việt", rate_type="syllables", base_rate_per_second=4.8, words_per_minute=150, pause_comma_ms=200, pause_period_ms=400),
    "th": LanguageSpec(code="th", name="Thai", native_name="ไทย", rate_type="characters", base_rate_per_second=6.5, words_per_minute=160, pause_comma_ms=220, pause_period_ms=420),
    "id": LanguageSpec(code="id", name="Indonesian", native_name="Bahasa Indonesia", rate_type="syllables", base_rate_per_second=6.2, words_per_minute=160, pause_comma_ms=190, pause_period_ms=390),
    "uk": LanguageSpec(code="uk", name="Ukrainian", native_name="Українська", rate_type="syllables", base_rate_per_second=5.3, words_per_minute=130, pause_comma_ms=220, pause_period_ms=420),
    "el": LanguageSpec(code="el", name="Greek", native_name="Ελληνικά", rate_type="syllables", base_rate_per_second=6.1, words_per_minute=155, pause_comma_ms=200, pause_period_ms=400),
    "he": LanguageSpec(code="he", name="Hebrew", native_name="עברית", rate_type="syllables", base_rate_per_second=4.9, words_per_minute=135, pause_comma_ms=210, pause_period_ms=410),
}


FEW_SHOT_TRANSLATION_EXAMPLES = {
    "en-es": [
        {"src": "Let's hit the ground running.", "tgt": "Empecemos con fuerza.", "note": "Idiom adapted with equivalent duration"},
        {"src": "It's not rocket science.", "tgt": "No es nada del otro mundo.", "note": "Natural cultural equivalent"},
    ],
    "en-fr": [
        {"src": "Break a leg!", "tgt": "Bonne chance!", "note": "Concise cultural greeting"},
        {"src": "At the end of the day.", "tgt": "En fin de compte.", "note": "Pacing matched"},
    ],
    "en-de": [
        {"src": "Keep an eye on the metrics.", "tgt": "Behalten Sie die Metriken im Auge.", "note": "Formal business tone preserved"},
    ],
    "en-ja": [
        {"src": "Thank you for your valuable time.", "tgt": "貴重なお時間をいただき、ありがとうございます。", "note": "Polite keigo adaptation with proper cadence"},
    ],
    "en-zh": [
        {"src": "Welcome to our keynote presentation.", "tgt": "欢迎来到我们的主题演讲。", "note": "Pithy 4-syllable phrasing"},
    ],
}


def normalize_language_code(code: str) -> str:
    """Normalizes regional language codes to the backend-supported base code."""
    return code.strip().lower().replace("_", "-").split("-")[0]



def is_supported_language_code(code: str) -> bool:
    """Returns whether the normalized language code is supported by the backend."""
    return normalize_language_code(code) in SUPPORTED_LANGUAGES



def get_supported_language_codes() -> List[str]:
    """Returns the sorted set of backend-supported language codes."""
    return sorted(SUPPORTED_LANGUAGES.keys())



def get_supported_languages() -> List[LanguageSpec]:
    """Returns backend-supported languages sorted by code."""
    return [SUPPORTED_LANGUAGES[code] for code in get_supported_language_codes()]



def get_language_spec(code: str) -> LanguageSpec:
    """Returns LanguageSpec or default English fallback."""
    normalized = normalize_language_code(code)
    return SUPPORTED_LANGUAGES.get(normalized, SUPPORTED_LANGUAGES["en"])
