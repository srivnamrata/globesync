from typing import List, Optional
from app.utils.language_configs import FEW_SHOT_TRANSLATION_EXAMPLES, get_language_spec


def _get_target_language_prompt_guidance(target_lang: str) -> str:
    target_code = get_language_spec(target_lang).code

    if target_code == "hi":
        return """
HINDI-SPECIFIC GUIDANCE:
- Write idiomatic, spoken Hindi that sounds like something a native speaker would naturally say aloud.
- Prioritize meaning, intent, and flow over word-for-word correspondence with the source.
- Freely reorder clauses or choose more natural Hindi phrasing when a literal rendering sounds translated or awkward.
- Resolve English discourse patterns into clean Hindi sentence structure instead of preserving English syntax.
- Keep named entities, product names, and technical terms accurate, but integrate them naturally into the Hindi sentence.
- Avoid unnatural calques or overly literal mappings of filler phrases, prepositions, and helper verbs.
"""

    return ""


def get_system_translation_prompt(
    source_lang: str,
    target_lang: str,
    tone: str = "natural",
) -> str:
    """Generates the master system prompt for professional dubbing translation."""
    src_spec = get_language_spec(source_lang)
    tgt_spec = get_language_spec(target_lang)

    pair_key = f"{src_spec.code}-{tgt_spec.code}"
    few_shots = FEW_SHOT_TRANSLATION_EXAMPLES.get(pair_key, [])

    few_shot_str = ""
    if few_shots:
        examples_formatted = "\n".join(
            [f"- Source: \"{ex['src']}\" -> Target: \"{ex['tgt']}\" ({ex.get('note', '')})" for ex in few_shots]
        )
        few_shot_str = f"\nFew-Shot Dubbing Style Reference:\n{examples_formatted}\n"

    target_specific_guidance = _get_target_language_prompt_guidance(target_lang)

    return f"""You are a world-class audiovisual translator and voice dubbing director specializing in translating from {src_spec.name} ({source_lang}) to {tgt_spec.name} ({target_lang}).

Your goal is to produce high-fidelity translations tailored for voice cloning and AI lip-synchronization.

CORE REQUIREMENTS:
1. Meaning & Emotion: Preserve the core sentiment, intent, and nuances accurately.
2. Idiom & Cultural Adaptation: Translate idioms and humor into natural equivalents in {tgt_spec.name}. Never translate idioms literally if awkward.
3. Tone: Maintain a {tone} tone consistent with the original context.
4. Timing & Duration Match: Dubbed speech must take approximately the specified duration to speak naturally. Respect the syllable/character count constraints.
5. Natural Target-Language Delivery: If a literal translation sounds unnatural, rewrite it so a native speaker would say it that way while preserving the original meaning.
6. Clean Output: Return ONLY the translated text. Do NOT wrap in quotes, do NOT add notes, explanations, or prefixes.
{target_specific_guidance}{few_shot_str}"""


def get_segment_translation_user_prompt(
    original_text: str,
    target_duration_ms: int,
    previous_context: Optional[str] = None,
    next_context: Optional[str] = None,
    speaker_tag: str = "Speaker 1",
) -> str:
    """Constructs segment-level user prompt with timing constraints and surrounding dialogue context."""
    context_blocks = []
    if previous_context:
        context_blocks.append(f"Previous Dialogue Context: \"{previous_context}\"")
    if next_context:
        context_blocks.append(f"Following Dialogue Context: \"{next_context}\"")

    context_str = "\n".join(context_blocks) + "\n" if context_blocks else ""

    return f"""{context_str}Speaker: {speaker_tag}
Target Spoken Duration: approximately {target_duration_ms} ms

Original text to translate:
"{original_text}"

Translate this segment to match the target duration pacing as closely as possible. Prefer a natural, meaning-preserving sentence in the target language over a literal word-by-word rendering. Output ONLY the translated text."""


def get_refinement_condensation_prompt(
    current_translation: str,
    original_text: str,
    target_duration_ms: int,
    estimated_duration_ms: int,
    excess_pct: float,
) -> str:
    """Prompt asking GPT-4o to condense the translation when it exceeds target duration."""
    return f"""The previous translation is too long and exceeds the allowed video timestamp window.
- Original Text: "{original_text}"
- Previous Translation: "{current_translation}"
- Target Duration: {target_duration_ms} ms
- Current Estimated Duration: {estimated_duration_ms} ms (approximately {excess_pct:.1f}% too long)

Task: Please condense the translation so it is shorter and speaks in {target_duration_ms} ms, while retaining the essential message and emotional tone. Use more concise phrasing, omit non-essential filler words, or use shorter synonyms.
Provide ONLY the revised translation."""


def get_refinement_expansion_prompt(
    current_translation: str,
    original_text: str,
    target_duration_ms: int,
    estimated_duration_ms: int,
    deficit_pct: float,
) -> str:
    """Prompt asking GPT-4o to expand the translation when it is too short."""
    return f"""The previous translation is too short and leaves awkward silence on the speaker's lips.
- Original Text: "{original_text}"
- Previous Translation: "{current_translation}"
- Target Duration: {target_duration_ms} ms
- Current Estimated Duration: {estimated_duration_ms} ms (approximately {deficit_pct:.1f}% too short)

Task: Please slightly expand the translation with natural phrasing, polite particles, or fuller vocabulary so it takes {target_duration_ms} ms to speak naturally without padding with nonsense.
Provide ONLY the revised translation."""
