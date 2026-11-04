from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import expired, password_hash, verify_password
from app.permissions.policy import Authorization, Risk, ToolDefinition, authorize_tool


def test_password_storage_is_salted_and_wrong_password_is_rejected():
    first = password_hash("strong-password-123")
    second = password_hash("strong-password-123")
    assert first != second
    assert "strong-password" not in first
    assert verify_password("strong-password-123", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("strong-password-123", "malformed-record")


def test_expiry_handles_sqlite_naive_dates_and_aware_dates():
    assert expired(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert expired(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1))
    assert not expired(datetime.now(timezone.utc) + timedelta(minutes=1))


def test_green_actions_still_require_explicit_permission():
    light = ToolDefinition("office_light", Risk.GREEN)
    with pytest.raises(PermissionError):
        authorize_tool(light, Authorization("owner", frozenset()))
    authorize_tool(light, Authorization("owner", frozenset({"office_light"})))


@pytest.mark.parametrize("risk", [Risk.YELLOW, Risk.RED])
def test_model_supplied_confirmation_cannot_enable_restricted_actions(risk):
    tool = ToolDefinition("sensitive_action", risk)
    with pytest.raises(PermissionError):
        authorize_tool(tool, Authorization("owner", frozenset({"sensitive_action"})), confirmed=True)
