"""Shared fixtures.

Every test drives the application through its test client. The three network
edges are replaced at the dependency container, so nothing here touches the
network.
"""

import socket
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.container import Container


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if anything in the suite opens a socket.

    Every network edge is meant to be replaced by a fake, so a real connection
    attempt is a bug in the test, not a slow test.
    """

    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "This test tried to open a network connection. Override the "
            "relevant edge on the container with a fake instead."
        )

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


class FakeCaptionsSource:
    """Stand-in for the YouTube captions edge."""


class FakeNflverseSource:
    """Stand-in for the nflverse edge."""


class FakeClaudeClient:
    """Stand-in for the Claude client edge."""


@pytest.fixture
def container() -> Container:
    """A container with all three network edges replaced by fakes."""
    container = Container()
    container.override(
        captions=FakeCaptionsSource(),
        nflverse=FakeNflverseSource(),
        claude=FakeClaudeClient(),
    )
    return container


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container=container)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
