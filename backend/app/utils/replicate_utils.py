from typing import Any, Dict, Optional


class ReplicateUtils:
    """Helper utilities for Replicate payload formatting and parameter validation."""

    @staticmethod
    def build_liveportrait_input(
        image_or_video_url: str,
        audio_url: str,
        duration_sec: float,
        face_expand_ratio: float = 1.25,
    ) -> Dict[str, Any]:
        """Formats LivePortrait neural facial animation prediction parameters."""
        return {
            "image": image_or_video_url,
            "audio": audio_url,
            "duration": round(duration_sec, 2),
            "face_expand_ratio": face_expand_ratio,
            "driving_smooth_observation_variance": 0.0003,
        }

    @staticmethod
    def build_wav2lip_input(
        face_video_url: str,
        audio_url: str,
        smooth: bool = True,
    ) -> Dict[str, Any]:
        """Formats Wav2Lip model prediction parameters."""
        return {
            "face": face_video_url,
            "audio": audio_url,
            "pads": "0 10 0 0",
            "smooth": smooth,
            "fps": 25,
        }


replicate_utils = ReplicateUtils()
