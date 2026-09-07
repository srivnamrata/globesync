from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.video_processor import VideoProcessor
from app.utils.error_codes import MediaAppException


class _Process:
    def __init__(self, *, returncode=0, stdout=b"", stderr=b"", create_output=True):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.create_output = create_output
        self.output_path = None

    async def communicate(self):
        if self.returncode == 0 and self.create_output and self.output_path:
            Path(self.output_path).write_bytes(b"media")
        return self.stdout, self.stderr


def _runner(process, commands):
    async def run(*command, **_kwargs):
        process.output_path = command[-1]
        commands.append(command)
        return process

    return run


@pytest.mark.asyncio
async def test_video_processor_extracts_segment_and_frame_with_expected_timing(tmp_path):
    segment_output = tmp_path / "segments" / "clip.mp4"
    frame_output = tmp_path / "frames" / "frame.jpg"
    commands = []
    processes = [_Process(), _Process(create_output=False)]

    async def side_effect(*command, **_kwargs):
        process = processes.pop(0)
        process.output_path = command[-1]
        commands.append(command)
        return process

    with patch(
        "app.services.video_processor.asyncio.create_subprocess_exec",
        side_effect=side_effect,
    ):
        segment = await VideoProcessor.extract_video_segment(
            "input.mp4", 1.25, 2.5, str(segment_output)
        )
        frame = await VideoProcessor.extract_frame_at_timestamp(
            "input.mp4", 3.75, str(frame_output)
        )

    assert segment == str(segment_output)
    assert frame == str(frame_output)
    assert frame_output.read_bytes().startswith(b"\xff\xd8")
    assert "1.250" in commands[0]
    assert "2.500" in commands[0]
    assert "3.750" in commands[1]


@pytest.mark.asyncio
async def test_video_processor_segment_failure_surfaces_subprocess_error(tmp_path):
    output = tmp_path / "segments" / "missing.mp4"
    process = _Process(returncode=1, stderr=b"slice failed")
    commands = []
    with patch(
        "app.services.video_processor.asyncio.create_subprocess_exec",
        side_effect=_runner(process, commands),
    ):
        with pytest.raises(MediaAppException) as error:
            await VideoProcessor.extract_video_segment(
                "input.mp4", 0, 1, str(output)
            )
    assert error.value.details["stderr"] == "slice failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (b"1920,1080,30000/1001,12.3456\n", (1920, 1080, 29.97, 12.346)),
        (b",,,\n", (1920, 1080, 30.0, 60.0)),
        (b"1920,1080,__import__('os').system('whoami'),12.3456\n", (1920, 1080, 30.0, 12.346)),
        (b"1920,1080,30/0,12.3456\n", (1920, 1080, 30.0, 12.346)),
    ],
)
async def test_video_processor_reads_properties_and_defaults(stdout, expected):
    process = _Process(stdout=stdout, create_output=False)
    with patch(
        "app.services.video_processor.asyncio.create_subprocess_exec",
        return_value=process,
    ):
        assert await VideoProcessor.get_video_properties("input.mp4") == expected


@pytest.mark.asyncio
async def test_video_processor_property_probe_failure_returns_safe_defaults():
    with patch(
        "app.services.video_processor.asyncio.create_subprocess_exec",
        side_effect=OSError("missing executable"),
    ):
        assert await VideoProcessor.get_video_properties("input.mp4") == (
            1920,
            1080,
            30.0,
            60.0,
        )
