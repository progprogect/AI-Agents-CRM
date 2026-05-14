"""Smoke tests for admin end-users API models."""

from __future__ import annotations

from app.api.v1.admin import EndUserRow, EndUsersPageResponse


def test_end_user_row_and_page_response_roundtrip() -> None:
    row = EndUserRow(
        agent_id="agent-1",
        agent_display_name="Мой агент",
        channel="telegram",
        external_user_id="999888777",
        display_name="Иван",
        username="ivan_user",
        last_seen_at="2026-05-01T12:00:00+00:00",
        conversation_count=2,
    )
    page = EndUsersPageResponse(total=1, items=[row])
    dumped = page.model_dump()
    assert dumped["total"] == 1
    assert dumped["items"][0]["external_user_id"] == "999888777"
    assert dumped["items"][0]["conversation_count"] == 2
