"""Questionnaire submission list: API validation, escape helper, repo guard for bad field_key."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_admin
from app.api.v1 import questionnaires as qmod
from app.storage.postgres_questionnaire import escape_ilike_pattern


@pytest.fixture
def q_client() -> TestClient:
    app = FastAPI()
    app.include_router(qmod.router, prefix="/api/v1/admin")

    async def _admin() -> str:
        return "tester"

    app.dependency_overrides[get_current_admin] = _admin
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_escape_ilike_pattern_escapes_metacharacters() -> None:
    assert escape_ilike_pattern("a%b_c\\d") == "a\\%b\\_c\\\\d"


@pytest.mark.asyncio
async def test_list_submissions_invalid_field_key_returns_empty_without_db() -> None:
    from app.storage import postgres_questionnaire as pq

    rows = await pq.list_submissions(
        "any-agent-id",
        field_key="InvalidKey",
        value_search="foo",
    )
    assert rows == []


@patch.object(qmod.repo, "list_submissions", new_callable=AsyncMock)
def test_api_submissions_passes_filters(mock_list: AsyncMock, q_client: TestClient) -> None:
    mock_list.return_value = []
    r = q_client.get(
        "/api/v1/admin/agents/a1/questionnaire/submissions",
        params={
            "field_key": "pet_name",
            "value_search": "rex",
            "sort": "completed_at_desc",
        },
    )
    assert r.status_code == 200
    mock_list.assert_awaited_once()
    assert mock_list.await_args.args[0] == "a1"
    kwargs = mock_list.await_args.kwargs
    assert kwargs["field_key"] == "pet_name"
    assert kwargs["value_search"] == "rex"
    assert kwargs["sort"] == "completed_at_desc"


@patch.object(qmod.repo, "list_submissions", new_callable=AsyncMock)
def test_api_invalid_sort(mock_list: AsyncMock, q_client: TestClient) -> None:
    r = q_client.get("/api/v1/admin/agents/a1/questionnaire/submissions?sort=bad")
    assert r.status_code == 400
    mock_list.assert_not_called()


@patch.object(qmod.repo, "list_submissions", new_callable=AsyncMock)
def test_api_invalid_field_key(mock_list: AsyncMock, q_client: TestClient) -> None:
    r = q_client.get("/api/v1/admin/agents/a1/questionnaire/submissions?field_key=Invalid")
    assert r.status_code == 400
    mock_list.assert_not_called()


@patch.object(qmod.repo, "list_submissions", new_callable=AsyncMock)
def test_api_value_search_too_long(mock_list: AsyncMock, q_client: TestClient) -> None:
    r = q_client.get(
        "/api/v1/admin/agents/a1/questionnaire/submissions",
        params={"value_search": "x" * 201},
    )
    assert r.status_code == 400
    mock_list.assert_not_called()


@patch.object(qmod.repo, "list_distinct_response_field_keys", new_callable=AsyncMock)
def test_response_field_keys_endpoint(mock_keys: AsyncMock, q_client: TestClient) -> None:
    mock_keys.return_value = ["age", "legacy_field"]
    r = q_client.get("/api/v1/admin/agents/ag1/questionnaire/response-field-keys")
    assert r.status_code == 200
    assert r.json() == ["age", "legacy_field"]
    mock_keys.assert_awaited_once_with("ag1")
