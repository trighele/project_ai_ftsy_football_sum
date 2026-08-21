"""How this application opens the one SQLite file it keeps everything in.

Saved runs and the cached player reference are two concerns in one file, and
they were opening it two slightly different ways — which is how one of them
ended up without the write-ahead log the other documents as load-bearing. Both
go through here instead.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
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


def add_missing_columns(path: Path, table: str, columns: Mapping[str, str]) -> None:
    """Bring a table that already exists up to the columns declared for it.

    `CREATE TABLE IF NOT EXISTS` does nothing whatsoever to a table that is
    already there, so a column added to the schema after a database was created
    would never reach that database — including the deployed one, which is the
    only copy of the data that matters. This reads the columns the table has
    and adds the ones it does not.

    Idempotent, and a no-op on a fresh database: the table was just created
    with every column, so there is nothing missing to add. A table that is not
    there at all is left alone rather than half-built.

    A column added to the declaration after the first release has to be
    nullable, because `ALTER TABLE ... ADD COLUMN` has no answer to give the
    rows already in the table for a `NOT NULL` column without a default.
    """
    with connect(path) as connection:
        existing = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if not existing:
            return
        for name, declaration in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
                )


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
