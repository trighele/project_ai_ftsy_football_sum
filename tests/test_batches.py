"""Several episodes from one submission, followed as a queue.

Driven through the HTTP boundary like the rest of the suite: a batch is
started with a POST and followed over Server-Sent Events, exactly as the
browser does it. What is asserted is the sequence of events and what ended up
saved — not how many events a particular episode produced on the way there.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.services import batches, store
from project_ai_ftsy_football_sum.services.store import RunStore
from tests import events as sse
from tests.events import BATCH_URLS, BATCH_VIDEO_IDS, run_batch
from tests.fakes import FakeYouTubeSource


def _last_row(events: list[sse.Event], position: int) -> sse.Event:
    """The final state one queue row reached.

    By position rather than by counting events: how many times a row
    changed on the way is the batch's business, not the protocol's.
    """
    rows = [event for event in sse.named(events, "batch-episode")
            if event.data["position"] == position]
    assert rows, sse.outline(events)
    return rows[-1]


def _index_of(rows: list[sse.Event], *, position: int, state: str) -> int:
    """Where in the stream one row reached one state."""
    for index, row in enumerate(rows):
        if row.data["position"] == position and row.data["state"] == state:
            return index
    raise AssertionError(f"no row {position} ever reached {state}")


def test_the_home_page_offers_a_second_form_that_posts_a_list_of_urls(
    client: TestClient,
) -> None:
    """Two tabs over two real forms, each posting to its own route."""
    body = client.get("/").text

    assert 'action="/runs"' in body
    assert 'action="/batches"' in body
    assert "data-batch-form" in body
    assert 'name="youtube_urls"' in body


def test_a_batch_returns_at_once_with_a_queue_naming_the_stream_to_follow(
    client: TestClient,
) -> None:
    """The submission answers before any work: the queue is the receipt."""
    response = client.post("/batches", data={"youtube_urls": "\n".join(BATCH_URLS)})

    assert response.status_code == 202
    assert 'data-batch-events="/batches/' in response.text
    for position, url in enumerate(BATCH_URLS):
        assert f'data-batch-row="{position}"' in response.text
        assert url in response.text


def test_the_episodes_are_summarized_in_the_order_they_were_submitted(
    client: TestClient, app_store: RunStore
) -> None:
    """One click, three saved runs, and the queue's order is the paste's."""
    sse.batch_terminal(run_batch(client))

    saved = app_store.recent(len(BATCH_URLS))
    # `recent` is newest first, so the submission read back is its reverse.
    assert [run.video_id for run in reversed(saved)] == list(BATCH_VIDEO_IDS)
    assert all(run.summary for run in saved)


def test_a_batch_ends_with_one_terminal_event_carrying_the_counts(
    client: TestClient,
) -> None:
    events = run_batch(client)

    finished = sse.batch_terminal(events)
    assert finished.name == "batch-done"
    assert finished.data["total"] == len(BATCH_URLS)
    assert finished.data["summarized"] == len(BATCH_URLS)
    assert finished.data["failed"] == 0
    assert finished.data["label"] == "3 episodes summarized"


def test_one_failing_episode_does_not_cost_the_reader_the_others(
    client: TestClient, youtube: FakeYouTubeSource, app_store: RunStore
) -> None:
    """A dead video in the middle of a paste is one failed row, not a lost batch."""
    youtube.captions_errors = {
        BATCH_VIDEO_IDS[1]: RuntimeError("Subtitles are disabled for this video")
    }

    events = run_batch(client)

    assert [run.video_id for run in app_store.recent(3)] == [
        BATCH_VIDEO_IDS[2],
        BATCH_VIDEO_IDS[0],
    ]
    finished = sse.batch_terminal(events)
    assert finished.data["summarized"] == 2
    assert finished.data["failed"] == 1
    assert finished.data["label"] == "2 summarized, 1 failed"


def test_a_failed_row_names_its_kind_and_offers_the_underlying_error(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """The same words a single run is stopped with, behind the same toggle."""
    youtube.captions_errors = {
        BATCH_VIDEO_IDS[1]: RuntimeError("Subtitles are disabled for this video")
    }

    row = _last_row(run_batch(client), position=1)

    assert row.data["state"] == "failed"
    assert "no captions to read" in row.data["html"]
    assert "Show the underlying error" in row.data["html"]
    assert "Subtitles are disabled" in row.data["html"]


def test_the_home_page_ships_the_controller_that_follows_a_batch(
    client: TestClient,
) -> None:
    """Following the queue is the browser's job; being wired to do it is not."""
    body = client.get("/").text

    assert "/static/js/batch.js" in body
    assert "/static/js/recent-runs.js" in body
    assert client.get("/static/js/batch.js").status_code == 200
    assert client.get("/static/js/recent-runs.js").status_code == 200


def test_the_recent_list_is_up_to_date_once_the_batch_has_ended(
    client: TestClient, app_store: RunStore
) -> None:
    """What the browser re-fetches when the queue says it has finished."""
    run_batch(client)

    body = client.get("/fragments/recent-runs").text

    for run in app_store.recent(len(BATCH_URLS)):
        assert f'href="/runs/{run.id}"' in body


def test_a_finished_episode_is_a_link_to_its_run_before_the_next_one_starts(
    client: TestClient, app_store: RunStore
) -> None:
    """The reader starts reading the first while the rest are still going."""
    rows = sse.named(run_batch(client), "batch-episode")

    first_done = _index_of(rows, position=0, state="done")
    assert first_done < _index_of(rows, position=1, state="running")

    saved = app_store.recent(len(BATCH_URLS))[-1]
    assert saved.video_id == BATCH_VIDEO_IDS[0]
    assert f'href="/runs/{saved.id}"' in rows[first_done].data["html"]


def test_a_batch_in_which_everything_failed_still_ends_with_its_counts(
    client: TestClient, youtube: FakeYouTubeSource, app_store: RunStore
) -> None:
    """A batch that ran is a batch that finished, whatever came of it."""
    youtube.captions_error = RuntimeError("Subtitles are disabled for this video")

    finished = sse.batch_terminal(run_batch(client))

    assert finished.name == "batch-done"
    assert finished.data == {
        "total": 3,
        "summarized": 0,
        "failed": 3,
        "label": "3 episodes failed",
    }
    assert app_store.recent(1) == []


def test_a_batch_whose_driving_task_dies_still_ends_its_stream(
    client: TestClient, app_store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream that merely stops is indistinguishable from a hang.

    A store that cannot be written to is the case that proves it: saving a run
    is the one step the pipeline does not turn into a `RunFailed`, so it is
    not one episode's failure and it takes the batch with it.
    """

    def unwritable(_run: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(app_store, "save", unwritable)

    finished = sse.batch_terminal(run_batch(client))

    assert finished.name == "batch-failed"
    assert finished.data["kind"] == "unknown"
    assert "Show the underlying error" in finished.data["html"]
    # A batch that died telling its reader a *run* stopped would be the one
    # place the two tellings borrow each other's words.
    assert "Batch stopped" in finished.data["html"]
    assert "Run stopped" not in finished.data["html"]


def test_a_batch_keeps_going_when_nobody_is_following_it(
    client: TestClient, app_store: RunStore
) -> None:
    """Navigating away does not cancel the work: the follower is not the task."""
    events_url = sse.start_batch(client)

    assert client.get("/").status_code == 200
    assert client.get("/history").status_code == 200

    sse.batch_terminal(sse.follow(client, events_url))
    assert len(app_store.recent(len(BATCH_URLS))) == len(BATCH_URLS)


def test_a_batch_speaks_none_of_the_words_a_single_run_speaks(
    client: TestClient,
) -> None:
    """Distinct names mean the two client scripts cannot misread each other."""
    spoken = {event.name for event in run_batch(client)}

    assert spoken.isdisjoint(
        {"stage", "transcript", "warning", "summary", "done", "failed"}
    )
    assert spoken <= {"batch-episode", *batches.TERMINAL_EVENTS}


def test_following_a_batch_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.get("/batches/nosuchbatch/events").status_code == 404


def test_nothing_downstream_of_the_queue_knows_a_batch_happened(
    client: TestClient,
) -> None:
    """A batch is a way of starting work, not a thing the domain model keeps."""
    assert not any("batch" in column for column in store.COLUMNS)

    run_batch(client)

    assert "batch" not in client.get("/history").text.lower()
