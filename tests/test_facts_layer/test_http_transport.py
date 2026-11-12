"""Guards for the one HTTP transport shared by the API clients (proposal 4)."""

import inspect

import pytest

from edcg.facts._http import ApiClient
from edcg.facts.inara import InaraClient
from edcg.facts.raven import RavenClient
from edcg.facts.spansh import SpanshClient


def test_every_client_uses_the_shared_transport_base():
    """A client that stops inheriting ApiClient has re-grown its own transport."""
    for client in (RavenClient, SpanshClient, InaraClient):
        assert issubclass(client, ApiClient), client.__name__
        assert ApiClient in client.__mro__, client.__name__


def test_retry_lives_only_on_the_shared_base():
    """Retry/backoff is one policy: no client may define its own."""
    for client in (RavenClient, SpanshClient, InaraClient):
        assert "_request_with_retry" not in client.__dict__, client.__name__

    assert ApiClient._request_with_retry.__qualname__ == "ApiClient._request_with_retry"
    source = inspect.getsourcefile(ApiClient._request_with_retry)
    assert source is not None
    assert source.replace("\\", "/").endswith("facts/_http.py"), source


def test_default_headers_are_read_only():
    """The shared base's header mapping is frozen, not mutable module state."""
    with pytest.raises(TypeError):
        ApiClient.default_headers["X-Probe"] = "written"  # type: ignore[index]
