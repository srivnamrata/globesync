from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.video_reconstructor import VideoReconstructor
from app.utils.error_codes import ErrorCode, MediaAppException


class _Process:
    def __init__(self, *, returncode=0, stderr=b"", create_output=True):
        self.returncode = returncode
        self.stderr = stderr
        self.create_output = create_output
        self.output_path = None

    async def communicate(self):
        if self.returncode == 0 and self.create_output and self.output_path:
            Path(self.output_path).write_bytes(b"video")
        return b"", self.stderr


def _process_runner(*processes):
    remaining = list(processes)
    commands = []

    async def run(*command, **_kwargs):
        process = remaining.pop(0)
        process.output_path = command[-1]
        commands.append(command)
        return process

    return run, commands


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("burn_in", "expected"),
    [
        (True, ("-vf", "libx264")),
        (False, ("-c:s", "mov_text")),
    ],
)
async def test_mux_video_and_audio_supports_burned_and_soft_subtitles(tmp_path, burn_in, expected):
    video = tmp_path / "input.mp4"
    audio = tmp_path / "audio.wav"
    subtitle = tmp_path / "captions.srt"
    output = tmp_path / f"output-{burn_in}.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    subtitle.write_text("captions", encoding="utf-8")
    run, commands = _process_runner(_Process())

    with patch("app.services.video_reconstructor.asyncio.create_subprocess_exec", side_effect=run):
        result = await VideoReconstructor._mux_video_and_audio(
            str(video),
            str(audio),
            str(output),
            str(subtitle),
            burn_in,
        )

    assert result == str(output)
    assert output.exists()
    command = commands[0]
    assert expected[0] in command
    assert expected[1] in command
    if burn_in:
        assert "-c:s" not in command
    else:
        assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"
        assert "2:s:0" in command


@pytest.mark.asyncio
async def test_mux_video_and_audio_copies_video_without_subtitles_and_reports_failure(tmp_path):
    video = tmp_path / "input.mp4"
    audio = tmp_path / "audio.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    output = tmp_path / "missing.mp4"
    run, commands = _process_runner(_Process(returncode=1, stderr=b"mux failed"))

    with patch("app.services.video_reconstructor.asyncio.create_subprocess_exec", side_effect=run):
        with pytest.raises(MediaAppException) as error:
            await VideoReconstructor._mux_video_and_audio(str(video), str(audio), str(output))

    assert "-c:v" in commands[0]
    assert "copy" in commands[0]
    assert error.value.error_code == ErrorCode.INTERNAL_SERVER_ERROR
    assert error.value.details["stderr"] == "mux failed"


@pytest.mark.asyncio
async def test_reconstruct_video_builds_sorted_gap_timeline_and_cleans_temporaries(tmp_path, monkeypatch):
    original = tmp_path / "original.mp4"
    audio = tmp_path / "dub.wav"
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    output = tmp_path / "final" / "video.mp4"
    for path in (original, audio, first, second):
        path.write_bytes(b"fixture")
    monkeypatch.setattr("app.services.video_reconstructor.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    async def extract(**kwargs):
        Path(kwargs["output_segment_path"]).write_bytes(b"slice")
        return kwargs["output_segment_path"]

    get_properties = AsyncMock(return_value=(1920, 1080, 30.0, 10.0))
    extract_segment = AsyncMock(side_effect=extract)
    mux = AsyncMock(side_effect=lambda **kwargs: kwargs["output_path"])
    run, commands = _process_runner(_Process())

    with (
        patch("app.services.video_reconstructor.video_processor.get_video_properties", get_properties),
        patch("app.services.video_reconstructor.video_processor.extract_video_segment", extract_segment),
        patch("app.services.video_reconstructor.asyncio.create_subprocess_exec", side_effect=run),
        patch.object(VideoReconstructor, "_mux_video_and_audio", mux),
    ):
        result = await VideoReconstructor.reconstruct_video_with_lip_sync(
            str(original),
            [
                {"segment_path": str(second), "start_sec": 6.0, "duration_sec": 1.0},
                {"segment_path": str(first), "start_sec": 2.0, "duration_sec": 2.0},
            ],
            str(audio),
            str(output),
        )

    assert result == str(output)
    assert [call.kwargs["start_seconds"] for call in extract_segment.await_args_list] == [0.0, 4.0, 7.0]
    assert [call.kwargs["duration_seconds"] for call in extract_segment.await_args_list] == [2.0, 2.0, 3.0]
    concat_file = Path(commands[0][commands[0].index("-i") + 1])
    assert not concat_file.exists()
    assert not list(tmp_path.glob("gap_*.mp4"))
    assert not list(tmp_path.glob("tail_*.mp4"))
    assert not list(tmp_path.glob("stitched_*.mp4"))
    assert mux.await_args.kwargs["video_path"].endswith(".mp4")


@pytest.mark.asyncio
async def test_reconstruct_video_uses_direct_mux_for_empty_timeline(tmp_path):
    output = tmp_path / "final.mp4"
    mux = AsyncMock(return_value=str(output))

    with (
        patch(
            "app.services.video_reconstructor.video_processor.get_video_properties",
            new=AsyncMock(return_value=(1280, 720, 24.0, 3.0)),
        ),
        patch.object(VideoReconstructor, "_mux_video_and_audio", mux),
    ):
        result = await VideoReconstructor.reconstruct_video_with_lip_sync(
            "original.mp4", [], "audio.wav", str(output)
        )

    assert result == str(output)
    mux.assert_awaited_once_with("original.mp4", "audio.wav", str(output), None, False)


@pytest.mark.asyncio
async def test_reconstruct_video_reports_stitch_failure_and_removes_temp_files(tmp_path, monkeypatch):
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"segment")
    monkeypatch.setattr("app.services.video_reconstructor.settings.PROCESSED_MEDIA_DIR", str(tmp_path))
    run, commands = _process_runner(_Process(returncode=1, stderr=b"concat failed"))

    with (
        patch(
            "app.services.video_reconstructor.video_processor.get_video_properties",
            new=AsyncMock(return_value=(1280, 720, 24.0, 1.0)),
        ),
        patch("app.services.video_reconstructor.asyncio.create_subprocess_exec", side_effect=run),
    ):
        with pytest.raises(MediaAppException) as error:
            await VideoReconstructor.reconstruct_video_with_lip_sync(
                "original.mp4",
                [{"segment_path": str(rendered), "start_sec": 0.0, "duration_sec": 1.0}],
                "audio.wav",
                str(tmp_path / "final.mp4"),
            )

    assert error.value.message == "Intermediate video stitching failed."
    assert error.value.details["stderr"] == "concat failed"
    assert not Path(commands[0][commands[0].index("-i") + 1]).exists()

