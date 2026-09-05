import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from app.services.av_sync_service import AVSyncChecker
from app.services.export_orchestrator import ExportOrchestrator
from app.services.tts_orchestrator import TTSOrchestrator


class _Process:
    def __init__(self):
        self.command = None

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_export_orchestrator_generates_burned_subtitles_and_cleans_them(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.export_orchestrator.settings.PROCESSED_MEDIA_DIR",
        str(tmp_path),
    )
    render = AsyncMock(return_value=str(tmp_path / "output.mp4"))
    segments = [
        {
            "start_sec": 0,
            "end_sec": 1.25,
            "duration_sec": 1.25,
            "speaker_tag": "Narrator",
            "text": "Hello",
        }
    ]

    with patch(
        "app.services.export_orchestrator.ffmpeg_service.render_export_video",
        new=render,
    ):
        result = await ExportOrchestrator.process_export_render(
            "source.mp4",
            "dub.wav",
            str(tmp_path / "output.mp4"),
            {
                "format": "webm",
                "resolution": "720p",
                "codec": "vp9",
                "frame_rate": 24,
                "video_quality": "high",
                "audio_codec": "opus",
                "subtitles": {"enabled": True, "format": "burnt-in"},
                "post_processing": {
                    "color_grading": True,
                    "watermark": "logo.png",
                    "audio_normalization": False,
                },
            },
            segments,
        )

    assert result == str(tmp_path / "output.mp4")
    kwargs = render.await_args.kwargs
    assert kwargs["subtitle_srt_path"].endswith(".srt")
    assert not Path(kwargs["subtitle_srt_path"]).exists()
    assert kwargs["burn_in_subtitles"] is True
    assert kwargs["color_grading"] is True
    assert kwargs["watermark_image_path"] == "logo.png"
    assert kwargs["audio_normalization"] is False


@pytest.mark.asyncio
async def test_export_orchestrator_uses_safe_defaults_without_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.export_orchestrator.settings.PROCESSED_MEDIA_DIR",
        str(tmp_path),
    )
    render = AsyncMock()

    with patch(
        "app.services.export_orchestrator.ffmpeg_service.render_export_video",
        new=render,
    ):
        await ExportOrchestrator.process_export_render(
            "source.mp4",
            "dub.wav",
            "output.mp4",
            {"subtitles": {"enabled": True}},
            [],
        )

    kwargs = render.await_args.kwargs
    assert kwargs["subtitle_srt_path"] is None
    assert kwargs["format"] == "mp4"
    assert kwargs["resolution"] == "1080p"
    assert kwargs["audio_normalization"] is True


@pytest.mark.asyncio
async def test_tts_orchestrator_synthesizes_retimes_uploads_and_returns_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.tts_orchestrator.settings.PROCESSED_MEDIA_DIR",
        str(tmp_path),
    )
    monkeypatch.setattr(
        "app.services.tts_orchestrator.settings.GCS_BUCKET_NAME",
        "audio-bucket",
    )
    translation = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        translated_text="Bonjour",
        target_language="fr",
        original_duration_ms=1200,
    )
    raw_path = tmp_path / f"raw_tts_{translation.id.hex}.wav"
    retimed_path = tmp_path / f"retimed_{translation.id.hex}.wav"

    async def synthesize(**kwargs):
        Path(kwargs["output_file_path"]).write_bytes(b"raw")

    async def retime(**kwargs):
        Path(kwargs["output_audio_path"]).write_bytes(b"retimed")

    with (
        patch(
            "app.services.tts_orchestrator.google_tts_service.synthesize_speech",
            new=AsyncMock(side_effect=synthesize),
        ) as synthesize_mock,
        patch(
            "app.services.tts_orchestrator.audio_postprocessor.get_audio_duration_ms",
            new=AsyncMock(side_effect=[1500, 1210]),
        ),
        patch(
            "app.services.tts_orchestrator.audio_matcher.calculate_retiming_factor",
            return_value=(1.25, 300),
        ),
        patch(
            "app.services.tts_orchestrator.audio_postprocessor.retime_and_normalize_segment",
            new=AsyncMock(side_effect=retime),
        ) as retime_mock,
        patch(
            "app.services.tts_orchestrator.storage_service.upload_file",
            new=AsyncMock(return_value="gs://audio-bucket/result.wav"),
        ) as upload,
    ):
        result = await TTSOrchestrator.synthesize_single_translation(
            translation,
            request_id="request-1",
            task_id="task-1",
            idempotency_key="tts-key",
        )

    synthesize_mock.assert_awaited_once_with(
        text="Bonjour",
        language_code="fr",
        output_file_path=str(raw_path),
    )
    retime_mock.assert_awaited_once_with(
        input_audio_path=str(raw_path),
        output_audio_path=str(retimed_path),
        speed_factor=1.25,
        target_duration_ms=1200,
    )
    upload.assert_awaited_once_with(
        file_path=str(retimed_path),
        key=f"tts_segments/{translation.project_id}/{translation.id.hex}.wav",
        mime_type="audio/wav",
    )
    assert result.raw_tts_duration_ms == 1500
    assert result.retimed_duration_ms == 1210
    assert result.request_id == "request-1"
    assert result.idempotency_key == "tts-key"
    assert not raw_path.exists()
    assert not retimed_path.exists()


@pytest.mark.asyncio
async def test_tts_batch_preserves_order_and_builds_per_segment_idempotency_keys():
    translations = [
        SimpleNamespace(id=uuid.uuid4()),
        SimpleNamespace(id=uuid.uuid4()),
    ]

    async def synthesize(translation, **kwargs):
        return SimpleNamespace(
            translation_id=translation.id,
            idempotency_key=kwargs["idempotency_key"],
        )

    with patch.object(
        TTSOrchestrator,
        "synthesize_single_translation",
        new=AsyncMock(side_effect=synthesize),
    ) as single:
        result = await TTSOrchestrator.synthesize_batch_concurrent(
            translations,
            request_id="request",
            task_id="task",
            idempotency_key_prefix="batch",
            concurrency=1,
        )

    assert [item.translation_id for item in result] == [item.id for item in translations]
    assert [item.idempotency_key for item in result] == [
        f"batch:{translations[0].id}",
        f"batch:{translations[1].id}",
    ]
    assert single.await_count == 2


@pytest.mark.asyncio
async def test_av_sync_measurement_returns_signed_drift():
    with (
        patch(
            "app.services.av_sync_service.video_processor.get_video_properties",
            new=AsyncMock(return_value=(1920, 1080, 30, 2.0)),
        ),
        patch(
            "app.services.av_sync_service.audio_postprocessor.get_audio_duration_ms",
            new=AsyncMock(return_value=2150),
        ),
    ):
        assert await AVSyncChecker.measure_av_drift_ms("video.mp4", "audio.wav") == 150


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("offset_ms", "expected_offset"),
    [(250, "0.250"), (-125, "-0.125"), (5, None)],
)
async def test_av_sync_command_applies_only_material_offsets(
    tmp_path,
    offset_ms,
    expected_offset,
):
    output = tmp_path / "aligned.mp4"
    process = _Process()

    async def create(*command, **kwargs):
        process.command = command
        return process

    with patch(
        "app.services.av_sync_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AVSyncChecker.align_av_streams(
            "video.mp4",
            "audio.wav",
            str(output),
            offset_ms=offset_ms,
        )

    assert result == str(output)
    if expected_offset is None:
        assert "-itsoffset" not in process.command
    else:
        assert process.command[process.command.index("-itsoffset") + 1] == expected_offset
    assert process.command[-2:] == ("-shortest", str(output))
