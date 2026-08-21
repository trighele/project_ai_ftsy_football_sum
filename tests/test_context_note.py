"""A note the reader attaches to one episode, and everywhere it has to reach.

The decision this file defends is where the note lands in what Claude is sent.
The system prompt's second block is marked for caching and has to stay
byte-identical between runs; a per-episode string in there would invalidate
that cache silently, at full price and with no error to explain it. So the
assertions here are on the recorded request: the note in the user turn, and
the system blocks unchanged beside it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import RECENT_RUN_LIMIT, create_app
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.store import RunStore
from project_ai_ftsy_football_sum.services.summarize import (
    CONTEXT_NOTE_LABEL,
    MAX_CONTEXT_NOTE_LENGTH,
)
from tests.events import run_episode
from tests.fakes import FakeClaudeClient
from tests.test_history import only_run_id, run_ids
from tests.test_saved_runs import older_schema, table_columns

NOTE = "Weigh this against a roster that is thin at running back."

#: Where the note has to sit in the user turn: after the episode's own facts,
#: before the transcript it is an instruction about.
UPLOAD_DATE_LINE = "Upload date: 7 August 2026\n"
TRANSCRIPT_HEADING = "\nTranscript:\n\n"


def test_the_note_sits_between_the_upload_date_and_the_transcript(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client, context_note=NOTE)

    user = claude.request.user

    assert f"{UPLOAD_DATE_LINE}\n{CONTEXT_NOTE_LABEL}\n{NOTE}\n{TRANSCRIPT_HEADING}" in user


def test_a_run_without_a_note_sends_the_user_turn_it_sends_today(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """No empty label, no stray blank line — the date meets the transcript."""
    run_episode(client)

    user = claude.request.user

    assert f"{UPLOAD_DATE_LINE}{TRANSCRIPT_HEADING}" in user
    assert "Context note" not in user


def test_the_system_blocks_are_byte_identical_with_and_without_a_note(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """The whole point of the ticket: the cached prefix is not disturbed."""
    run_episode(client)
    run_episode(client, context_note=NOTE)

    without, with_note = claude.requests

    assert with_note.system == without.system
    assert with_note.user != without.user


def test_a_whitespace_only_note_is_no_note_at_all(
    client: TestClient, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    run_episode(client, context_note="   \n\t  ")

    assert "Context note" not in claude.request.user
    assert app_store.recent(1)[0].context_note is None


def test_a_note_is_trimmed_on_the_way_in(
    client: TestClient, app_store: RunStore
) -> None:
    run_episode(client, context_note=f"\n  {NOTE}  \n")

    assert app_store.recent(1)[0].context_note == NOTE


def test_an_over_long_note_is_truncated_rather_than_losing_the_run(
    client: TestClient, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    """Pasting a wall of text costs the tail of the note, not the summary."""
    over_long = "a" * (MAX_CONTEXT_NOTE_LENGTH + 500)

    events = run_episode(client, context_note=over_long)

    assert events[-1].name == "done", [event.name for event in events]
    stored = app_store.recent(1)[0].context_note
    assert stored == "a" * MAX_CONTEXT_NOTE_LENGTH
    assert stored in claude.request.user


def test_the_note_is_stored_with_the_run_and_survives_a_restart(
    tmp_path: Path, container: Container
) -> None:
    database = tmp_path / "restart.db"

    with TestClient(create_app(container=container, store=RunStore(database))) as first:
        run_episode(first, context_note=NOTE)

    with TestClient(create_app(container=container, store=RunStore(database))) as second:
        body = second.get(f"/runs/{only_run_id(second)}").text

    assert NOTE in body


def test_the_run_page_shows_the_note_in_its_own_panel_above_the_summary(
    client: TestClient,
) -> None:
    run_episode(client, context_note=NOTE)

    body = client.get(f"/runs/{only_run_id(client)}").text

    assert "Context note" in body
    assert NOTE in body
    assert body.index(NOTE) < body.index("Summary")


def test_a_run_without_a_note_shows_no_panel(client: TestClient) -> None:
    """Nothing gains an empty field for the sake of consistency."""
    run_episode(client)

    body = client.get(f"/runs/{only_run_id(client)}").text

    assert "Context note" not in body


def test_the_downloaded_document_carries_a_multi_line_note(
    client: TestClient,
) -> None:
    """Written as a block, so the newlines survive the round trip."""
    run_episode(client, context_note="Thin at running back.\nStart/sit for Week 1.")

    document = client.get(f"/runs/{only_run_id(client)}/download").text

    assert (
        "- **Context note:** |\n"
        "      Thin at running back.\n"
        "      Start/sit for Week 1.\n"
    ) in document


def test_a_download_without_a_note_carries_no_context_note_field(
    client: TestClient,
) -> None:
    run_episode(client)

    assert "Context note" not in client.get(
        f"/runs/{only_run_id(client)}/download"
    ).text


def test_startup_adds_the_column_to_a_database_created_before_it_existed(
    tmp_path: Path,
) -> None:
    """The first real use of the reconcile: the live box has the older table."""
    database = tmp_path / "older.db"
    older_schema(database, without="context_note")

    RunStore(database).initialize()

    assert "context_note" in table_columns(database)
    saved = RunStore(database).recent(RECENT_RUN_LIMIT)
    assert len(saved) == 1
    assert saved[0].context_note is None


def test_history_does_not_search_on_the_note(client: TestClient) -> None:
    """The note is an input to one request, not a thing the app reads back.

    Asserted against a term that appears only in the note, beside one that
    appears in the title, so this fails if the search stopped narrowing at all
    rather than only if it started reading notes.
    """
    run_episode(client, context_note="Hyperspecific waiver wire phrasing")

    assert run_ids(client.get("/history?q=Hyperspecific").text) == []
    assert run_ids(client.get("/history?q=Waiver").text) != []
