"""How this application opens the one SQLite file it keeps everything in.

Saved runs and the cached player reference are two concerns in one file, and
they were opening it two slightly different ways — which is how one of them
ended up without the write-ahead log the other documents as load-bearing. Both
go through here instead.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


def create_schema(path: Path, schema: str) -> None:
    """Create the database and everything `schema` declares, if absent.

    Idempotent: starting against an existing file leaves its contents alone.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        # Outside any transaction, because switching journal mode from inside
        # one is an error. Readers are not blocked by the writer, which matters
        # once a run is saved while a page is being served.
        connection.execute("PRAGMA journal_mode = WAL")
        with connection:
            connection.executescript(schema)


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """One connection, for one operation, inside one transaction.

    Opened per operation rather than held open. SQLite makes that cheap, and it
    keeps callers safe to use from the request threads FastAPI runs synchronous
    endpoints on without any thread-affinity rules.
    """
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            yield connection
