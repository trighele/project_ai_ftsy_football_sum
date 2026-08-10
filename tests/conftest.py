"""Shared fixtures.

Every test drives the application through its test client. The three network
edges are replaced at the dependency container, so nothing here touches the
network.
"""

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.config import DATA_DIR_VARIABLE
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.store import RunStore
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource


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


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the configured data directory at a temporary one.

    Autouse because a test that builds an application without saying where its
    database goes — `test_container.py` does, deliberately — would otherwise
    write into the working tree.
    """
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(tmp_path / "data"))


@pytest.fixture
def youtube() -> FakeYouTubeSource:
    """The captions edge, serving the fixture episode."""
    return FakeYouTubeSource()


@pytest.fixture
def container(youtube: FakeYouTubeSource) -> Container:
    """A container with all three network edges replaced by fakes."""
    container = Container()
    container.override(
        captions=youtube,
        nflverse=FakeNflverseSource(),
        claude=FakeClaudeClient(),
    )
    return container


@pytest.fixture
def app_store(tmp_path: Path) -> RunStore:
    """The run store the application under test saves to.

    A real SQLite file, not a fake: the store is not a network edge, and the
    behaviour worth testing is that what it writes comes back.
    """
    return RunStore(tmp_path / "runs.db")


@pytest.fixture
def app(container: Container, app_store: RunStore) -> FastAPI:
    return create_app(container=container, store=app_store)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
