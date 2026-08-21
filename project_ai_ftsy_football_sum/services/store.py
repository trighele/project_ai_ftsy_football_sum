"""Saved runs, in a single SQLite file.

The store is deliberately not one of the container's edges — it is local disk,
not a network dependency, and tests exercise the real thing. What it owes the
rest of the application is small: save a finished run, hand back the recent
ones, and reopen any one of them.

The file lives at a configured path (see `config.py`) so that a deployment can
mount a volume there without a code change. The schema is created on startup
when absent, and then reconciled: a column added to `COLUMNS` after a database
already exists is added to it, because `CREATE TABLE IF NOT EXISTS` would
otherwise leave the deployed database on the schema it was born with forever.
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from project_ai_ftsy_football_sum.services.sqlite import (
    add_missing_columns,
    connect,
    create_schema,
)
from project_ai_ftsy_football_sum.services.transcripts import (
    Episode,
    date_label,
    upload_date_label,
)

#: The runs table, one column at a time, and the single place the schema is
#: stated: the table is created from this on a fresh database, and a database
#: that predates one of these columns has it added on startup from the same
#: declaration. `season` is the season of the player reference the run was
#: summarized against — see `services/players.py` for why that is worth
#: keeping.
#:
#: A column added here after a release has to be nullable — see
#: `sqlite.add_missing_columns` for why an existing table admits no other kind.
COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "url": "TEXT NOT NULL",
    "video_id": "TEXT NOT NULL",
    "title": "TEXT NOT NULL",
    "channel": "TEXT",
    "upload_date": "TEXT",
    "transcript": "TEXT NOT NULL",
    "summary": "TEXT",
    "context_note": "TEXT",
    "season": "INTEGER",
    "model": "TEXT",
    "created_at": "TEXT NOT NULL",
    "duration_seconds": "REAL NOT NULL",
}

_DECLARATIONS = ", ".join(f"{name} {kind}" for name, kind in COLUMNS.items())

SCHEMA = f"CREATE TABLE IF NOT EXISTS runs ({_DECLARATIONS});"

#: One index per ordering below, created after the columns they sort on are
#: known to be there. SQLite sorts nulls last in a descending index, which is
#: exactly where `ORDER BY upload_date DESC NULLS LAST` wants them, so the
#: episode ordering is a scan of this index rather than of the table.
INDEXES = """
CREATE INDEX IF NOT EXISTS runs_by_recency ON runs (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS runs_by_episode
    ON runs (upload_date DESC, created_at DESC, id DESC);
"""

#: What `save` writes. The identifier is the one column the store does not
#: supply — SQLite assigns it.
_INSERT_COLUMNS = tuple(name for name in COLUMNS if name != "id")


#: The two orders a list of runs is asked for in, kept apart because they
#: answer two different questions. History is a list of *episodes*: newest
#: episode first, with an upload date that never resolved sorting last, because
#: an unknown date is not a recent one. The home page's recent list is a list of
#: *work*: what was just run. Neither is the other's default — a caller says
#: which it wants by the read it calls, not by an argument.
_BY_EPISODE_DATE = "ORDER BY upload_date DESC NULLS LAST, created_at DESC, id DESC"
_BY_RUN_TIME = "ORDER BY created_at DESC, id DESC"

#: Every read below selects whole rows; only what it asks for and the order it
#: asks in differ.
_RUNS = "SELECT * FROM runs"


def _now() -> datetime:
    return datetime.now(UTC)


def _escape_like(term: str) -> str:
    """Make a search term mean itself inside a `LIKE` pattern.

    A title can contain `%` — "100% Start Em Sit Em" — and a reader typing it
    means those characters, not SQL's wildcards.
    """
    for character in ("\\", "%", "_"):
        term = term.replace(character, f"\\{character}")
    return term


@dataclass(frozen=True)
class Run:
    """One end-to-end pass over an episode, as it is kept.

    A run carries everything needed to reopen it without going back to
    YouTube or to Claude, `season` included: which season's players it was
    summarized against is part of what the summary means.
    """

    url: str
    video_id: str
    transcript: str
    title: str
    channel: str | None = None
    upload_date: date | None = None
    summary: str | None = None
    #: What the reader asked this summary to pay attention to, if anything.
    #: Nothing reads it back to decide anything — it is a record of what was
    #: asked for, kept beside what came of it.
    context_note: str | None = None
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
        season: int | None = None,
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
            context_note=episode.context_note,
            season=season,
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
    """Reads and writes saved runs in one SQLite file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create the database, bring an older one up to date, and index it.

        Three steps in this order and no other: the table has to exist before
        its columns can be reconciled, and the columns have to be there before
        an index can be built over them.
        """
        create_schema(self.path, SCHEMA)
        add_missing_columns(self.path, "runs", COLUMNS)
        create_schema(self.path, INDEXES)

    def save(self, run: Run) -> Run:
        """Persist a finished run and return it with its assigned identifier."""
        placeholders = ", ".join("?" for _ in _INSERT_COLUMNS)
        with self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO runs ({', '.join(_INSERT_COLUMNS)}) "
                f"VALUES ({placeholders})",
                _row_values(run),
            )
            run_id = cursor.lastrowid
        return replace(run, id=run_id)

    def recent(self, limit: int) -> list[Run]:
        """The runs most recently made, newest work first.

        What the home page asks: "what did I just run". Deliberately not the
        order History uses — see `search`.
        """
        return self._read(f"{_RUNS} {_BY_RUN_TIME} LIMIT ?", (limit,))

    def search(self, query: str = "") -> list[Run]:
        """Every saved run whose title contains `query`, newest episode first.

        What History asks: "what is the newest episode I have covered". The
        order is the episode's own, not the order the work was done in, so
        catching up on a backlog does not scramble the list.

        An empty query is not a filter, so the History page and its search box
        are the same read — and so a search is a filter over that list rather
        than a differently ordered one. Matching is on the title alone: it is
        what the reader remembers about an episode, and searching the
        transcript would turn a name-drop into a hit.
        """
        term = query.strip()
        where = "WHERE title LIKE ? ESCAPE '\\'" if term else ""
        parameters: tuple[Any, ...] = (f"%{_escape_like(term)}%",) if term else ()
        return self._read(f"{_RUNS} {where} {_BY_EPISODE_DATE}", parameters)

    def get(self, run_id: int) -> Run | None:
        """One saved run, or `None` when nothing has that identifier."""
        rows = self._read(f"{_RUNS} WHERE id = ?", (run_id,))
        return rows[0] if rows else None

    def delete(self, run_id: int) -> bool:
        """Forget a run entirely. `False` when there was nothing to forget.

        A real deletion, not a hidden flag: a run deleted because it was junk
        should not come back in anything that reads the table later.
        """
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            return cursor.rowcount > 0

    def _read(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[Run]:
        """Run a query that selects whole rows and hand back runs.

        The ordering is not this method's to decide: each read above states its
        own, so the question being asked is answered by the name of the read.
        """
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [_run_from_row(row) for row in rows]

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return connect(self.path)


def _row_values(run: Run) -> tuple[Any, ...]:
    stored = {
        "upload_date": run.upload_date.isoformat() if run.upload_date else None,
        # Normalised to UTC on the way in, because recency is ordered on this
        # column as text: a row written at a different offset would otherwise
        # sort by the digits rather than by when it happened.
        "created_at": _as_utc(run.created_at).isoformat(),
    }
    return tuple(stored.get(column, getattr(run, column)) for column in _INSERT_COLUMNS)


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
        context_note=row["context_note"],
        season=row["season"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
        duration_seconds=row["duration_seconds"],
    )
