"""The real nflverse edge, exercised without the network.

The second and last place the suite steps inside the HTTP boundary. It has to:
the retry is by design invisible from outside the application — a sync that
survived a reset connection renders exactly the page a sync that never hit one
does. The loader and the sleep are handed in; everything else about the class
is real.

The assertions are about what the edge did, not how it decided to: how many
times the loader was called, what came back, and how long it claimed to wait.
"""

from typing import Any

import pytest
import requests

from project_ai_ftsy_football_sum.config import data_dir
from project_ai_ftsy_football_sum.services.nflverse import NflverseSource, cache_settings
from project_ai_ftsy_football_sum.services.players import CACHE_TTL


class FakeLoader:
    """Stands in for `nflreadpy`, serving a scripted answer per call.

    Each entry in `answers` is either an exception to raise or a value to
    return, taken in order; the last entry is repeated once exhausted.
    """

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _answer(self, name: str, *args: Any) -> Any:
        self.calls.append((name, args))
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def load_depth_charts(self, season: int) -> Any:
        return self._answer("load_depth_charts", season)

    def load_players(self) -> Any:
        return self._answer("load_players")

    def load_ff_rankings(self, page: str) -> Any:
        return self._answer("load_ff_rankings", page)

    def load_injuries(self, season: int) -> Any:
        return self._answer("load_injuries", season)


class FakeSleep:
    """Records what it was asked to wait for, and waits for none of it."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def wrapped(cause: Exception) -> ConnectionError:
    """A failure as the library hands it on.

    Every `requests` failure reaches us wrapped in one `ConnectionError`
    naming the URL, with the real one chained underneath it — which is why the
    class alone cannot say whether asking again is worth anything.
    """
    failure = ConnectionError("Failed to download depth_charts_2026.parquet")
    failure.__cause__ = cause
    return failure


def dropped_connection() -> ConnectionError:
    """What the library raises when GitHub resets a parquet download."""
    return wrapped(ConnectionResetError(104, "Connection reset by peer"))


def source(loader: FakeLoader, sleep: FakeSleep) -> NflverseSource:
    return NflverseSource(loader=loader, sleep=sleep)


def test_a_dropped_connection_is_retried_until_it_succeeds() -> None:
    loader = FakeLoader(dropped_connection(), dropped_connection(), "the frame")
    sleep = FakeSleep()

    frame = source(loader, sleep).depth_charts(2026)

    assert frame == "the frame"
    assert [name for name, _ in loader.calls] == ["load_depth_charts"] * 3
    assert len(sleep.waits) == 2


def http_error(status: int) -> ConnectionError:
    """What the library raises for a status GitHub answered with.

    A 404 is the ordinary preseason answer for the current season's depth
    charts, and it arrives wrapped exactly like a reset does.
    """
    response = requests.Response()
    response.status_code = status
    return wrapped(requests.exceptions.HTTPError(response=response))


def test_a_missing_season_is_not_asked_for_twice() -> None:
    loader = FakeLoader(http_error(404))
    sleep = FakeSleep()

    with pytest.raises(ConnectionError):
        source(loader, sleep).depth_charts(2026)

    assert len(loader.calls) == 1
    assert sleep.waits == []


def test_a_refused_season_raises_without_being_asked_again() -> None:
    """The library's own refusal, which no amount of asking will change."""
    loader = FakeLoader(ValueError("Season must be between 2009 and 2026"))
    sleep = FakeSleep()

    with pytest.raises(ValueError):
        source(loader, sleep).injuries(2026)

    assert len(loader.calls) == 1
    assert sleep.waits == []


def test_a_server_error_is_retried() -> None:
    loader = FakeLoader(http_error(503), "the frame")
    sleep = FakeSleep()

    assert source(loader, sleep).players() == "the frame"
    assert len(loader.calls) == 2


def test_three_dropped_connections_raise_the_last_of_them() -> None:
    last = dropped_connection()
    loader = FakeLoader(dropped_connection(), dropped_connection(), last)
    sleep = FakeSleep()

    with pytest.raises(ConnectionError) as raised:
        source(loader, sleep).players()

    assert raised.value is last
    assert len(loader.calls) == 3
    assert len(sleep.waits) == 2


def test_each_wait_is_longer_than_the_one_before_it() -> None:
    sleep = FakeSleep()
    loader = FakeLoader(dropped_connection())

    with pytest.raises(ConnectionError):
        source(loader, sleep).fantasy_rankings()

    assert sleep.waits[0] > 0
    assert sleep.waits[1] > sleep.waits[0]


def test_each_table_is_asked_of_the_loader_that_holds_it() -> None:
    loader = FakeLoader("the frame")
    edge = source(loader, FakeSleep())

    edge.depth_charts(2026)
    edge.players()
    edge.fantasy_rankings()
    edge.injuries(2025)

    assert loader.calls == [
        ("load_depth_charts", (2026,)),
        ("load_players", ()),
        ("load_ff_rankings", ("draft",)),
        ("load_injuries", (2025,)),
    ]


def test_downloaded_tables_are_kept_on_the_configured_data_directory() -> None:
    settings = cache_settings()

    assert settings["cache_mode"] == "filesystem"
    assert data_dir() in settings["cache_dir"].parents
    assert settings["cache_duration"] == CACHE_TTL.total_seconds()
    assert settings["timeout"] > 30
