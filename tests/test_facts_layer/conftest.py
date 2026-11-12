"""Fixtures shared by the facts-layer tests.

The three network clients all need the same shape: an ``AsyncMock`` that also
works as an async context manager, because ``gather_facts`` opens each client
with ``async with``. One factory owns that shape so the three fixtures cannot
drift.
"""

from unittest.mock import AsyncMock

import pytest


def async_mock_client() -> AsyncMock:
    """An ``AsyncMock`` wired as an async context manager returning itself."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_raven_client():
    """A stand-in RavenClient."""
    return async_mock_client()


@pytest.fixture
def mock_inara_client():
    """A stand-in InaraClient."""
    return async_mock_client()


@pytest.fixture
def mock_spansh_client():
    """A stand-in SpanshClient."""
    return async_mock_client()
