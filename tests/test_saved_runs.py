"""Every run is saved, listed on the home page, and reopenable afterwards.

Driven through the HTTP boundary like the rest of the suite. The store is not
a network edge, so it is not faked: a real SQLite file in a temporary directory
is the thing under test, and the restart test would prove nothing against a
fake.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import RECENT_RUN_LIMIT, create_app
from project_ai_ftsy_football_sum.config import (
    DATA_DIR_VARIABLE,
    DATABASE_FILENAME,
    DEFAULT_MODEL,
    database_path,
)
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.players import calendar_season
from project_ai_ftsy_football_sum.services.sqlite import connect
from project_ai_ftsy_football_sum.services.store import COLUMNS, RunStore
from tests.events import EPISODE_URL, run_episode, run_titled
from tests.fakes import FakeClaudeClient, FakeYouTubeSource

EPISODE_TITLE = "Week 1 Waiver Wire Targets"
TRANSCRIPT_OPENING = "Welcome back to the Fantasy Fallout podcast."


def run_links(body: str) -> list[str]:
    """The `/runs/<id>` hrefs on a page, in the order they appear."""
    return re.findall(r'href="(/runs/\d+)"', body)


def test_a_completed_run_is_saved_with_no_explicit_save_action(
    client: TestClient,
) -> None:
    """Submitting the URL is the whole interaction — there is no save button."""
    run_episode(client)

    body = client.get("/").text

    assert EPISODE_TITLE in body
    assert run_links(body)


def test_a_failed_run_is_not_saved(client: TestClient, youtube: FakeYouTubeSource) -> None:
    youtube.captions_error = RuntimeError("Subtitles are disabled for this video")

    run_episode(client)

    assert run_links(client.get("/").text) == []


def test_a_rejected_url_is_not_saved(client: TestClient) -> None:
    run_episode(client, "https://vimeo.com/123456789")

    assert run_links(client.get("/").text) == []


def test_the_home_page_lists_the_five_most_recent_runs(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    for number in range(1, 8):
        run_titled(client, youtube, f"Episode {number}")

    body = client.get("/").text

    assert len(run_links(body)) == RECENT_RUN_LIMIT
    for number in (7, 6, 5, 4, 3):
        assert f"Episode {number}" in body
    for number in (2, 1):
        assert f"Episode {number}" not in body


def test_the_most_recent_run_is_listed_first(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    for number in (1, 2, 3):
        run_titled(client, youtube, f"Episode {number}")

    body = client.get("/").text

    assert body.index("Episode 3") < body.index("Episode 2") < body.index("Episode 1")


def test_the_two_orderings_are_two_different_reads(
    client: TestClient, youtube: FakeYouTubeSource, app_store: RunStore
) -> None:
    """The home page asks what was run last; History asks what is newest.

    Same rows, two questions, and the answers differ — which is the whole
    reason they are two named reads rather than one with a flag.
    """
    run_titled(client, youtube, "August Episode", uploaded="20260812")
    run_titled(client, youtube, "June Episode", uploaded="20260619")

    assert [run.title for run in app_store.recent(RECENT_RUN_LIMIT)] == [
        "June Episode",
        "August Episode",
    ]
    assert [run.title for run in app_store.search()] == [
        "August Episode",
        "June Episode",
    ]


def test_the_home_pages_recent_list_still_orders_by_when_the_run_happened(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """What was just run is a different question from what is newest."""
    run_titled(client, youtube, "August Episode", uploaded="20260812")
    run_titled(client, youtube, "June Episode", uploaded="20260619")

    body = client.get("/").text

    assert body.index("June Episode") < body.index("August Episode")


def table_columns(database: Path) -> set[str]:
    with connect(database) as connection:
        return {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}


def older_schema(database: Path, *, without: str) -> None:
    """A runs table as it stood before `without` was added to the schema."""
    declarations = ", ".join(
        f"{name} {declaration}"
        for name, declaration in COLUMNS.items()
        if name != without
    )
    with connect(database) as connection:
        connection.execute(f"CREATE TABLE runs ({declarations})")
        connection.execute(
            "INSERT INTO runs (url, video_id, title, transcript, created_at, "
            "duration_seconds) VALUES (?, ?, ?, ?, ?, ?)",
            (EPISODE_URL, "dQw4w9WgXcQ", EPISODE_TITLE, "...", "2026-08-01", 1.0),
        )


def test_startup_adds_a_column_an_older_database_is_missing_and_keeps_its_rows(
    tmp_path: Path,
) -> None:
    """A column added after a deployment only arrives if startup adds it."""
    database = tmp_path / "older.db"
    older_schema(database, without="season")

    RunStore(database).initialize()

    assert "season" in table_columns(database)
    saved = RunStore(database).recent(RECENT_RUN_LIMIT)
    assert [run.title for run in saved] == [EPISODE_TITLE]
    assert saved[0].season is None


def test_the_schema_reconcile_is_a_no_op_on_a_fresh_database_and_on_a_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fresh.db"

    RunStore(database).initialize()
    first = table_columns(database)
    RunStore(database).initialize()

    assert first == set(COLUMNS)
    assert table_columns(database) == set(COLUMNS)


def test_a_listed_run_carries_enough_detail_to_identify_the_episode(
    client: TestClient,
) -> None:
    run_episode(client)

    body = client.get("/").text
    listing = body[body.index("Recent runs") :]

    assert EPISODE_TITLE in listing
    assert "Fantasy Fallout" in listing
    assert "7 August 2026" in listing


def test_the_home_page_says_so_when_nothing_has_been_run_yet(
    client: TestClient,
) -> None:
    body = client.get("/").text

    assert "No runs yet" in body
    assert run_links(body) == []


def test_clicking_a_recent_run_opens_it_with_its_transcript_intact(
    client: TestClient,
) -> None:
    run_episode(client)
    href = run_links(client.get("/").text)[0]

    response = client.get(href)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert TRANSCRIPT_OPENING in body
    assert "the Falcons are talking about a bigger role." in body
    assert EPISODE_TITLE in body
    assert "Fantasy Fallout" in body
    assert "7 August 2026" in body


def test_a_reopened_run_links_back_to_the_episode_on_youtube(
    client: TestClient,
) -> None:
    run_episode(client)

    body = client.get(run_links(client.get("/").text)[0]).text

    assert EPISODE_URL in body


def test_reopening_a_run_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.get("/runs/404404").status_code == 404


def test_the_recent_list_is_re_fetchable_once_a_run_has_made_it_stale(
    client: TestClient,
) -> None:
    """The browser re-fetches this the moment a run finishes; no page reload."""
    run_episode(client)

    body = client.get("/fragments/recent-runs").text

    assert 'id="recent-runs"' in body
    assert EPISODE_TITLE in body


def test_runs_written_by_one_application_instance_are_read_by_a_fresh_one(
    tmp_path: Path, container: Container
) -> None:
    """The point of persisting at all: a restart must not lose the work."""
    database = tmp_path / "restart.db"

    with TestClient(create_app(container=container, store=RunStore(database))) as first:
        run_episode(first)
        href = run_links(first.get("/").text)[0]

    with TestClient(create_app(container=container, store=RunStore(database))) as second:
        listing = second.get("/")
        reopened = second.get(href)

    assert EPISODE_TITLE in listing.text
    assert reopened.status_code == 200
    assert TRANSCRIPT_OPENING in reopened.text


def test_the_database_location_is_read_from_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ticket 10 mounts a volume at this path; no code changes when it does."""
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(tmp_path / "mounted"))

    assert database_path() == tmp_path / "mounted" / DATABASE_FILENAME


def test_the_schema_is_created_on_startup_when_the_database_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, container: Container
) -> None:
    data_dir = tmp_path / "not-created-yet"
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(data_dir))
    assert not data_dir.exists()

    with TestClient(create_app(container=container)) as client:
        run_episode(client)
        assert EPISODE_TITLE in client.get("/").text

    assert (data_dir / DATABASE_FILENAME).is_file()


def test_starting_up_against_an_existing_database_keeps_its_runs(
    tmp_path: Path, container: Container
) -> None:
    """Schema creation is idempotent — it must not wipe what is already there."""
    database = tmp_path / "existing.db"

    with TestClient(create_app(container=container, store=RunStore(database))) as first:
        run_episode(first)

    with TestClient(create_app(container=container, store=RunStore(database))) as second:
        assert len(run_links(second.get("/").text)) == 1


def test_a_saved_run_records_everything_needed_to_reopen_it(
    client: TestClient, app_store: RunStore, claude: FakeClaudeClient
) -> None:
    """Everything a reopened run shows, including the season it was written
    against — a summary means something different if the players were last
    year's."""
    run_episode(client)

    run = app_store.recent(1)[0]

    assert run.url == EPISODE_URL
    assert run.video_id == "dQw4w9WgXcQ"
    assert run.title == EPISODE_TITLE
    assert run.channel == "Fantasy Fallout"
    assert run.upload_date is not None and run.upload_date.year == 2026
    assert run.transcript.startswith(TRANSCRIPT_OPENING)
    assert run.created_at is not None
    assert run.duration_seconds >= 0
    assert run.summary == claude.summary
    assert run.model == DEFAULT_MODEL
    assert run.season == calendar_season()
