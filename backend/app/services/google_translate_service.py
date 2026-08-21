"""Google Cloud Translation Advanced integration.

Credentials are supplied by Application Default Credentials.  For local
development, set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON key;
do not put key material in source control.
"""

import asyncio
import logging

from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException

logger = logging.getLogger("google_translate_service")


class GoogleTranslateService:
    """Async facade over the synchronous Google Cloud Translation v3 client."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if not settings.GOOGLE_CLOUD_PROJECT:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="GOOGLE_CLOUD_PROJECT must be set when TRANSLATION_PROVIDER is 'google'.",
            )

        if self._client is None:
            try:
                import google.auth
                from google.cloud import translate_v3
            except ImportError as exc:
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="Google Cloud Translation is not installed. Run pip install -r requirements.txt.",
                ) from exc
            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                credentials, _ = google.auth.load_credentials_from_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=["https://www.googleapis.com/auth/cloud-translation"],
                )
                self._client = translate_v3.TranslationServiceClient(credentials=credentials)
            else:
                # Uses Application Default Credentials in Cloud Run/GKE or a
                # developer credential configured with `gcloud auth application-default login`.
                self._client = translate_v3.TranslationServiceClient()
        return self._client

    async def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Translate one segment using Translation Advanced v3."""
        if not text.strip():
            return text

        def _translate() -> str:
            client = self._get_client()
            response = client.translate_text(
                request={
                    "parent": f"projects/{settings.GOOGLE_CLOUD_PROJECT}/locations/global",
                    "contents": [text],
                    "mime_type": "text/plain",
                    "source_language_code": source_language,
                    "target_language_code": target_language,
                }
            )
            return response.translations[0].translated_text

        try:
            return await asyncio.to_thread(_translate)
        except MediaAppException:
            raise
        except Exception as exc:
            logger.error("Google Cloud Translation request failed", exc_info=True)
            raise MediaAppException(
                status_code=502,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Google Cloud Translation failed: {exc}",
            ) from exc


google_translate_service = GoogleTranslateService()
