"""The synced player reference, kept in the same SQLite file as the runs.

Like `RunStore` this is local disk rather than a network edge, so tests
exercise the real thing. It holds exactly one reference: a sync replaces what
was there, because a half-current reference is worse than either version of it.

The row order written is the order `players.py` sorted them into, and the order
they are read back in, so the block handed to Claude is byte-stable between
runs however many times it goes through here.
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from project_ai_ftsy_football_sum.services.players import PlayerReference, PlayerRow
from project_ai_ftsy_football_sum.services.sqlite import connect, create_schema

#: `ordinal` preserves the sort the player service applied. `depth_rank` and
#: `ecr_tier` are two columns because they are two different facts — see
#: ADR-0002. Nothing here is called `tier`.
SCHEMA = """
CREATE TABLE IF NOT EXISTS player_reference (
    ordinal       INTEGER PRIMARY KEY,
    player_id     TEXT    NOT NULL,
    player_name   TEXT    NOT NULL,
    team          TEXT    NOT NULL,
    position      TEXT,
    depth_rank    INTEGER,
    ecr_tier      INTEGER,
    ecr_rank      REAL,
    bye_week      INTEGER,
    injury_status TEXT
);

CREATE TABLE IF NOT EXISTS player_reference_sync (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    season    INTEGER NOT NULL,
    synced_at TEXT    NOT NULL
);
"""

_COLUMNS = (
    "player_id",
    "player_name",
    "team",
    "position",
    "depth_rank",
    "ecr_tier",
    "ecr_rank",
    "bye_week",
    "injury_status",
)


class PlayerCache:
    """Reads and writes the one cached player reference."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create the tables if they are not there yet. Idempotent."""
        create_schema(self.path, SCHEMA)

    def load(self) -> PlayerReference | None:
        """The cached reference, or `None` before anything has been synced."""
        with self._connect() as connection:
            synced = connection.execute(
                "SELECT season, synced_at FROM player_reference_sync WHERE id = 1"
            ).fetchone()
            if synced is None:
                return None
            rows = connection.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM player_reference ORDER BY ordinal"
            ).fetchall()

        return PlayerReference(
            season=synced["season"],
            synced_at=datetime.fromisoformat(synced["synced_at"]),
            rows=tuple(PlayerRow(**dict(row)) for row in rows),
        )

    def save(self, reference: PlayerReference) -> None:
        """Replace the cached reference with this one, in one transaction."""
        placeholders = ", ".join("?" for _ in ("ordinal", *_COLUMNS))
        with self._connect() as connection:
            connection.execute("DELETE FROM player_reference")
            connection.executemany(
                f"INSERT INTO player_reference (ordinal, {', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                [
                    (ordinal, *(getattr(row, column) for column in _COLUMNS))
                    for ordinal, row in enumerate(reference.rows)
                ],
            )
            connection.execute(
                "INSERT OR REPLACE INTO player_reference_sync "
                "(id, season, synced_at) VALUES (1, ?, ?)",
                (reference.season, _as_utc(reference.synced_at).isoformat()),
            )

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return connect(self.path)


def _as_utc(moment: datetime) -> datetime:
    """A naive time is read as UTC; an aware one is converted to it."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
