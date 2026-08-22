import os
from typing import Any, Dict, List, Optional
from app.schemas.transcription_schema import SegmentResponse


class SubtitleGenerator:
    """Generates SRT and WebVTT subtitle stream files from translated dialogue segments."""

    @classmethod
    def generate_srt(cls, segments: List[SegmentResponse]) -> str:
        """Generates standard SubRip Subtitle (SRT) format content."""
        lines = []
        for idx, seg in enumerate(segments, start=1):
            start = cls._format_timestamp(seg.start_time, delimiter=",")
            end = cls._format_timestamp(seg.end_time, delimiter=",")
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(f"{seg.text}\n")
        return "\n".join(lines)

    @classmethod
    def generate_vtt(cls, segments: List[SegmentResponse], style_config: Optional[Dict[str, Any]] = None) -> str:
        """Generates WebVTT format content with optional inline styling cues."""
        lines = ["WEBVTT\n"]
        if style_config:
            # Inject CSS style configuration block
            font = style_config.get("font", "Arial")
            size = style_config.get("size", 16)
            color = style_config.get("color", "#FFFFFF")
            bg = style_config.get("background_color", "rgba(0,0,0,0.8)")
            lines.append("STYLE")
            lines.append(f"::cue {{ font-family: {font}; font-size: {size}px; color: {color}; background-color: {bg}; }}\n")

        for idx, seg in enumerate(segments, start=1):
            start = cls._format_timestamp(seg.start_time, delimiter=".")
            end = cls._format_timestamp(seg.end_time, delimiter=".")
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(f"{seg.text}\n")
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(seconds: float, delimiter: str = ",") -> str:
        """Formats seconds to HH:MM:SS,ms or HH:MM:SS.ms string."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int(round((seconds % 1) * 1000))
        return f"{hrs:02d}:{mins:02d}:{secs:02d}{delimiter}{ms:03d}"


subtitle_generator = SubtitleGenerator()
