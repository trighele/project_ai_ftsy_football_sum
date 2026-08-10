"""Saved runs, in a single SQLite file.

The store is deliberately not one of the container's edges — it is local disk,
not a network dependency, and tests exercise the real thing. What it owes the
rest of the application is small: save a finished run, hand back the recent
ones, and reopen any one of them.

The file lives at a configured path (see `config.py`) so that a deployment can
mount a volume there without a code change. The schema is created on startup
when absent; there is no migration framework, so every column a later ticket
needs is declared now and left empty until then.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from project_ai_ftsy_football_sum.services.transcripts import (
    Episode,
    date_label,
    upload_date_label,
)

#: Every column, created on startup when the table is not there. `season` is
#: filled by the player reference ticket; it is declared here so that ticket
#: needs no schema change.
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT    NOT NULL,
    video_id         TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    channel          TEXT,
    upload_date      TEXT,
    transcript       TEXT    NOT NULL,
    summary          TEXT,
    season           INTEGER,
    model            TEXT,
    created_at       TEXT    NOT NULL,
    duration_seconds REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS runs_by_recency ON runs (created_at DESC, id DESC);
"""

_COLUMNS = (
    "url",
    "video_id",
    "title",
    "channel",
    "upload_date",
    "transcript",
    "summary",
    "season",
    "model",
    "created_at",
    "duration_seconds",
)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Run:
    """One end-to-end pass over an episode, as it is kept.

    A run carries everything needed to reopen it without going back to
    YouTube or to Claude. `season` stays empty until the player reference
    ticket fills it.
    """

    url: str
    video_id: str
    transcript: str
    title: str
    channel: str | None = None
    upload_date: date | None = None
    summary: str | None = None
    season: int | None = None
    model: str | None = None
    created_at: datetime = field(default_factory=_now)
    duration_seconds: float = 0.0
    #: Assigned by the store on save; `None` before a run has been saved.
    id: int | None = None

    @classmethod
    def of(
        cls,
        episode: Episode,
        *,
        duration_seconds: float,
        summary: str | None = None,
        model: str | None = None,
    ) -> Run:
        """The run to save for an episode that has just been summarized."""
        return cls(
            url=episode.url,
            video_id=episode.video_id,
            transcript=episode.transcript,
            title=episode.title,
            channel=episode.channel,
            upload_date=episode.upload_date,
            summary=summary,
            model=model,
            duration_seconds=duration_seconds,
        )

    @property
    def upload_date_label(self) -> str:
        """How the episode's upload date is put to the reader."""
        return upload_date_label(self.upload_date)

    @property
    def created_at_label(self) -> str:
        """When the run happened, as a reader scanning a list wants it."""
        return date_label(self.created_at.date())


class RunStore:
    """Reads and writes saved runs in one SQLite file.

    A connection is opened per operation rather than held open. SQLite makes
    that cheap, and it keeps the store safe to call from the request threads
    FastAPI runs synchronous endpoints on without any thread-affinity rules.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create the database and its schema if they are not there yet.

        Idempotent: starting against an existing file leaves its runs alone.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            # Outside any transaction, because switching journal mode from
            # inside one is an error. Readers are not blocked by the writer,
            # which matters once a run is saved while a page is being served.
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                connection.executescript(SCHEMA)

    def save(self, run: Run) -> Run:
        """Persist a finished run and return it with its assigned identifier."""
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO runs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                _row_values(run),
            )
            run_id = cursor.lastrowid
        return replace(run, id=run_id)

    def recent(self, limit: int) -> list[Run]:
        """The most recently created runs, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def get(self, run_id: int) -> Run | None:
        """One saved run, or `None` when nothing has that identifier."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _run_from_row(row) if row is not None else None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                yield connection


def _row_values(run: Run) -> tuple[Any, ...]:
    stored = {
        "upload_date": run.upload_date.isoformat() if run.upload_date else None,
        # Normalised to UTC on the way in, because recency is ordered on this
        # column as text: a row written at a different offset would otherwise
        # sort by the digits rather than by when it happened.
        "created_at": _as_utc(run.created_at).isoformat(),
    }
    return tuple(stored.get(column, getattr(run, column)) for column in _COLUMNS)


def _as_utc(moment: datetime) -> datetime:
    """A naive time is read as UTC; an aware one is converted to it."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _run_from_row(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        url=row["url"],
        video_id=row["video_id"],
        title=row["title"],
        channel=row["channel"],
        upload_date=date.fromisoformat(row["upload_date"])
        if row["upload_date"]
        else None,
        transcript=row["transcript"],
        summary=row["summary"],
        season=row["season"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
        duration_seconds=row["duration_seconds"],
    )
