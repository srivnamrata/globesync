from enum import Enum
from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    INVALID_FORMAT = "INVALID_FORMAT"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    CHUNK_OUT_OF_ORDER = "CHUNK_OUT_OF_ORDER"
    CHUNK_TOO_SMALL = "CHUNK_TOO_SMALL"
    UPLOAD_SESSION_EXPIRED = "UPLOAD_SESSION_EXPIRED"
    UPLOAD_SESSION_NOT_FOUND = "UPLOAD_SESSION_NOT_FOUND"
    STORAGE_UPLOAD_FAILED = "STORAGE_UPLOAD_FAILED"
    FFPROBE_ANALYSIS_FAILED = "FFPROBE_ANALYSIS_FAILED"
    THUMBNAIL_GENERATION_FAILED = "THUMBNAIL_GENERATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class MediaAppException(HTTPException):
    """Base application exception with structured error code and metadata."""
    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "error_code": error_code.value,
                "message": message,
                "details": details or {},
            }
        )
        self.error_code = error_code
        self.message = message
        self.details = details or {}


class FileTooLargeException(MediaAppException):
    def __init__(self, max_bytes: int, received_bytes: int):
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_code=ErrorCode.FILE_TOO_LARGE,
            message=f"File exceeds maximum allowed size of {max_bytes / (1024*1024*1024):.2f} GB.",
            details={"max_bytes": max_bytes, "received_bytes": received_bytes},
        )


class UnsupportedMediaFormatException(MediaAppException):
    def __init__(self, detected_format: str, allowed_formats: list):
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            error_code=ErrorCode.INVALID_FORMAT,
            message=f"Media format '{detected_format}' is not supported.",
            details={"detected_format": detected_format, "allowed_formats": allowed_formats},
        )


class UnsupportedCodecException(MediaAppException):
    def __init__(self, detected_codec: str, allowed_codecs: list, codec_type: str = "video"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=ErrorCode.UNSUPPORTED_CODEC,
            message=f"Unsupported {codec_type} codec '{detected_codec}'.",
            details={"detected_codec": detected_codec, "allowed_codecs": allowed_codecs, "codec_type": codec_type},
        )


class ChecksumMismatchException(MediaAppException):
    def __init__(self, expected: str, calculated: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=ErrorCode.CHECKSUM_MISMATCH,
            message="Provided SHA256 checksum does not match uploaded data.",
            details={"expected_checksum": expected, "calculated_checksum": calculated},
        )


class UploadSessionExpiredException(MediaAppException):
    def __init__(self, session_id: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            error_code=ErrorCode.UPLOAD_SESSION_EXPIRED,
            message=f"Upload session {session_id} has expired or was aborted.",
            details={"session_id": session_id},
        )
