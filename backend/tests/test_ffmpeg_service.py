from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.ffmpeg_service import FFmpegService
from app.utils.error_codes import ErrorCode, MediaAppException


class _Process:
    def __init__(self, returncode=0, stdout=b"", stderr=b"", output_path=None, create_output=True):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.output_path = output_path
        self.create_output = create_output

    async def communicate(self):
        if self.returncode == 0 and self.output_path and self.create_output:
            Path(self.output_path).write_bytes(b"rendered-video")
        return self.stdout, self.stderr


def _create_process(*processes):
    remaining = list(processes)
    commands = []

    async def runner(*command, **kwargs):
        process = remaining.pop(0)
        process.output_path = command[-1]
        commands.append(command)
        return process

    return runner, commands


@pytest.mark.asyncio
async def test_render_export_video_builds_ffmpeg_filter_graph_and_writes_output(tmp_path):
    video = tmp_path / "input.mp4"
    audio = tmp_path / "dub.wav"
    watermark = tmp_path / "watermark.png"
    subtitle = tmp_path / "captions.srt"
    output = tmp_path / "renders" / "final.mp4"
    for path, payload in (
        (video, b"video"),
        (audio, b"audio"),
        (watermark, b"image"),
        (subtitle, b"1\n00:00:00,000 --> 00:00:01,000\nhello\n"),
    ):
        path.write_bytes(payload)

    create, commands = _create_process(_Process())

    with patch("app.services.ffmpeg_service.asyncio.create_subprocess_exec", side_effect=create):
        result = await FFmpegService.render_export_video(
            video_input_path=str(video),
            audio_input_path=str(audio),
            output_path=str(output),
            resolution="2k",
            codec="vp9",
            frame_rate=24,
            video_quality="high",
            audio_codec="opus",
            color_grading=True,
            watermark_image_path=str(watermark),
            subtitle_srt_path=str(subtitle),
            burn_in_subtitles=True,
            audio_normalization=False,
        )

    assert result == str(output)
    assert output.read_bytes() == b"rendered-video"

    command = commands[0]
    assert command[:8] == (
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-i",
        str(watermark),
    )

    filter_graph = command[command.index("-filter_complex") + 1]
    expected_subtitles = str(subtitle).replace("\\", "/").replace(":", "\\:")
    assert filter_graph == (
        f"[0:v]scale=2560:1440,eq=contrast=1.1:saturation=1.2[vbase];"
        f"[vbase][2:v]overlay=W-w-10:10[vwatermarked];"
        f"[vwatermarked]subtitles='{expected_subtitles}'[vsubbed]"
    )
    assert command[command.index("-map") + 1] == "[vsubbed]"
    assert command[command.index("-c:v") + 1] == "libvpx-vp9"
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-r") + 1] == "24"
    assert command[command.index("-c:a") + 1] == "libopus"
    assert "-af" not in command


@pytest.mark.asyncio
async def test_render_export_video_reports_ffmpeg_failure(tmp_path):
    video = tmp_path / "input.mp4"
    audio = tmp_path / "dub.wav"
    output = tmp_path / "renders" / "failed.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")

    create, _ = _create_process(_Process(returncode=1, stderr=b"codec rejected"))

    with patch("app.services.ffmpeg_service.asyncio.create_subprocess_exec", side_effect=create):
        with pytest.raises(MediaAppException) as error:
            await FFmpegService.render_export_video(
                video_input_path=str(video),
                audio_input_path=str(audio),
                output_path=str(output),
            )

    assert error.value.status_code == 500
    assert error.value.error_code == ErrorCode.INTERNAL_SERVER_ERROR
    assert error.value.details["stderr"] == "codec rejected"
    assert not output.exists()


@pytest.mark.asyncio
async def test_render_export_video_validates_output_existence_even_on_success(tmp_path):
    video = tmp_path / "input.mp4"
    audio = tmp_path / "dub.wav"
    output = tmp_path / "renders" / "missing.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")

    create, _ = _create_process(_Process(returncode=0, create_output=False))

    with patch("app.services.ffmpeg_service.asyncio.create_subprocess_exec", side_effect=create):
        with pytest.raises(MediaAppException) as error:
            await FFmpegService.render_export_video(
                video_input_path=str(video),
                audio_input_path=str(audio),
                output_path=str(output),
            )

    assert error.value.status_code == 500
    assert error.value.error_code == ErrorCode.INTERNAL_SERVER_ERROR
    assert "Video rendering and encoding failed" in error.value.message
