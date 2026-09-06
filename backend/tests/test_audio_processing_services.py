import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.audio_extraction_service import AudioExtractor
from app.services.audio_postprocessor import AudioPostProcessor
from app.services.audio_preprocessing_service import AudioPreprocessor
from app.utils.error_codes import MediaAppException


class _Process:
    def __init__(self, returncode=0, stdout=b"", stderr=b"", create_output=False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.create_output = create_output
        self.command = None

    async def communicate(self):
        if self.create_output and self.command:
            Path(self.command[-1]).write_bytes(b"audio")
        return self.stdout, self.stderr


def _process_factory(*processes):
    remaining = list(processes)
    commands = []

    async def create(*command, **kwargs):
        process = remaining.pop(0)
        process.command = command
        commands.append(command)
        return process

    return create, commands


@pytest.mark.asyncio
async def test_extract_audio_for_stt_builds_pcm_command_and_default_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.audio_extraction_service.settings.PROCESSED_MEDIA_DIR",
        str(tmp_path),
    )
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_extraction_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioExtractor.extract_audio_for_stt(
            "recording.mp4",
            sample_rate=22050,
            channels=2,
        )

    assert result == str(tmp_path / "recording_stt_16k.wav")
    assert commands[0] == (
        "ffmpeg",
        "-y",
        "-i",
        "recording.mp4",
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "22050",
        "-ac",
        "2",
        result,
    )


@pytest.mark.asyncio
async def test_extract_audio_for_stt_reports_ffmpeg_failure(tmp_path):
    output = tmp_path / "missing.wav"
    create, _ = _process_factory(_Process(returncode=1, stderr=b"no audio stream"))

    with patch(
        "app.services.audio_extraction_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        with pytest.raises(MediaAppException) as error:
            await AudioExtractor.extract_audio_for_stt("video.mp4", str(output))

    assert error.value.details["stderr"] == "no audio stream"


@pytest.mark.asyncio
async def test_extract_segment_falls_back_to_pcm_on_copy_failure(tmp_path):
    output = tmp_path / "segments" / "part.wav"
    create, commands = _process_factory(
        _Process(returncode=1),
        _Process(create_output=True),
    )

    with patch(
        "app.services.audio_extraction_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioExtractor.extract_audio_segment(
            "source.wav",
            1.2345,
            2.3456,
            str(output),
        )

    assert result == str(output)
    assert commands[0][2:6] == ("-ss", "1.234", "-i", "source.wav")
    assert "copy" in commands[0]
    assert "pcm_s16le" in commands[1]


@pytest.mark.asyncio
async def test_extract_segment_raises_when_fallback_does_not_create_output(tmp_path):
    output = tmp_path / "part.wav"
    create, _ = _process_factory(
        _Process(returncode=1),
        _Process(returncode=0, stderr=b"empty output"),
    )

    with patch(
        "app.services.audio_extraction_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        with pytest.raises(MediaAppException) as error:
            await AudioExtractor.extract_audio_segment("source.wav", 0, 1, str(output))

    assert error.value.details["stderr"] == "empty output"


@pytest.mark.asyncio
async def test_convert_to_web_audio_uses_requested_bitrate(tmp_path):
    output = tmp_path / "web.mp3"
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_extraction_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioExtractor.convert_to_web_audio(
            "input.wav",
            str(output),
            bitrate_kbps=192,
        )

    assert result == str(output)
    assert commands[0][commands[0].index("-b:a") + 1] == "192k"


@pytest.mark.asyncio
async def test_preprocess_audio_builds_optional_filter_chain(tmp_path):
    output = tmp_path / "processed.wav"
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_preprocessing_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioPreprocessor.preprocess_audio_pipeline(
            "input.wav",
            str(output),
            apply_noise_reduction=False,
            apply_loudness_norm=False,
        )

    assert result == str(output)
    assert commands[0][commands[0].index("-af") + 1] == "anull"


@pytest.mark.asyncio
async def test_preprocess_audio_includes_noise_and_loudness_filters(tmp_path):
    output = tmp_path / "processed.wav"
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_preprocessing_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        await AudioPreprocessor.preprocess_audio_pipeline(
            "input.wav",
            str(output),
            target_lufs=-18,
        )

    filters = commands[0][commands[0].index("-af") + 1]
    assert filters == (
        "highpass=f=80,lowpass=f=7500,afftdn=nf=-25,"
        "loudnorm=I=-18:LRA=11:TP=-1.5"
    )


@pytest.mark.asyncio
async def test_preprocess_audio_raises_when_output_is_missing(tmp_path):
    create, _ = _process_factory(_Process(stderr=b"filter rejected"))

    with patch(
        "app.services.audio_preprocessing_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        with pytest.raises(MediaAppException) as error:
            await AudioPreprocessor.preprocess_audio_pipeline(
                "input.wav",
                str(tmp_path / "missing.wav"),
            )

    assert error.value.details["stderr"] == "filter rejected"


@pytest.mark.asyncio
async def test_silence_detection_pairs_only_ordered_start_end_events():
    stderr = b"\n".join(
        [
            b"[silencedetect] silence_end: 0.25 | silence_duration: 0.25",
            b"[silencedetect] silence_start: 1.5",
            b"[silencedetect] silence_end: 2.75 | silence_duration: 1.25",
            b"[silencedetect] silence_start: 8.0",
            b"[silencedetect] silence_end: 9.0 | silence_duration: 1.0",
        ]
    )
    create, commands = _process_factory(_Process(stderr=stderr))

    with patch(
        "app.services.audio_preprocessing_service.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioPreprocessor.detect_silence_segments(
            "input.wav",
            noise_threshold_db=-35,
            min_silence_duration_sec=0.75,
        )

    assert result == [(1.5, 2.75), (8.0, 9.0)]
    assert "silencedetect=noise=-35dB:d=0.75" in commands[0]


@pytest.mark.asyncio
async def test_chunking_returns_original_for_short_audio():
    with patch.object(
        AudioPreprocessor,
        "detect_silence_segments",
        new=AsyncMock(),
    ) as detect:
        result = await AudioPreprocessor.split_audio_into_chunks_if_needed(
            "short.wav",
            90,
            max_chunk_duration_sec=120,
        )

    assert result == [("short.wav", 0.0, 90)]
    detect.assert_not_awaited()


@pytest.mark.asyncio
async def test_chunking_uses_nearby_silence_and_exact_final_duration(tmp_path):
    source = tmp_path / "long.wav"
    source.write_bytes(b"source")
    create, commands = _process_factory(_Process(), _Process())

    with (
        patch.object(
            AudioPreprocessor,
            "detect_silence_segments",
            new=AsyncMock(return_value=[(95.0, 97.0)]),
        ),
        patch(
            "app.services.audio_preprocessing_service.asyncio.create_subprocess_exec",
            side_effect=create,
        ),
    ):
        chunks = await AudioPreprocessor.split_audio_into_chunks_if_needed(
            str(source),
            total_duration_sec=180,
            max_chunk_duration_sec=100,
        )

    assert chunks == [
        (str(tmp_path / "long_chunk_0.wav"), 0.0, 96.0),
        (str(tmp_path / "long_chunk_1.wav"), 96.0, 84.0),
    ]
    assert commands[0][commands[0].index("-t") + 1] == "96.000"
    assert commands[1][commands[1].index("-ss") + 1] == "96.000"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("speed", "expected"),
    [
        (2.6, "atempo=2.0,atempo=1.3"),
        (0.4, "atempo=0.5,atempo=0.8"),
        (1.25, "atempo=1.250"),
    ],
)
async def test_retime_builds_supported_atempo_chains(tmp_path, speed, expected):
    output = tmp_path / f"retimed-{speed}.wav"
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        await AudioPostProcessor.retime_and_normalize_segment(
            "input.wav",
            str(output),
            speed_factor=speed,
            pitch_adjustment_semitones=2,
            room_reverb_config={"in_gain": 0.7, "out_gain": 0.8, "delays": 30, "decays": 0.2},
        )

    filters = commands[0][commands[0].index("-af") + 1]
    assert expected in filters
    assert "asetrate=" in filters
    assert "aecho=0.7:0.8:30:0.2" in filters
    assert filters.endswith("loudnorm=I=-20:LRA=11:TP=-1.5")


@pytest.mark.asyncio
async def test_retime_reports_missing_output(tmp_path):
    create, _ = _process_factory(_Process(returncode=0, stderr=b"no file"))

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        with pytest.raises(MediaAppException) as error:
            await AudioPostProcessor.retime_and_normalize_segment(
                "input.wav",
                str(tmp_path / "missing.wav"),
            )

    assert error.value.details["stderr"] == "no file"


@pytest.mark.asyncio
async def test_audio_duration_reads_wav_header_and_handles_missing(tmp_path):
    wav_path = tmp_path / "duration.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 8000)

    assert await AudioPostProcessor.get_audio_duration_ms(str(wav_path)) == 500
    assert await AudioPostProcessor.get_audio_duration_ms(str(tmp_path / "missing.wav")) == 0


@pytest.mark.asyncio
async def test_audio_duration_falls_back_to_ffprobe_and_safe_default(tmp_path):
    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not-wave")
    create, _ = _process_factory(_Process(stdout=b"1.75\n"), _Process(stdout=b"invalid"))

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        assert await AudioPostProcessor.get_audio_duration_ms(str(invalid)) == 1750
        assert await AudioPostProcessor.get_audio_duration_ms(str(invalid)) == 1000


@pytest.mark.asyncio
async def test_timeline_without_segments_generates_silence(tmp_path):
    output = tmp_path / "master.wav"
    create, commands = _process_factory(_Process())

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioPostProcessor.assemble_master_dubbed_timeline(
            [],
            12.3456,
            str(output),
        )

    assert result == str(output)
    assert "anullsrc=r=16000:cl=mono" in commands[0]
    assert commands[0][commands[0].index("-t") + 1] == "12.346"


@pytest.mark.asyncio
async def test_timeline_mixes_existing_segments_and_skips_missing(tmp_path):
    segment = tmp_path / "segment.wav"
    segment.write_bytes(b"audio")
    output = tmp_path / "master.wav"
    create, commands = _process_factory(_Process(create_output=True))

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioPostProcessor.assemble_master_dubbed_timeline(
            [
                {"audio_path": str(segment), "start_sec": 1.25},
                {"audio_path": str(tmp_path / "missing.wav"), "start_sec": 3},
            ],
            5,
            str(output),
        )

    assert result == str(output)
    command = commands[0]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "adelay=1250|1250" in filter_graph
    assert "amix=inputs=2" in filter_graph
    assert str(tmp_path / "missing.wav") not in command


@pytest.mark.asyncio
async def test_timeline_failure_uses_concat_fallback_and_removes_manifest(tmp_path):
    segment = tmp_path / "segment.wav"
    segment.write_bytes(b"audio")
    output = tmp_path / "master.wav"
    create, commands = _process_factory(_Process(returncode=1), _Process())

    with patch(
        "app.services.audio_postprocessor.asyncio.create_subprocess_exec",
        side_effect=create,
    ):
        result = await AudioPostProcessor.assemble_master_dubbed_timeline(
            [{"audio_path": str(segment), "start_sec": 0}],
            5,
            str(output),
        )

    assert result == str(output)
    manifest = Path(f"{output}.concat.txt")
    assert not manifest.exists()
    assert commands[1][0:6] == ("ffmpeg", "-y", "-f", "concat", "-safe", "0")
