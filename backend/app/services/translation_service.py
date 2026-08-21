import asyncio
import logging
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.transcript import TranscriptSegment
from app.models.translation import Translation
from app.services.duration_matcher import duration_matcher

logger = logging.getLogger("translation_service")


class TranslationService:
    """Orchestrates batch translation pipelines, concurrency management, and persistence."""

    @classmethod
    async def translate_segments_batch_async(
        cls,
        segments: List[TranscriptSegment],
        source_language: str,
        target_language: str,
        project_id: Optional[uuid.UUID] = None,
        concurrency_limit: int = 10,
    ) -> List[Translation]:
        """
        Translates a batch of transcript segments in parallel with context window preservation.
        """
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def _translate_single_segment(idx: int, seg: TranscriptSegment) -> Translation:
            async with semaphore:
                orig_dur_ms = int(float(seg.duration_seconds) * 1000)
                # Extract surrounding context
                prev_text = segments[idx - 1].text if idx > 0 else None
                next_text = segments[idx + 1].text if idx < len(segments) - 1 else None

                res = await duration_matcher.translate_with_duration_matching(
                    source_text=seg.text,
                    original_duration_ms=orig_dur_ms,
                    source_language=source_language,
                    target_language=target_language,
                    speaker_tag=seg.speaker_tag,
                    previous_context=prev_text,
                    next_context=next_text,
                )

                # Compute speed adjustment factor for downstream FFmpeg/Rubberband
                # If duration ratio is 1.05, speed adjustment is 1.05 to fit original slot
                speed_factor = max(0.80, min(1.25, res.duration_ratio))

                return Translation(
                    transcript_segment_id=seg.id,
                    project_id=project_id,
                    source_language=source_language,
                    target_language=target_language,
                    source_text=seg.text,
                    translated_text=res.translated_text,
                    original_duration_ms=res.original_duration_ms,
                    estimated_duration_ms=res.estimated_duration_ms,
                    duration_ratio=res.duration_ratio,
                    iterations_count=res.iterations_count,
                    confidence_score=res.confidence_score,
                    quality_score=res.confidence_score,
                    is_cached=res.is_cached,
                    speed_adjustment_factor=speed_factor,
                    iteration_history=res.iteration_history,
                )

        tasks = [_translate_single_segment(i, seg) for i, seg in enumerate(segments)]
        results = await asyncio.gather(*tasks)
        return results


translation_service = TranslationService()
