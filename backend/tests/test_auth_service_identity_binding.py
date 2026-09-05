from types import SimpleNamespace

import pytest

from app.services.auth_service import AccountAccessError, AuthService, ResolvedIdentity


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.flush_count = 0

    async def execute(self, statement):
        return _ScalarResult(next(self._results))

    async def flush(self):
        self.flush_count += 1


def _identity(subject="new-subject"):
    return ResolvedIdentity(
        email="user@example.com",
        display_name="User",
        auth_subject=subject,
        auth_provider="identity_platform",
    )


@pytest.mark.asyncio
async def test_rejects_email_match_bound_to_different_subject():
    existing_user = SimpleNamespace(
        email="user@example.com",
        display_name="Former User",
        auth_provider="identity_platform",
        auth_subject="old-subject",
        is_active=True,
    )
    session = _FakeSession([None, existing_user])

    with pytest.raises(AccountAccessError, match="not linked"):
        await AuthService()._get_or_create_user(session, _identity())

    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_rejects_inactive_user_with_matching_subject():
    existing_user = SimpleNamespace(
        email="user@example.com",
        display_name="Disabled User",
        auth_provider="identity_platform",
        auth_subject="new-subject",
        is_active=False,
    )
    session = _FakeSession([existing_user])

    with pytest.raises(AccountAccessError, match="inactive"):
        await AuthService()._get_or_create_user(session, _identity())

    assert existing_user.is_active is False
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_binds_subject_to_unbound_same_provider_account():
    existing_user = SimpleNamespace(
        email="user@example.com",
        display_name="Legacy User",
        auth_provider="identity_platform",
        auth_subject=None,
        is_active=True,
        last_login_at=None,
        updated_at=None,
    )
    session = _FakeSession([None, existing_user])

    result = await AuthService()._get_or_create_user(session, _identity())

    assert result is existing_user
    assert existing_user.auth_subject == "new-subject"
    assert session.flush_count == 1
