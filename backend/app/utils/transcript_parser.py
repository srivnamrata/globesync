from typing import Any, Dict, List, Tuple

from app.schemas.transcription_schema import SegmentResponse, WordDetail


class TranscriptParser:
    """Parses Google Speech-to-Text responses and exports normalized transcripts."""

    @staticmethod
    def _coerce_speaker_index(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_google_duration_seconds(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.endswith("s"):
                cleaned = cleaned[:-1]
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    @classmethod
    def parse_google_response(
        cls,
        google_data: Dict[str, Any],
        time_offset_seconds: float = 0.0,
    ) -> Tuple[List[SegmentResponse], str, float, int, int]:
        """Parse Google Cloud Speech-to-Text JSON into normalized segments."""
        results = google_data.get("results", []) or []
        if not results:
            return [], "", 0.0, 0, 0

        transcripts: List[str] = []
        result_level_segments: List[SegmentResponse] = []
        speaker_set = set()
        total_confidence = 0.0
        confidence_count = 0
        seq = 0
        word_collections: List[List[Dict[str, Any]]] = []
        diarized_word_collections: List[List[Dict[str, Any]]] = []

        for result in results:
            alternatives = result.get("alternatives", []) or []
            if not alternatives:
                continue

            alt = alternatives[0]
            transcript_text = (alt.get("transcript") or "").strip()
            if transcript_text:
                transcripts.append(transcript_text)

            alt_words = alt.get("words", []) or []
            if alt_words:
                word_collections.append(alt_words)
                if any(word.get("speakerTag") is not None for word in alt_words):
                    diarized_word_collections.append(alt_words)

            parsed_words: List[WordDetail] = []
            for word in alt_words:
                start = cls._parse_google_duration_seconds(word.get("startTime")) + time_offset_seconds
                end = cls._parse_google_duration_seconds(word.get("endTime")) + time_offset_seconds
                confidence = round(float(word.get("confidence", alt.get("confidence", 0.95))), 4)
                speaker_idx = max(0, cls._coerce_speaker_index(word.get("speakerTag"), default=1) - 1)
                speaker_tag = f"Speaker {speaker_idx + 1}"
                parsed_words.append(
                    WordDetail(
                        text=(word.get("word") or "").strip(),
                        start=round(start, 3),
                        end=round(end, 3),
                        confidence=confidence,
                        speaker=speaker_tag,
                    )
                )

            if transcript_text:
                seg_start = parsed_words[0].start if parsed_words else time_offset_seconds
                seg_end = parsed_words[-1].end if parsed_words else time_offset_seconds
                result_level_segments.append(
                    SegmentResponse(
                        start_time=round(seg_start, 3),
                        end_time=round(seg_end, 3),
                        duration=max(0.0, round(seg_end - seg_start, 3)),
                        speaker=parsed_words[0].speaker if parsed_words else "Speaker 1",
                        text=transcript_text,
                        confidence=round(float(alt.get("confidence", 0.95)), 4),
                        words=parsed_words,
                        sequence_order=seq,
                    )
                )
                seq += 1

        canonical_words = (
            diarized_word_collections[-1]
            if diarized_word_collections
            else [word for collection in word_collections for word in collection]
        )
        diarized_words: List[WordDetail] = []
        for word in canonical_words:
            start = cls._parse_google_duration_seconds(word.get("startTime")) + time_offset_seconds
            end = cls._parse_google_duration_seconds(word.get("endTime")) + time_offset_seconds
            confidence = round(float(word.get("confidence", 0.95)), 4)
            speaker_idx = max(0, cls._coerce_speaker_index(word.get("speakerTag"), default=1) - 1)
            speaker_tag = f"Speaker {speaker_idx + 1}"
            diarized_words.append(
                WordDetail(
                    text=(word.get("word") or "").strip(),
                    start=round(start, 3),
                    end=round(end, 3),
                    confidence=confidence,
                    speaker=speaker_tag,
                )
            )
            total_confidence += confidence
            confidence_count += 1
            speaker_set.add(speaker_tag)

        segments: List[SegmentResponse] = []
        if diarized_words:
            current_words: List[WordDetail] = []
            current_speaker = diarized_words[0].speaker
            seq = 0

            for word in diarized_words:
                pause = (word.start - current_words[-1].end) if current_words else 0.0
                current_duration = (current_words[-1].end - current_words[0].start) if current_words else 0.0
                should_split = current_words and (
                    word.speaker != current_speaker
                    or pause > 0.8
                    or current_duration > 8.0
                )
                if should_split:
                    seg_start = current_words[0].start
                    seg_end = current_words[-1].end
                    segments.append(
                        SegmentResponse(
                            start_time=round(seg_start, 3),
                            end_time=round(seg_end, 3),
                            duration=max(0.0, round(seg_end - seg_start, 3)),
                            speaker=current_speaker or "Speaker 1",
                            text=" ".join(item.text for item in current_words).strip(),
                            confidence=round(
                                sum(item.confidence for item in current_words) / len(current_words),
                                4,
                            ),
                            words=list(current_words),
                            sequence_order=seq,
                        )
                    )
                    seq += 1
                    current_words = []
                    current_speaker = word.speaker

                if not current_words:
                    current_speaker = word.speaker
                current_words.append(word)

            if current_words:
                seg_start = current_words[0].start
                seg_end = current_words[-1].end
                segments.append(
                    SegmentResponse(
                        start_time=round(seg_start, 3),
                        end_time=round(seg_end, 3),
                        duration=max(0.0, round(seg_end - seg_start, 3)),
                        speaker=current_speaker or "Speaker 1",
                        text=" ".join(item.text for item in current_words).strip(),
                        confidence=round(
                            sum(item.confidence for item in current_words) / len(current_words),
                            4,
                        ),
                        words=list(current_words),
                        sequence_order=seq,
                    )
                )
        elif result_level_segments:
            segments = result_level_segments
            speaker_set.add("Speaker 1")

        word_count = len(diarized_words) or sum(len(segment.words) for segment in result_level_segments)
        if diarized_word_collections and transcripts:
            full_transcript = transcripts[-1]
        else:
            full_transcript = (
                "\n\n".join(transcripts)
                if transcripts
                else " ".join(segment.text for segment in segments if segment.text)
            )
        avg_confidence = round(total_confidence / confidence_count, 4) if confidence_count else 0.95
        speaker_count = len(speaker_set) if speaker_set else 1

        return segments, full_transcript, avg_confidence, word_count, speaker_count

    @classmethod
    def export_to_dialogue_format(cls, segments: List[SegmentResponse]) -> str:
        """Format segments as a timestamped dialogue script."""
        lines = []
        for segment in segments:
            time_str = cls._format_seconds_to_timestamp(segment.start_time)
            lines.append(f'[{time_str}] {segment.speaker}: "{segment.text}"')
        return "\n".join(lines)

    @classmethod
    def export_to_srt(cls, segments: List[SegmentResponse]) -> str:
        """Export segments into SubRip format."""
        entries = []
        for index, segment in enumerate(segments, start=1):
            start_str = cls._format_seconds_to_srt_time(segment.start_time)
            end_str = cls._format_seconds_to_srt_time(segment.end_time)
            entries.append(
                f"{index}\n{start_str} --> {end_str}\n[{segment.speaker}] {segment.text}\n"
            )
        return "\n".join(entries)

    @classmethod
    def export_to_vtt(cls, segments: List[SegmentResponse]) -> str:
        """Export segments into WebVTT format."""
        lines = ["WEBVTT\n"]
        for index, segment in enumerate(segments, start=1):
            start_str = cls._format_seconds_to_vtt_time(segment.start_time)
            end_str = cls._format_seconds_to_vtt_time(segment.end_time)
            lines.append(
                f"{index}\n{start_str} --> {end_str}\n<v {segment.speaker}>{segment.text}\n"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_seconds_to_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole_seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"

    @staticmethod
    def _format_seconds_to_srt_time(seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"

    @staticmethod
    def _format_seconds_to_vtt_time(seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


transcript_parser = TranscriptParser()
