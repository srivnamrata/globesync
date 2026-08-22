from typing import Any, Dict, List, Optional, Tuple
from app.schemas.transcription_schema import SegmentResponse, WordDetail


class TranscriptParser:
    """Parses, normalizes, and exports Deepgram Nova-2 STT & Diarization responses."""

    @staticmethod
    def _coerce_speaker_index(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def parse_deepgram_response(
        cls,
        deepgram_data: Dict[str, Any],
        time_offset_seconds: float = 0.0,
    ) -> Tuple[List[SegmentResponse], str, float, int, int]:
        """
        Parses Deepgram Nova-2 JSON payload.
        Returns:
            - List of SegmentResponse (speaker, start, end, text, words)
            - Full consolidated text
            - Average confidence score
            - Total word count
            - Total distinct speaker count
        """
        results = deepgram_data.get("results", {})
        channels = results.get("channels", [])
        if not channels:
            return [], "", 0.0, 0, 0

        first_channel = channels[0]
        alternatives = first_channel.get("alternatives", [])
        if not alternatives:
            return [], "", 0.0, 0, 0

        alt = alternatives[0]
        words_data = alt.get("words", [])
        utterances_data = results.get("utterances", []) or []
        paragraphs_data = alt.get("paragraphs", {}).get("paragraphs", []) or []

        segments: List[SegmentResponse] = []
        speaker_set = set()
        total_confidence = 0.0
        matched_word_count = 0
        fallback_confidence_total = 0.0
        fallback_confidence_count = 0

        # Priority 1: Deepgram utterances already represent pause- and speaker-bounded speech units.
        if utterances_data:
            seq = 0
            for utterance in utterances_data:
                speaker_id = cls._coerce_speaker_index(utterance.get("speaker"))
                speaker_tag = f"Speaker {speaker_id + 1}"

                utterance_words_raw = utterance.get("words", []) or []
                utterance_words: List[WordDetail] = []
                utterance_conf_sum = 0.0

                for w in utterance_words_raw:
                    w_start = float(w.get("start", 0.0)) + time_offset_seconds
                    w_end = float(w.get("end", 0.0)) + time_offset_seconds
                    w_conf = float(w.get("confidence", 0.95))
                    utterance_words.append(
                        WordDetail(
                            text=w.get("punctuated_word") or w.get("word", ""),
                            start=round(w_start, 3),
                            end=round(w_end, 3),
                            confidence=round(w_conf, 4),
                            speaker=speaker_tag,
                        )
                    )
                    utterance_conf_sum += w_conf

                if utterance_words:
                    total_confidence += utterance_conf_sum
                    matched_word_count += len(utterance_words)

                segment_text = (utterance.get("transcript") or " ".join(word.text for word in utterance_words)).strip()
                if not segment_text:
                    continue

                s_start = float(utterance.get("start", 0.0)) + time_offset_seconds
                s_end = float(utterance.get("end", 0.0)) + time_offset_seconds
                avg_conf = (
                    round(utterance_conf_sum / len(utterance_words), 4)
                    if utterance_words
                    else round(float(utterance.get("confidence", 0.95)), 4)
                )
                if not utterance_words:
                    fallback_confidence_total += avg_conf
                    fallback_confidence_count += 1

                speaker_set.add(speaker_tag)
                segments.append(
                    SegmentResponse(
                        start_time=round(s_start, 3),
                        end_time=round(s_end, 3),
                        duration=max(0.0, round(s_end - s_start, 3)),
                        speaker=speaker_tag,
                        text=segment_text,
                        confidence=avg_conf,
                        words=utterance_words,
                        sequence_order=seq,
                    )
                )
                seq += 1

        # Priority 2: paragraph sentence structure, used only when utterances are absent or empty.
        if not segments and paragraphs_data:
            seq = 0
            for para in paragraphs_data:
                speaker_id = cls._coerce_speaker_index(para.get("speaker"))
                speaker_tag = f"Speaker {speaker_id + 1}"

                para_sentences = para.get("sentences", []) or []
                for sent in para_sentences:
                    s_text = sent.get("text", "").strip()
                    s_start = float(sent.get("start", 0.0)) + time_offset_seconds
                    s_end = float(sent.get("end", 0.0)) + time_offset_seconds
                    s_duration = max(0.0, round(s_end - s_start, 3))

                    sent_words: List[WordDetail] = []
                    sent_conf_sum = 0.0

                    for w in words_data:
                        w_start = float(w.get("start", 0.0)) + time_offset_seconds
                        w_end = float(w.get("end", 0.0)) + time_offset_seconds
                        w_speaker = cls._coerce_speaker_index(w.get("speaker"), default=speaker_id)
                        if (
                            s_start - 0.05 <= w_start
                            and w_end <= s_end + 0.05
                            and w_speaker == speaker_id
                        ):
                            w_conf = float(w.get("confidence", 0.95))
                            sent_words.append(
                                WordDetail(
                                    text=w.get("punctuated_word") or w.get("word", ""),
                                    start=round(w_start, 3),
                                    end=round(w_end, 3),
                                    confidence=round(w_conf, 4),
                                    speaker=speaker_tag,
                                )
                            )
                            sent_conf_sum += w_conf

                    if sent_words:
                        total_confidence += sent_conf_sum
                        matched_word_count += len(sent_words)

                    segment_text = s_text or " ".join(word.text for word in sent_words).strip()
                    if not segment_text:
                        continue

                    avg_sent_conf = (
                        round(sent_conf_sum / len(sent_words), 4)
                        if sent_words
                        else 0.95
                    )
                    if not sent_words:
                        fallback_confidence_total += avg_sent_conf
                        fallback_confidence_count += 1

                    speaker_set.add(speaker_tag)
                    segments.append(
                        SegmentResponse(
                            start_time=round(s_start, 3),
                            end_time=round(s_end, 3),
                            duration=s_duration,
                            speaker=speaker_tag,
                            text=segment_text,
                            confidence=avg_sent_conf,
                            words=sent_words,
                            sequence_order=seq,
                        )
                    )
                    seq += 1

        # Priority 3: group contiguous words by speaker and pause length.
        if not segments and words_data:
            current_speaker: Optional[int] = None
            current_words: List[WordDetail] = []
            seq = 0

            for w in words_data:
                spk = cls._coerce_speaker_index(w.get("speaker"))
                w_start = float(w.get("start", 0.0)) + time_offset_seconds
                w_end = float(w.get("end", 0.0)) + time_offset_seconds
                w_conf = float(w.get("confidence", 0.95))
                w_text = w.get("punctuated_word") or w.get("word", "")

                total_confidence += w_conf
                matched_word_count += 1

                if current_speaker is None:
                    current_speaker = spk

                # When speaker changes or pause > 1.5 seconds, start new segment
                pause = (w_start - current_words[-1].end) if current_words else 0.0
                if spk != current_speaker or pause > 1.5:
                    if current_words:
                        seg_speaker_tag = f"Speaker {current_speaker + 1}"
                        speaker_set.add(seg_speaker_tag)
                        seg_text = " ".join(cw.text for cw in current_words)
                        seg_start = current_words[0].start
                        seg_end = current_words[-1].end
                        seg_conf = round(sum(cw.confidence for cw in current_words) / len(current_words), 4)

                        segments.append(
                            SegmentResponse(
                                start_time=round(seg_start, 3),
                                end_time=round(seg_end, 3),
                                duration=round(seg_end - seg_start, 3),
                                speaker=seg_speaker_tag,
                                text=seg_text,
                                confidence=seg_conf,
                                words=current_words,
                                sequence_order=seq,
                            )
                        )
                        seq += 1

                    current_speaker = spk
                    current_words = []

                current_words.append(
                    WordDetail(
                        text=w_text,
                        start=round(w_start, 3),
                        end=round(w_end, 3),
                        confidence=round(w_conf, 4),
                        speaker=f"Speaker {spk + 1}",
                    )
                )

            if current_words:
                seg_speaker_tag = f"Speaker {current_speaker + 1}"
                speaker_set.add(seg_speaker_tag)
                seg_text = " ".join(cw.text for cw in current_words)
                seg_start = current_words[0].start
                seg_end = current_words[-1].end
                seg_conf = round(sum(cw.confidence for cw in current_words) / len(current_words), 4)

                segments.append(
                    SegmentResponse(
                        start_time=round(seg_start, 3),
                        end_time=round(seg_end, 3),
                        duration=round(seg_end - seg_start, 3),
                        speaker=seg_speaker_tag,
                        text=seg_text,
                        confidence=seg_conf,
                        words=current_words,
                        sequence_order=seq,
                    )
                )

        word_count = matched_word_count or sum(len(seg.words) for seg in segments) or len(words_data)
        full_transcript = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        avg_confidence = (
            round(total_confidence / word_count, 4)
            if total_confidence > 0 and word_count > 0
            else round(fallback_confidence_total / fallback_confidence_count, 4)
            if fallback_confidence_count > 0
            else 0.95
        )
        speaker_count = len(speaker_set) if speaker_set else 1

        return segments, full_transcript, avg_confidence, word_count, speaker_count

    # =========================================================================
    # EXPORT FORMATTERS (SRT, WebVTT, Dialogue Script)
    # =========================================================================
    @classmethod
    def export_to_dialogue_format(cls, segments: List[SegmentResponse]) -> str:
        """Formats as: [00:00:02] Speaker 1: "text goes here" """
        lines = []
        for seg in segments:
            time_str = cls._format_seconds_to_timestamp(seg.start_time)
            lines.append(f"[{time_str}] {seg.speaker}: \"{seg.text}\"")
        return "\n".join(lines)

    @classmethod
    def export_to_srt(cls, segments: List[SegmentResponse]) -> str:
        """Exports segments into SubRip (.srt) subtitle standard."""
        srt_entries = []
        for i, seg in enumerate(segments, start=1):
            start_str = cls._format_seconds_to_srt_time(seg.start_time)
            end_str = cls._format_seconds_to_srt_time(seg.end_time)
            srt_entries.append(f"{i}\n{start_str} --> {end_str}\n[{seg.speaker}] {seg.text}\n")
        return "\n".join(srt_entries)

    @classmethod
    def export_to_vtt(cls, segments: List[SegmentResponse]) -> str:
        """Exports segments into WebVTT (.vtt) standard."""
        vtt_lines = ["WEBVTT\n"]
        for i, seg in enumerate(segments, start=1):
            start_str = cls._format_seconds_to_vtt_time(seg.start_time)
            end_str = cls._format_seconds_to_vtt_time(seg.end_time)
            vtt_lines.append(f"{i}\n{start_str} --> {end_str}\n<v {seg.speaker}>{seg.text}\n")
        return "\n".join(vtt_lines)

    @staticmethod
    def _format_seconds_to_timestamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _format_seconds_to_srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        total_milliseconds = int(round(seconds * 1000))
        h, remainder = divmod(total_milliseconds, 3_600_000)
        m, remainder = divmod(remainder, 60_000)
        s, ms = divmod(remainder, 1_000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _format_seconds_to_vtt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        total_milliseconds = int(round(seconds * 1000))
        h, remainder = divmod(total_milliseconds, 3_600_000)
        m, remainder = divmod(remainder, 60_000)
        s, ms = divmod(remainder, 1_000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


transcript_parser = TranscriptParser()
