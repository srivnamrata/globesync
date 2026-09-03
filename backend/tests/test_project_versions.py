from app.schemas.projects import ProjectDraftPutRequest
from app.services.project_service import ProjectService


def test_project_version_payload_hash_is_order_independent() -> None:
    first = {"translations": [{"id": "segment-1", "text": "Hello"}], "timelineState": {"zoomLevel": 100}}
    reordered = {"timelineState": {"zoomLevel": 100}, "translations": [{"id": "segment-1", "text": "Hello"}]}

    assert ProjectService._hash_payload(first) == ProjectService._hash_payload(reordered)


def test_project_draft_checkpoint_reason_is_optional_for_autosave() -> None:
    request = ProjectDraftPutRequest(
        version=1,
        draft_schema_version="heygenx/v1",
        draft_payload={"projectMetadata": {"id": "project-1"}},
    )

    assert request.checkpoint_reason is None


def test_project_draft_accepts_meaningful_checkpoint_reason() -> None:
    request = ProjectDraftPutRequest(
        version=2,
        draft_schema_version="heygenx/v1",
        draft_payload={"projectMetadata": {"id": "project-1"}},
        checkpoint_reason="pre_build",
    )

    assert request.checkpoint_reason == "pre_build"


def test_legacy_hash_does_not_duplicate_equal_checkpoint_payload() -> None:
    payload = {"projectMetadata": {"id": "project-1"}}
    legacy_version = type("LegacyVersion", (), {"payload_hash": "legacy-md5-hash", "draft_payload": payload})()
    current_hash = ProjectService._hash_payload(payload)

    assert ProjectService._checkpoint_matches(legacy_version, current_hash, payload) is True
