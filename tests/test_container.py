"""The dependency container exists so the three network edges can be swapped.

These tests pin that behaviour: an override is handed out in place of the real
implementation, and the real factory is never invoked when one is set.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.container import (
    EDGES,
    UNWIRED_EDGES,
    Container,
    EdgeNotWiredError,
)
from project_ai_ftsy_football_sum.services.claude import ClaudeClient
from project_ai_ftsy_football_sum.services.youtube import YouTubeSource


class RecordingFactory:
    """A stand-in for a real edge factory that records whether it was called."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return object()


@pytest.mark.parametrize("edge", EDGES)
def test_override_is_used_in_place_of_the_real_implementation(edge: str) -> None:
    real_factory = RecordingFactory()
    container = Container(factories={edge: real_factory})
    fake = object()

    container.override(**{edge: fake})

    assert container.resolve(edge) is fake
    assert real_factory.calls == 0


@pytest.mark.parametrize("edge", EDGES)
def test_real_factory_is_used_when_not_overridden_and_resolved_once(edge: str) -> None:
    real_factory = RecordingFactory()
    container = Container(factories={edge: real_factory})

    first = container.resolve(edge)
    second = container.resolve(edge)

    assert first is second
    assert real_factory.calls == 1


@pytest.mark.parametrize("edge", UNWIRED_EDGES)
def test_unwired_edge_reports_which_source_supplies_it(edge: str) -> None:
    container = Container()

    with pytest.raises(EdgeNotWiredError, match=edge):
        container.resolve(edge)


def test_the_captions_edge_resolves_to_the_real_youtube_source() -> None:
    """Building the edge must not open a connection — only using it does."""
    assert isinstance(Container().resolve("captions"), YouTubeSource)


def test_the_claude_edge_resolves_to_the_real_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")

    assert isinstance(Container().resolve("claude"), ClaudeClient)


def test_the_claude_edge_is_unavailable_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The readiness pill is the right place to learn the API key is missing.

    The SDK would not say so until the first request, which is halfway
    through somebody's run.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    with pytest.raises(Exception, match="ANTHROPIC_API_KEY"):
        Container().resolve("claude")


def test_unknown_edge_is_rejected() -> None:
    with pytest.raises(KeyError, match="postgres"):
        Container().resolve("postgres")  # type: ignore[arg-type]


def test_serving_a_page_does_not_resolve_any_edge() -> None:
    """Edges are network connections; rendering the home page must not open one."""
    factories = {edge: RecordingFactory() for edge in EDGES}
    container = Container(factories=factories)

    with TestClient(create_app(container=container)) as client:
        assert client.get("/").status_code == 200

    assert [factory.calls for factory in factories.values()] == [0, 0, 0]


def test_status_fragment_reports_ready_when_the_edges_are_overridden(
    client: TestClient,
) -> None:
    """The `client` fixture's container has all three edges replaced by fakes.

    Without the overrides the real (unwired) implementations are resolved and
    the pill reads "Not ready" — see the companion test below. That difference
    is the override taking effect, observed over HTTP.
    """
    response = client.get("/fragments/status")

    assert response.status_code == 200
    assert "Ready" in response.text
    assert "Not ready" not in response.text


def test_status_fragment_reports_not_ready_without_overrides() -> None:
    with TestClient(create_app(container=Container())) as unwired_client:
        response = unwired_client.get("/fragments/status")

    assert response.status_code == 200
    assert "Not ready" in response.text
    for edge in UNWIRED_EDGES:
        assert edge in response.text


def test_app_exposes_the_container_it_was_built_with(
    app: FastAPI, container: Container
) -> None:
    assert app.state.container is container


def test_create_app_without_a_container_builds_a_default_one() -> None:
    app = create_app()

    assert isinstance(app.state.container, Container)
