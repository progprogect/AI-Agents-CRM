"""Pytest configuration for backend tests."""

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio only (trio is not a project dependency)."""
    return "asyncio"
