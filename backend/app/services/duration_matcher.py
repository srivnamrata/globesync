import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import redis.asyncio as aioredis
from app.core.config import settings
from app.services.openai_service import openai_service
from app.services.google_translate_service import google_translate_service
from app.utils.prompt_templates import (
    get_refinement_condensation_prompt,
    get_refinement_expansion_prompt,
    get_segment_translation_user_prompt,
    get_system_translation_prompt,
)
from app.utils.speech_rate import speech_rate_estimator

logger = logging.getLogger("duration_matcher")


class DurationMatchedTranslationResult:
    def __init__(
        self,
        source_text: str,
        translated_text: str,
        source_language: str,
        target_language: str,
        original_duration_ms: int,
        estimated_duration_ms: int,
        duration_ratio: float,
        duration_status: str,
        iterations_count: int,
        confidence_score: float,
        is_cached: bool,
        total_cost_usd: float,
        iteration_history: List[Dict[str, Any]],
    ):
        self.source_text = source_text
        self.translated_text = translated_text
        self.source_language = source_language
        self.target_language = target_language
        self.original_duration_ms = original_duration_ms
        self.estimated_duration_ms = estimated_duration_ms
        self.duration_ratio = duration_ratio
        self.duration_status = duration_status
        self.iterations_count = iterations_count
        self.confidence_score = confidence_score
        self.is_cached = is_cached
        self.total_cost_usd = total_cost_usd
        self.iteration_history = iteration_history


class DurationMatcher:
    """Intelligent Translation Service with iterative audio duration matching feedback loop."""

    @classmethod
    async def translate_with_duration_matching(
        cls,
        source_text: str,
        original_duration_ms: int,
        source_language: str,
        target_language: str,
        speaker_tag: str = "Speaker 1",
        previous_context: Optional[str] = None,
        next_context: Optional[str] = None,
        tolerance: float = 0.10,
        max_iterations: int = 3,
    ) -> DurationMatchedTranslationResult:
        """
        Translates text with active feedback loop to constrain translated speaking time within ±10%.
        """
        # Step 1: Check Redis cache
        cache_key = cls._generate_cache_key(
            text=source_text,
            src=source_language,
            tgt=target_language,
            provider=settings.TRANSLATION_PROVIDER,
            original_duration_ms=original_duration_ms,
            speaker_tag=speaker_tag,
            previous_context=previous_context,
            next_context=next_context,
            tolerance=tolerance,
            max_iterations=max_iterations,
        )
        cached_data = await cls._get_from_cache(cache_key)

        if cached_data:
            cached_text = cached_data["translated_text"]
            est_ms = speech_rate_estimator.estimate_speech_duration_ms(cached_text, target_language)
            ratio, status = speech_rate_estimator.calculate_duration_delta(original_duration_ms, est_ms, tolerance)
            return DurationMatchedTranslationResult(
                source_text=source_text,
                translated_text=cached_text,
                source_language=source_language,
                target_language=target_language,
                original_duration_ms=original_duration_ms,
                estimated_duration_ms=est_ms,
                duration_ratio=ratio,
                duration_status=status,
                iterations_count=1,
                confidence_score=0.98,
                is_cached=True,
                total_cost_usd=0.0,
                iteration_history=[{"iteration": 1, "text": cached_text, "duration_ms": est_ms, "status": "cache_hit"}],
            )

        # Step 2: Prepare initial prompt
        system_prompt = get_system_translation_prompt(source_language, target_language)
        user_prompt = get_segment_translation_user_prompt(
            original_text=source_text,
            target_duration_ms=original_duration_ms,
            previous_context=previous_context,
            next_context=next_context,
            speaker_tag=speaker_tag,
        )

        iteration_history: List[Dict[str, Any]] = []
        total_cost = 0.0
        current_text = ""
        current_est_ms = 0
        current_ratio = 1.0
        current_status = "pending"
        conversation_history: List[Dict[str, str]] = []

        provider = settings.TRANSLATION_PROVIDER.lower().strip()
        if provider not in {"openai", "google"}:
            raise ValueError("TRANSLATION_PROVIDER must be either 'openai' or 'google'.")

        # Google Cloud Translation provides direct translation. Duration-guided
        # rewriting is an OpenAI capability, so Google runs a single pass and
        # reports its measured duration for downstream audio retiming.
        iterations_to_run = 1 if provider == "google" else max_iterations

        # Iteration Loop (Max 3 iterations for OpenAI)
        for iteration in range(1, iterations_to_run + 1):
            if iteration == 1:
                prompt_to_send = user_prompt
            else:
                # Build feedback refinement prompt
                delta_ms = current_est_ms - original_duration_ms
                if current_status == "too_long":
                    excess_pct = (delta_ms / original_duration_ms) * 100.0
                    prompt_to_send = get_refinement_condensation_prompt(
                        current_translation=current_text,
                        original_text=source_text,
                        target_duration_ms=original_duration_ms,
                        estimated_duration_ms=current_est_ms,
                        excess_pct=excess_pct,
                    )
                else:  # too_short
                    deficit_pct = (abs(delta_ms) / original_duration_ms) * 100.0
                    prompt_to_send = get_refinement_expansion_prompt(
                        current_translation=current_text,
                        original_text=source_text,
                        target_duration_ms=original_duration_ms,
                        estimated_duration_ms=current_est_ms,
                        deficit_pct=deficit_pct,
                    )

            if provider == "google":
                text_result = await google_translate_service.translate_text(
                    source_text, source_language, target_language
                )
                cost = 0.0
            else:
                text_result, _p_tokens, _c_tokens, cost = await openai_service.generate_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=prompt_to_send,
                    conversation_history=conversation_history if iteration > 1 else None,
                )
            total_cost += cost
            current_text = text_result

            # Re-estimate duration
            current_est_ms = speech_rate_estimator.estimate_speech_duration_ms(current_text, target_language)
            current_ratio, current_status = speech_rate_estimator.calculate_duration_delta(
                original_duration_ms, current_est_ms, tolerance
            )

            iteration_history.append({
                "iteration": iteration,
                "text": current_text,
                "estimated_duration_ms": current_est_ms,
                "duration_ratio": current_ratio,
                "status": current_status,
                "cost_usd": cost,
            })

            # Append to conversation thread for next iteration context
            conversation_history.append({"role": "user", "content": prompt_to_send})
            conversation_history.append({"role": "assistant", "content": current_text})

            # If within ±10% tolerance, exit loop early
            if current_status == "within_tolerance":
                break

        # Calculate confidence score
        # Closeness factor: 1.0 - abs(ratio - 1.0), clamped between 0.70 and 0.99
        closeness = max(0.70, min(0.99, round(1.0 - (abs(current_ratio - 1.0) * 0.8), 4)))

        # Cache result in Redis for future reuse
        await cls._save_to_cache(
            cache_key,
            {
                "translated_text": current_text,
                "target_language": target_language,
                "estimated_duration_ms": current_est_ms,
            },
        )

        return DurationMatchedTranslationResult(
            source_text=source_text,
            translated_text=current_text,
            source_language=source_language,
            target_language=target_language,
            original_duration_ms=original_duration_ms,
            estimated_duration_ms=current_est_ms,
            duration_ratio=current_ratio,
            duration_status=current_status,
            iterations_count=len(iteration_history),
            confidence_score=closeness,
            is_cached=False,
            total_cost_usd=round(total_cost, 6),
            iteration_history=iteration_history,
        )

    @staticmethod
    def _generate_cache_key(
        text: str,
        src: str,
        tgt: str,
        provider: str = "openai",
        original_duration_ms: int = 0,
        speaker_tag: str = "Speaker 1",
        previous_context: Optional[str] = None,
        next_context: Optional[str] = None,
        tolerance: float = 0.10,
        max_iterations: int = 3,
    ) -> str:
        payload = {
            "text": text.strip(),
            "src": src,
            "tgt": tgt,
            "provider": provider.lower(),
            "original_duration_ms": int(original_duration_ms),
            "speaker_tag": speaker_tag,
            "previous_context": (previous_context or "").strip(),
            "next_context": (next_context or "").strip(),
            "tolerance": round(float(tolerance), 4),
            "max_iterations": int(max_iterations),
        }
        cache_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:24]
        return f"cache:trans:{payload['provider']}:{src}:{tgt}:{cache_hash}"

    @staticmethod
    async def _get_from_cache(key: str) -> Optional[Dict[str, Any]]:
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            data = await r.get(key)
            await r.close()
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None

    @staticmethod
    async def _save_to_cache(key: str, data: Dict[str, Any], ttl: int = settings.TRANSLATION_CACHE_TTL_SECONDS) -> None:
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            await r.setex(key, ttl, json.dumps(data))
            await r.close()
        except Exception:
            pass


duration_matcher = DurationMatcher()
