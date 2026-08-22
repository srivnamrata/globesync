import asyncio
from typing import Any, Dict, Optional
import httpx
from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException
import mimetypes

class DeepgramSTT:
    """Deepgram Nova-2 Speech-to-Text & Speaker Diarization Client."""

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.base_url = "https://api.deepgram.com/v1/listen"

    def get_headers(self, file_path: str):
        # Guess MIME type based on file extension
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            # Default to audio/wav if unknown
            mime_type = "audio/wav"

        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": mime_type,
        }

    async def transcribe_audio_file(
        self,
        audio_file_path: str,
        language: Optional[str] = None,
        max_speakers: Optional[int] = None,
        smart_format: bool = True,
        diarize: bool = True,
    ) -> Dict[str, Any]:
        """
        Submits audio directly to Deepgram Nova-2 API.
        Extracts word-level timestamps and speaker diarization labels.
        """
        # Allow canned responses only for local development; production must fail loudly
        # so placeholder credentials never masquerade as a successful transcript.
        api_key = (self.api_key or "").strip()
        looks_mock = (not api_key) or ("placeholder" in api_key.lower()) or ("test" in api_key.lower())
        if looks_mock:
            if settings.DEPLOYMENT_ENV == "development":
                return self._generate_mock_deepgram_response(audio_file_path, language)
            raise MediaAppException(
                status_code=503,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Deepgram API key is not configured for production transcription.",
            )

        params: Dict[str, Any] = {
            "model": settings.DEEPGRAM_MODEL,
            "smart_format": "true" if (smart_format and settings.DEEPGRAM_SMART_FORMAT) else "false",
            "punctuate": "true" if settings.DEEPGRAM_PUNCTUATE else "false",
            "diarize": "true" if (diarize and settings.DEEPGRAM_DIARIZE) else "false",
            "utterances": "true" if settings.DEEPGRAM_UTTERANCES else "false",
            "paragraphs": "true",
            "filler_words": "false",
        }

        if language:
            params["language"] = language
        else:
            params["detect_language"] = "true"

        if max_speakers:
            params["diarize_version"] = "latest"
            params["max_speakers"] = str(int(max_speakers))

        # headers = {
        #     "Authorization": f"Token {self.api_key}",
        #     "Content-Type": "audio/wav",
        # }
        headers = self.get_headers(audio_file_path)
        
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                with open(audio_file_path, "rb") as f:
                    audio_data = f.read()

                response = await client.post(
                    self.base_url,
                    params=params,
                    headers=headers,
                    content=audio_data,
                )

                if response.status_code == 429:
                    raise MediaAppException(
                        status_code=429,
                        error_code=ErrorCode.RATE_LIMITED,
                        message="Deepgram API rate limit reached.",
                    )
                elif response.status_code != 200:
                    raise MediaAppException(
                        status_code=response.status_code,
                        error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                        message=f"Deepgram STT API returned error status {response.status_code}.",
                        details={"response_text": response.text},
                    )

                return response.json()

        except httpx.TimeoutException:
            raise MediaAppException(
                status_code=504,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Deepgram STT API request timed out.",
            )
        except MediaAppException:
            raise
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Failed to communicate with Deepgram STT API: {str(e)}",
            )

    @staticmethod
    def _generate_mock_deepgram_response(
        audio_file_path: str, language: Optional[str]
    ) -> Dict[str, Any]:
        """High-fidelity mock Deepgram Nova-2 response for testing and offline development."""
        return {
            "metadata": {
                "transaction_key": "mock_tx_12345",
                "request_id": "req_deepgram_mock",
                "sha256": "mock_sha256_hash",
                "created": "2026-08-16T18:00:00.000Z",
                "duration": 12.5,
                "channels": 1,
                "models": ["nova-2"],
            },
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "Hello and welcome to the global launch presentation. Thank you for joining us today.",
                                "confidence": 0.982,
                                "words": [
                                    {"word": "Hello", "punctuated_word": "Hello", "start": 0.5, "end": 0.9, "confidence": 0.99, "speaker": 0},
                                    {"word": "and", "punctuated_word": "and", "start": 1.0, "end": 1.1, "confidence": 0.98, "speaker": 0},
                                    {"word": "welcome", "punctuated_word": "welcome", "start": 1.2, "end": 1.7, "confidence": 0.99, "speaker": 0},
                                    {"word": "to", "punctuated_word": "to", "start": 1.8, "end": 1.9, "confidence": 0.97, "speaker": 0},
                                    {"word": "the", "punctuated_word": "the", "start": 2.0, "end": 2.1, "confidence": 0.98, "speaker": 0},
                                    {"word": "global", "punctuated_word": "global", "start": 2.2, "end": 2.6, "confidence": 0.98, "speaker": 0},
                                    {"word": "launch", "punctuated_word": "launch", "start": 2.7, "end": 3.1, "confidence": 0.97, "speaker": 0},
                                    {"word": "presentation", "punctuated_word": "presentation.", "start": 3.2, "end": 4.1, "confidence": 0.98, "speaker": 0},
                                    {"word": "Thank", "punctuated_word": "Thank", "start": 5.0, "end": 5.3, "confidence": 0.99, "speaker": 1},
                                    {"word": "you", "punctuated_word": "you", "start": 5.4, "end": 5.6, "confidence": 0.98, "speaker": 1},
                                    {"word": "for", "punctuated_word": "for", "start": 5.7, "end": 5.9, "confidence": 0.97, "speaker": 1},
                                    {"word": "joining", "punctuated_word": "joining", "start": 6.0, "end": 6.4, "confidence": 0.99, "speaker": 1},
                                    {"word": "us", "punctuated_word": "us", "start": 6.5, "end": 6.7, "confidence": 0.98, "speaker": 1},
                                    {"word": "today", "punctuated_word": "today.", "start": 6.8, "end": 7.4, "confidence": 0.98, "speaker": 1},
                                ],
                                "paragraphs": {
                                    "transcript": "Hello and welcome to the global launch presentation.\n\nThank you for joining us today.",
                                    "paragraphs": [
                                        {
                                            "speaker": 0,
                                            "num_words": 8,
                                            "start": 0.5,
                                            "end": 4.1,
                                            "sentences": [
                                                {
                                                    "text": "Hello and welcome to the global launch presentation.",
                                                    "start": 0.5,
                                                    "end": 4.1,
                                                }
                                            ],
                                        },
                                        {
                                            "speaker": 1,
                                            "num_words": 6,
                                            "start": 5.0,
                                            "end": 7.4,
                                            "sentences": [
                                                {
                                                    "text": "Thank you for joining us today.",
                                                    "start": 5.0,
                                                    "end": 7.4,
                                                }
                                            ],
                                        },
                                    ],
                                },
                            }
                        ]
                    }
                ]
            },
        }


deepgram_stt = DeepgramSTT()
