"""The real nflverse edge: four tables from nflreadpy, retried when the wire drops.

This is the implementation the container resolves for the `nflverse` edge, and
the only place in the application that imports `nflreadpy` or sees a Polars
frame on its way out. Every decision about what the four tables mean lives in
`players.py`, which needs no network to be tested; only the calls, the retry
around them, and the staleness window they borrow from it are here.

GitHub, where nflverse publishes its releases, resets a connection partway
through a multi-megabyte parquet download often enough to notice. Retrying that
is a transport concern and so lives here, beside the calls it wraps, rather
than in the module that reads the tables — the same reason the captions edge
owns its own oEmbed fallback. Nothing above this class knows a retry happened:
a sync that survived a reset renders the page a sync that never hit one does.

`nflreadpy` is imported at module scope, which costs nothing until an edge is
resolved: the container imports this module inside its factory, so nothing that
does not do a sync ever pays for Polars.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import nflreadpy

from project_ai_ftsy_football_sum import config
from project_ai_ftsy_football_sum.services.players import CACHE_TTL

#: How many times a table is asked for before the failure is the reader's.
#: Three is enough to ride out a reset without making a genuine outage feel
#: like a hang.
MAX_ATTEMPTS = 3

#: The wait after a first failure, in seconds. It doubles each time.
BACKOFF_SECONDS = 1.0

#: How much of a wait is added at random, as a fraction of it. Enough that two
#: syncs started together stop retrying in lockstep, small enough that the
#: waits still grow.
BACKOFF_JITTER = 0.25

#: How long to wait on the download itself. The library's thirty-second
#: default is tight for a multi-megabyte parquet on a domestic connection.
DOWNLOAD_TIMEOUT_SECONDS = 120


class NflverseSource:
    """Everything the app asks nflverse for, in one place.

    Four tables, each answering one question about a player: where they are on
    the depth chart, who they are, what the experts think they are worth, and
    whether they are hurt. Each is asked for through `_fetch`, which is where
    a dropped connection is asked again.

    The loader and the sleep are injectable so the retry can be asserted on
    without the network and without waiting in real time; every other test
    replaces this whole class with a fake.
    """

    def __init__(
        self,
        *,
        loader: Any | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._loader = loader if loader is not None else _configured_loader()
        self._sleep = sleep if sleep is not None else time.sleep

    def depth_charts(self, season: int) -> Any:
        """Every depth chart published during a season. Depth rank lives here."""
        return self._fetch(lambda: self._loader.load_depth_charts(season))

    def players(self) -> Any:
        """Identity: the name, position, and team nflverse knows a player by."""
        return self._fetch(self._loader.load_players)

    def fantasy_rankings(self) -> Any:
        """Expert consensus rankings. ECR rank and the bye week live here."""
        return self._fetch(lambda: self._loader.load_ff_rankings("draft"))

    def injuries(self, season: int) -> Any:
        """Weekly injury reports, and the one call that refuses a season.

        nflverse rejects a season that has not kicked off yet, which in the
        preseason is the season whose depth charts we are reading — see
        `players._optional_records` for what is done about it.
        """
        return self._fetch(lambda: self._loader.load_injuries(season))

    def _fetch(self, call: Callable[[], Any]) -> Any:
        """One table, asked for again while the failure is worth asking again.

        The last attempt is made outside the loop, so the failure the caller
        sees is the last one rather than the first: that is the state of the
        network when we gave up on it.
        """
        for attempt in range(1, MAX_ATTEMPTS):
            try:
                return call()
            except Exception as error:
                if not _is_transient(error):
                    raise
                self._sleep(_backoff(attempt))
        return call()


def _backoff(attempt: int) -> float:
    """How long to wait after `attempt` failures: a second, then two, jittered."""
    wait = BACKOFF_SECONDS * 2 ** (attempt - 1)
    return wait + wait * BACKOFF_JITTER * random.random()


def _is_transient(error: Exception) -> bool:
    """Whether asking again could plausibly answer differently.

    The library wraps every `requests` failure in a single `ConnectionError`
    naming the URL, so the class alone says nothing and the chained cause is
    what gets read: a reset, a timeout and an HTTP 5xx are all worth asking
    again; a status the server meant is not. Its `ValueError` — a season
    outside the range it holds, or a payload it could not parse — is not
    wrapped that way at all and never retries.

    A 404 is the load-bearing case: it is the *normal* preseason answer for the
    current season's depth charts, so the season walk-back reaches it on the
    ordinary path. Asking three times for a file the server has already said
    it does not have adds the whole backoff schedule to an answer that was
    right the first time.
    """
    if not isinstance(error, ConnectionError):
        return False
    status = _status_of(error.__cause__)
    return status is None or status >= 500


def _status_of(cause: BaseException | None) -> int | None:
    """The HTTP status a failure carries, when the server answered with one.

    `requests` hangs the response off the exception it raises for a bad status
    and off nothing else, so a cause with no response is a failure that never
    got an answer — which is exactly the kind worth retrying.
    """
    response = getattr(cause, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def cache_settings() -> dict[str, Any]:
    """What the edge tells `nflreadpy` about keeping what it downloads.

    Settled here rather than through the environment so that the edge arranges
    its own caching and no deployment has to know: the tables land on the
    volume the runs and the reference already live on, and are kept for as long
    as a synced reference is treated as current. Only a table that arrived
    whole is kept — a download the wire cut short caches nothing — so a retry
    starts that table again but never the three beside it, and a second sync
    the same day downloads none of them.
    """
    return {
        "cache_mode": "filesystem",
        "cache_dir": config.nflverse_cache_dir(),
        "cache_duration": int(CACHE_TTL.total_seconds()),
        "timeout": DOWNLOAD_TIMEOUT_SECONDS,
    }


def _configured_loader() -> Any:
    """`nflreadpy` itself, told where to keep what it downloads on the way out."""
    nflreadpy.config.update_config(**cache_settings())
    return nflreadpy
