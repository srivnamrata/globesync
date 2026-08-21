import hashlib
import mimetypes
import os
from typing import Dict, List, Set, Tuple
from app.utils.error_codes import (
    ErrorCode,
    FileTooLargeException,
    UnsupportedCodecException,
    UnsupportedMediaFormatException,
)

# Supported MIME types and extensions
SUPPORTED_VIDEO_FORMATS: Dict[str, List[str]] = {
    "video/mp4": [".mp4", ".m4v"],
    "video/webm": [".webm"],
    "video/quicktime": [".mov"],
    "video/x-matroska": [".mkv"],
    "video/x-msvideo": [".avi"],
}

SUPPORTED_AUDIO_FORMATS: Dict[str, List[str]] = {
    "audio/mpeg": [".mp3"],
    "audio/mp3": [".mp3"],
    "audio/wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/ogg": [".ogg", ".oga"],
    "audio/flac": [".flac"],
    "audio/aac": [".aac"],
    "audio/mp4": [".m4a"],
}

SUPPORTED_MIME_TYPES: Set[str] = set(SUPPORTED_VIDEO_FORMATS.keys()) | set(SUPPORTED_AUDIO_FORMATS.keys())

# Supported Video & Audio Codecs for Pipeline Processing
SUPPORTED_VIDEO_CODECS: Set[str] = {
    "h264", "hevc", "h265", "vp8", "vp9", "av1", "mpeg4", "prores"
}

SUPPORTED_AUDIO_CODECS: Set[str] = {
    "aac", "opus", "mp3", "pcm_s16le", "pcm_s24le", "pcm_s32le", "flac", "vorbis"
}

# Magic numbers signatures for fast header verification
MAGIC_SIGNATURES: List[Tuple[bytes, str]] = [
    (b"\x00\x00\x00\x18ftypmp42", "video/mp4"),
    (b"\x00\x00\x00\x20ftypisom", "video/mp4"),
    (b"\x00\x00\x00\x1cftyp", "video/mp4"),
    (b"\x1a\x45\xdf\xa3", "video/webm_or_mkv"),  # EBML header for WebM and MKV
    (b"RIFF", "audio/wav_or_avi"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"\x00\x00\x00\x14ftypqt", "video/quicktime"),
    (b"\x00\x00\x00\x08wide", "video/quicktime"),
    (b"\x00\x00\x00\x08moov", "video/quicktime"),
]


def detect_mime_type_from_header(first_bytes: bytes, filename: str) -> str:
    """Detects MIME type using magic header bytes with fallback to filename extension."""
    if len(first_bytes) >= 12:
        # Check standard ISO Base Media File Format (MP4 / MOV / M4A)
        if b"ftyp" in first_bytes[4:12]:
            brand = first_bytes[8:12]
            if brand in [b"qt  ", b"moov"]:
                return "video/quicktime"
            elif brand in [b"M4A ", b"M4B "]:
                return "audio/mp4"
            return "video/mp4"

        # Check EBML (WebM / Matroska)
        if first_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            ext = os.path.splitext(filename.lower())[1]
            return "video/webm" if ext == ".webm" else "video/x-matroska"

        # Check RIFF (WAV vs AVI)
        if first_bytes.startswith(b"RIFF"):
            if len(first_bytes) >= 12 and first_bytes[8:12] == b"WAVE":
                return "audio/wav"
            elif len(first_bytes) >= 12 and first_bytes[8:12] == b"AVI ":
                return "video/x-msvideo"
            return "audio/wav"

        # MP3 ID3 or Sync Frame
        if first_bytes.startswith(b"ID3") or first_bytes.startswith(b"\xff\xfb") or first_bytes.startswith(b"\xff\xf3"):
            return "audio/mpeg"

        # FLAC / OGG
        if first_bytes.startswith(b"fLaC"):
            return "audio/flac"
        if first_bytes.startswith(b"OggS"):
            return "audio/ogg"

    # Fallback to extension matching
    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        return guessed_type

    return "application/octet-stream"


def validate_file_metadata(
    filename: str,
    filesize_bytes: int,
    detected_mime: str,
    max_filesize_bytes: int = 4 * 1024 * 1024 * 1024,
) -> None:
    """Validates basic file constraints before accepting upload."""
    if filesize_bytes > max_filesize_bytes:
        raise FileTooLargeException(max_bytes=max_filesize_bytes, received_bytes=filesize_bytes)

    if detected_mime not in SUPPORTED_MIME_TYPES:
        allowed = list(SUPPORTED_MIME_TYPES)
        raise UnsupportedMediaFormatException(detected_format=detected_mime, allowed_formats=allowed)


def validate_codecs(
    video_codec: str | None,
    audio_codec: str | None,
    is_video: bool = True,
) -> None:
    """Ensures codecs are supported by the downstream STT, LipSync, and FFmpeg pipeline."""
    if is_video and video_codec:
        normalized_video_codec = video_codec.lower()
        if normalized_video_codec not in SUPPORTED_VIDEO_CODECS:
            raise UnsupportedCodecException(
                detected_codec=video_codec,
                allowed_codecs=list(SUPPORTED_VIDEO_CODECS),
                codec_type="video",
            )

    if audio_codec:
        normalized_audio_codec = audio_codec.lower()
        if normalized_audio_codec not in SUPPORTED_AUDIO_CODECS:
            raise UnsupportedCodecException(
                detected_codec=audio_codec,
                allowed_codecs=list(SUPPORTED_AUDIO_CODECS),
                codec_type="audio",
            )


def calculate_sha256(file_path: str, chunk_size: int = 65536) -> str:
    """Computes SHA-256 hash of a file incrementally to avoid high memory usage."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()
