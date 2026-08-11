"""One click fetches the transcript and then streams the summary in below it.

Driven through the HTTP boundary like the rest of the suite: a run is started
with a POST and followed over Server-Sent Events, which is exactly what the
browser does. What Claude was handed is asserted on the fake it was handed to.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.config import DEFAULT_MODEL, MODEL_VARIABLE
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.runs import (
    KEEPALIVE_FRAME,
    RETAINED_RUNS,
    Event,
    LiveRuns,
)
from project_ai_ftsy_football_sum.services.store import RunStore
from tests import events as sse
from tests.events import EPISODE_URL, run_episode, start
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource

TRANSCRIPT_OPENING = "Welcome back to the Fantasy Fallout podcast."


def test_one_click_produces_both_a_transcript_and_a_summary(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """There is no separate summarize step — the URL is the whole interaction."""
    events = run_episode(client)

    assert TRANSCRIPT_OPENING in sse.transcript_html(events)
    assert sse.summary_text(events) == claude.summary
    assert sse.terminal(events).name == "done"


def test_the_sse_event_sequence_for_a_successful_run(client: TestClient) -> None:
    """The protocol every later ticket adds to, pinned in one assertion."""
    assert sse.outline(run_episode(client)) == [
        "stage:captions",
        "stage:metadata",
        "transcript",
        "stage:players",
        "stage:summarizing",
        "summary",
        "done",
    ]


def test_the_transcript_is_delivered_before_summarizing_begins(
    client: TestClient,
) -> None:
    """The reader knows the episode was found before waiting on Claude."""
    names = [event.name for event in run_episode(client)]

    assert names.index("transcript") < names.index("summary")


def test_the_summary_arrives_in_pieces_rather_than_all_at_once(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    events = run_episode(client)

    pieces = sse.named(events, "summary")
    assert len(pieces) == len(claude.chunks)
    assert "".join(piece.data["text"] for piece in pieces) == claude.summary


def test_stage_transitions_are_announced_with_words_for_the_reader(
    client: TestClient,
) -> None:
    stages = sse.named(run_episode(client), "stage")

    assert [stage.data["stage"] for stage in stages] == [
        "captions",
        "metadata",
        "players",
        "summarizing",
    ]
    assert all(stage.data["label"].strip() for stage in stages)


def test_the_completed_summary_model_and_duration_are_saved_to_the_run(
    client: TestClient, app_store: RunStore, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    run = app_store.recent(1)[0]

    assert run.summary == claude.summary
    assert run.model == DEFAULT_MODEL
    assert run.duration_seconds > 0


def test_the_finished_run_is_announced_with_the_record_it_was_saved_as(
    client: TestClient, app_store: RunStore
) -> None:
    done = sse.terminal(run_episode(client))

    saved = app_store.recent(1)[0]
    assert done.data["run_id"] == saved.id
    assert done.data["href"] == f"/runs/{saved.id}"
    assert done.data["duration_seconds"] >= 0


def test_reopening_a_saved_run_shows_its_summary_as_well_as_its_transcript(
    client: TestClient, app_store: RunStore, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    body = client.get(f"/runs/{app_store.recent(1)[0].id}").text

    assert TRANSCRIPT_OPENING in body
    assert "## News Section" in body
    assert "Bijan Robinson (ATL, RB)" in body


def test_the_home_page_ships_the_controller_that_drives_a_run(
    client: TestClient,
) -> None:
    """Disabling the button for the length of a run is the browser's job.

    Nothing about it is visible over HTTP, so what is pinned here is that the
    page is wired to the script that does it and that the button has a
    disabled appearance to show for it.
    """
    body = client.get("/").text

    assert "data-run-form" in body
    assert 'action="/runs"' in body
    assert "/static/js/run.js" in body
    assert "disabled:" in body


def test_the_recent_list_can_be_re_fetched_once_a_run_has_made_it_stale(
    client: TestClient,
) -> None:
    run_episode(client)

    response = client.get("/fragments/recent-runs")

    assert response.status_code == 200
    assert 'id="recent-runs"' in response.text
    assert "Week 1 Waiver Wire Targets" in response.text


# --- What Claude is handed ------------------------------------------------


def test_the_fake_records_the_whole_request_claude_received(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    request = claude.request
    assert request.model == DEFAULT_MODEL
    assert len(request.system) == 1
    assert TRANSCRIPT_OPENING in request.user


def test_the_prompt_keeps_the_existing_output_contract(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """The sections and the per-item sentiment the old app produced."""
    run_episode(client)

    instructions = "".join(block["text"] for block in claude.request.system)
    for required in (
        "## News Section",
        "**Player/Team**",
        "**News**",
        "**Sentiment**",
        "## Matchup Analysis",
        "## Player Debates",
        "## Waiver Wire Suggestions",
    ):
        assert required in instructions


def test_the_episode_travels_in_the_user_turn_after_the_system_prompt(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """Ticket 08 caches the system prefix; per-run text cannot sit inside it."""
    run_episode(client)

    request = claude.request
    instructions = "".join(block["text"] for block in request.system)
    assert "Week 1 Waiver Wire Targets" in request.user
    assert "7 August 2026" in request.user
    assert "Week 1 Waiver Wire Targets" not in instructions
    assert TRANSCRIPT_OPENING not in instructions


def test_the_model_defaults_to_sonnet_and_the_environment_can_override_it(
    client: TestClient, claude: FakeClaudeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert DEFAULT_MODEL == "claude-sonnet-5"

    monkeypatch.setenv(MODEL_VARIABLE, "claude-opus-5")
    run_episode(client)

    assert claude.request.model == "claude-opus-5"


# --- When a run cannot finish ---------------------------------------------


def test_a_claude_failure_ends_the_run_with_the_claude_error_kind(
    client: TestClient, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    claude.error = RuntimeError("rate limited")

    events = run_episode(client)

    failure = sse.terminal(events)
    assert failure.name == "failed"
    assert failure.data["kind"] == "claude"
    assert "worth trying again" in failure.data["html"]
    assert "rate limited" not in failure.data["html"]
    assert app_store.recent(1) == []


def test_the_transcript_still_arrived_before_a_claude_failure(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    claude.error = RuntimeError("rate limited")

    assert sse.outline(run_episode(client)) == [
        "stage:captions",
        "stage:metadata",
        "transcript",
        "stage:players",
        "stage:summarizing",
        "failed",
    ]


def test_an_unusable_url_fails_the_run_before_any_edge_is_touched(
    client: TestClient, youtube: FakeYouTubeSource, claude: FakeClaudeClient
) -> None:
    events = run_episode(client, "https://vimeo.com/123456789")

    failure = sse.terminal(events)
    assert failure.name == "failed"
    assert failure.data["kind"] == "invalid_url"
    assert "YouTube" in failure.data["html"]
    assert youtube.calls == []
    assert claude.requests == []


def test_a_captions_failure_fails_the_run_with_the_captions_error_kind(
    client: TestClient, youtube: FakeYouTubeSource, claude: FakeClaudeClient
) -> None:
    youtube.captions_error = RuntimeError("Subtitles are disabled for this video")

    failure = sse.terminal(run_episode(client))

    assert failure.data["kind"] == "captions"
    assert "Something went wrong" in failure.data["html"]
    assert claude.requests == []


@pytest.fixture
def client_without_claude(
    youtube: FakeYouTubeSource, app_store: RunStore
) -> Iterator[TestClient]:
    """An application whose Claude edge cannot be built at all."""
    container = Container()
    container.override(captions=youtube, nflverse=FakeNflverseSource())
    with TestClient(create_app(container=container, store=app_store)) as client:
        yield client


def test_an_unbuildable_edge_fails_the_run_rather_than_hanging_the_stream(
    client_without_claude: TestClient,
) -> None:
    """A stream that merely stops is indistinguishable from a hang."""
    failure = sse.terminal(run_episode(client_without_claude))

    assert failure.name == "failed"
    assert failure.data["kind"] == "claude"


# --- Following a run ------------------------------------------------------


def test_a_run_can_be_followed_again_after_it_has_finished(
    client: TestClient,
) -> None:
    """Events are buffered, so a follower that arrives late misses nothing."""
    events_url = start(client, EPISODE_URL)

    first = sse.follow(client, events_url)
    second = sse.follow(client, events_url)

    assert sse.outline(second) == sse.outline(first)
    assert sse.summary_text(second) == sse.summary_text(first)


def test_following_a_run_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.get("/runs/nosuchrun/events").status_code == 404


def test_a_quiet_run_keeps_its_connection_alive() -> None:
    """Claude can think for a minute before writing; an idle connection is
    what a proxy between here and the browser closes."""
    live = LiveRuns().start()

    frames = live.frames(keepalive=0.01)
    first = asyncio.run(_first_frame(frames))

    assert first == KEEPALIVE_FRAME
    assert sse.decode(first) == []


async def _first_frame(frames: AsyncIterator[str]) -> str:
    async for frame in frames:
        return frame
    raise AssertionError("the stream produced nothing at all")


def test_a_run_still_in_flight_is_not_forgotten_to_make_room() -> None:
    """Retention drops what has been finished with, not what is happening."""
    runs = LiveRuns()
    in_flight = runs.start()

    for _ in range(RETAINED_RUNS * 2):
        finished = runs.start()
        finished.publish(sse_done())

    assert runs.get(in_flight.token) is in_flight


def sse_done() -> Event:
    return Event("done", {"run_id": 1, "href": "/runs/1", "label": "done"})
