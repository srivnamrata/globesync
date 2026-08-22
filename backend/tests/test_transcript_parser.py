import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.utils.transcript_parser import transcript_parser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deepgram_mock_response.json"


def load_payload() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_parse_deepgram_response_from_saved_json_fixture() -> None:
    payload = load_payload()

    segments, full_text, avg_confidence, word_count, speaker_count = transcript_parser.parse_deepgram_response(payload)

    assert len(segments) == 2
    assert full_text == "Hello and welcome to the global launch presentation. Thank you for joining us today."
    assert avg_confidence == 0.9807
    assert word_count == 14
    assert speaker_count == 2

    assert segments[0].speaker == "Speaker 1"
    assert segments[0].start_time == 0.5
    assert segments[0].end_time == 4.1
    assert segments[0].text == "Hello and welcome to the global launch presentation."
    assert [word.text for word in segments[0].words[:3]] == ["Hello", "and", "welcome"]

    assert segments[1].speaker == "Speaker 2"
    assert segments[1].start_time == 5.0
    assert segments[1].end_time == 7.4
    assert segments[1].text == "Thank you for joining us today."
    assert [word.text for word in segments[1].words] == ["Thank", "you", "for", "joining", "us", "today."]


def test_export_formats_from_saved_json_fixture() -> None:
    payload = load_payload()
    segments, _, _, _, _ = transcript_parser.parse_deepgram_response(payload)

    dialogue_output = transcript_parser.export_to_dialogue_format(segments)
    srt_output = transcript_parser.export_to_srt(segments)
    vtt_output = transcript_parser.export_to_vtt(segments)

    assert '[00:00:00] Speaker 1: "Hello and welcome to the global launch presentation."' in dialogue_output
    assert '[00:00:05] Speaker 2: "Thank you for joining us today."' in dialogue_output

    assert "1\n00:00:00,500 --> 00:00:04,100\n[Speaker 1] Hello and welcome to the global launch presentation.\n" in srt_output
    assert "2\n00:00:05,000 --> 00:00:07,400\n[Speaker 2] Thank you for joining us today.\n" in srt_output

    assert vtt_output.startswith("WEBVTT")
    assert "00:00:00.500 --> 00:00:04.100" in vtt_output
    assert "<v Speaker 2>Thank you for joining us today." in vtt_output
