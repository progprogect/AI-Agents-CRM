"""Tests for Cloudinary RAG import (prefix guard, dedup, happy path). Run: cd backend && pytest tests/test_cloudinary_rag_import.py -v"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_admin
from app.api.v1 import rag as rag_module
from app.dependencies import CommonDependencies
from app.services.cloudinary_browse import public_id_allowed


def _settings_mock():
    s = MagicMock()
    s.database_backend = "postgres"
    s.storage_backend = "cloudinary"
    s.cloudinary_folder = "rag"
    return s


def _make_test_client(settings_obj) -> TestClient:
    app = FastAPI()
    app.include_router(rag_module.router, prefix="/api/v1/agents", tags=["rag"])

    async def override_admin() -> str:
        return "test"

    def override_common() -> CommonDependencies:
        mock_db = MagicMock()
        mock_db.get_agent = AsyncMock(return_value={"id": "agent1", "config": {}})
        mock_cache = MagicMock()
        return CommonDependencies(config=settings_obj, dynamodb=mock_db, cache=mock_cache)

    app.dependency_overrides[get_current_admin] = override_admin
    app.dependency_overrides[CommonDependencies] = override_common
    return TestClient(app)


@pytest.fixture
def settings_obj():
    return _settings_mock()


def test_public_id_allowed():
    assert public_id_allowed("rag/a1/file", "rag/a1") is True
    assert public_id_allowed("rag/a1", "rag/a1") is True
    assert public_id_allowed("other/x", "rag/a1") is False
    assert public_id_allowed("rag/a1x", "rag/a1") is False


@patch.object(rag_module, "get_settings")
def test_import_rejects_public_id_outside_prefix(mock_get_settings, settings_obj):
    mock_get_settings.return_value = settings_obj
    client = _make_test_client(settings_obj)
    body = {
        "items": [{"public_id": "other/account/doc", "resource_type": "raw", "format": "pdf"}],
        "allowed_prefix": "rag/agent1",
    }
    r = client.post("/api/v1/agents/agent1/rag/documents/import-from-cloudinary", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["status"] == "error"
    assert "rag/agent1" in data["results"][0]["message"]


@patch.object(rag_module, "get_settings")
@patch.object(rag_module, "get_postgres_rag_client")
@patch.object(rag_module, "build_secure_url")
@patch.object(rag_module, "download_url_bytes", new_callable=AsyncMock)
@patch.object(rag_module, "index_rag_document_core", new_callable=AsyncMock)
@patch.object(rag_module, "new_rag_document_id")
def test_import_duplicate_skips_indexing(
    mock_new_id,
    mock_index,
    mock_dl,
    mock_build_url,
    mock_get_rag,
    mock_get_settings,
    settings_obj,
):
    mock_get_settings.return_value = settings_obj
    mock_new_id.return_value = "new-id"
    rag = MagicMock()
    rag.get_document_id_by_file_url = AsyncMock(return_value="dup-doc-id")
    mock_get_rag.return_value = rag
    mock_build_url.return_value = "https://res.cloudinary.com/x/raw/upload/v1/rag/agent1/a.pdf"

    client = _make_test_client(settings_obj)
    body = {
        "items": [{"public_id": "rag/agent1/a", "resource_type": "raw", "format": "pdf"}],
        "allowed_prefix": "rag/agent1",
    }
    r = client.post("/api/v1/agents/agent1/rag/documents/import-from-cloudinary", json=body)
    assert r.status_code == 200
    out = r.json()["results"][0]
    assert out["status"] == "duplicate"
    assert out["document_id"] == "dup-doc-id"
    mock_dl.assert_not_called()
    mock_index.assert_not_called()


@patch.object(rag_module, "get_settings")
@patch.object(rag_module, "get_postgres_rag_client")
@patch.object(rag_module, "build_secure_url")
@patch.object(rag_module, "download_url_bytes", new_callable=AsyncMock)
@patch.object(rag_module, "index_rag_document_core", new_callable=AsyncMock)
@patch.object(rag_module, "new_rag_document_id")
def test_import_ok_indexes_bytes(
    mock_new_id,
    mock_index,
    mock_dl,
    mock_build_url,
    mock_get_rag,
    mock_get_settings,
    settings_obj,
):
    mock_get_settings.return_value = settings_obj
    mock_new_id.return_value = "doc-new"
    rag = MagicMock()
    rag.get_document_id_by_file_url = AsyncMock(return_value=None)
    mock_get_rag.return_value = rag
    mock_build_url.return_value = "https://res.cloudinary.com/x/raw/upload/v1/rag/agent1/b.pdf"
    mock_dl.return_value = b"%PDF-1.4 fake"
    mock_index.return_value = {
        "document_id": "doc-new",
        "title": "b",
        "file_type": "pdf",
        "file_url": mock_build_url.return_value,
    }

    client = _make_test_client(settings_obj)
    body = {
        "items": [{"public_id": "rag/agent1/b", "resource_type": "raw", "format": "pdf"}],
        "allowed_prefix": "rag/agent1",
    }
    r = client.post("/api/v1/agents/agent1/rag/documents/import-from-cloudinary", json=body)
    assert r.status_code == 200
    out = r.json()["results"][0]
    assert out["status"] == "ok"
    assert out["document_id"] == "doc-new"
    mock_dl.assert_called_once()
    mock_index.assert_called_once()
