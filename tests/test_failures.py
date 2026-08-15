"""A run that cannot finish says what broke and what to do about it.

Driven through the HTTP boundary like the rest of the suite: a failure is read
off the terminal event the browser receives, not off an exception. What is
asserted here is what a reader can see — the kind, the words, and the raw
error sitting behind its toggle.

The caption failures are raised as the real `youtube-transcript-api`
exceptions, because the mapping under test is precisely the one between that
library's exceptions and the six kinds. Those exceptions all stringify to the
same paragraph, so a test that raised a lookalike would prove nothing.
"""

from __future__ import annotations

import html
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

from project_ai_ftsy_football_sum.services.failures import FAILURE_MESSAGES
from project_ai_ftsy_football_sum.services.players import CACHE_TTL
from project_ai_ftsy_football_sum.services.store import RunStore
from tests import events as sse
from tests.events import run_episode
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource

VIDEO_ID = "dQw4w9WgXcQ"


def warm_the_cache(client: TestClient) -> None:
    """Sync a reference, the way a visit to the Players page does."""
    assert client.get("/players").status_code == 200


def age_the_cache(app: FastAPI, age: timedelta) -> None:
    """Push the cached reference's sync time into the past."""
    cache = app.state.players
    reference = cache.load()
    assert reference is not None, "nothing has been cached yet"
    cache.save(replace(reference, synced_at=reference.synced_at - age))


def failure(client: TestClient, url: str | None = None) -> sse.Event:
    """The terminal event of a run that was not expected to finish."""
    events = run_episode(client) if url is None else run_episode(client, url)
    terminal = sse.terminal(events)
    assert terminal.name == "failed", sse.outline(events)
    return terminal


def rendered(event: sse.Event) -> str:
    """The failure's markup, as the browser would read it."""
    return html.unescape(event.data["html"])


# --- The six kinds --------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TranscriptsDisabled(VIDEO_ID), "no_captions"),
        (VideoUnavailable(VIDEO_ID), "video_unavailable"),
        (AgeRestricted(VIDEO_ID), "video_unavailable"),
        (VideoUnplayable(VIDEO_ID, "Members-only content", []), "video_unavailable"),
        (IpBlocked(VIDEO_ID), "youtube_blocked"),
        (RequestBlocked(VIDEO_ID), "youtube_blocked"),
    ],
)
def test_a_youtube_error_is_reported_as_the_kind_it_actually_is(
    client: TestClient, youtube: FakeYouTubeSource, error: Exception, kind: str
) -> None:
    youtube.captions_error = error

    assert failure(client).data["kind"] == kind


def test_an_episode_with_no_captions_says_they_may_still_be_generating(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """There is no audio fallback to offer instead — see ADR-0001."""
    youtube.tracks = []

    body = rendered(failure(client))

    assert "captions" in body
    assert "generates them" in body
    assert "trying again later" in body


def test_an_unavailable_video_says_the_problem_is_the_video(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.captions_error = VideoUnavailable(VIDEO_ID)

    body = rendered(failure(client))

    assert "private" in body
    assert "members-only" in body
    assert "not this app" in body.lower() or "rather than with this app" in body


def test_a_blocked_request_is_named_as_blocking_rather_than_left_mysterious(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.captions_error = RequestBlocked(VIDEO_ID)

    body = rendered(failure(client))

    assert "refused" in body.lower() or "blocked" in body.lower()
    assert "bot detection" in body.lower()


def test_an_unusable_url_is_rejected_with_what_was_wrong_with_it(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    stopped = failure(client, "https://vimeo.com/123456789")

    assert stopped.data["kind"] == "invalid_url"
    assert "not a YouTube episode URL" in rendered(stopped)
    assert youtube.calls == []


def test_a_claude_failure_says_it_is_worth_retrying(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    claude.error = RuntimeError("rate limited")

    stopped = failure(client)

    assert stopped.data["kind"] == "claude"
    assert "worth trying again" in rendered(stopped)


def test_nflverse_with_nothing_cached_says_so_and_says_to_wait(
    client: TestClient, nflverse: FakeNflverseSource
) -> None:
    nflverse.error = RuntimeError("nflverse is unreachable")

    stopped = failure(client)

    assert stopped.data["kind"] == "nflverse"
    assert "nflverse" in rendered(stopped)
    assert "few minutes" in rendered(stopped)


def test_every_kind_has_its_own_wording(client: TestClient) -> None:
    """Six kinds saying the same thing would be one kind wearing six labels."""
    messages = list(FAILURE_MESSAGES.values())

    assert len(set(messages)) == len(messages)


# --- The raw error --------------------------------------------------------


def test_a_caption_failure_carries_its_raw_error_behind_a_toggle(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.captions_error = TranscriptsDisabled(VIDEO_ID)

    body = rendered(failure(client))

    assert "<details" in body
    assert "TranscriptsDisabled" in body
    assert body.index("<details") > body.index(FAILURE_MESSAGES["no_captions"][:40])


def test_a_claude_failure_carries_its_raw_error_behind_a_toggle(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    claude.error = RuntimeError("429 rate_limit_error")

    body = rendered(failure(client))

    assert "<details" in body
    assert "429 rate_limit_error" in body


def test_an_nflverse_failure_carries_its_raw_error_behind_a_toggle(
    client: TestClient, nflverse: FakeNflverseSource
) -> None:
    nflverse.error = RuntimeError("nflverse is unreachable")

    body = rendered(failure(client))

    assert "<details" in body
    assert "nflverse is unreachable" in body


def test_an_unusable_url_offers_the_toggle_too(client: TestClient) -> None:
    """One shape of failure panel, whatever stopped the run."""
    body = rendered(failure(client, "https://vimeo.com/123456789"))

    assert "<details" in body
    assert "InvalidUrlError" in body


def test_a_failed_sync_on_the_players_page_offers_the_toggle_too(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    """The same failure, wherever the reader met it."""
    warm_the_cache(client)
    age_the_cache(app, CACHE_TTL + timedelta(hours=1))
    nflverse.error = RuntimeError("nflverse is unreachable")

    body = html.unescape(client.get("/players").text)

    assert "Sync failed" in body
    assert "<details" in body
    assert "nflverse is unreachable" in body
    assert "Bijan Robinson" in body


def test_the_raw_error_is_not_shouted_at_a_reader_who_did_not_ask(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """It is available, not on show: the summary element is what is on show."""
    youtube.captions_error = IpBlocked(VIDEO_ID)

    body = rendered(failure(client))

    assert "<summary" in body
    assert body.index("<summary") < body.index("IpBlocked")


# --- nflverse degrades rather than failing --------------------------------


def test_an_outage_with_a_warm_cache_finishes_the_run_and_warns_about_its_age(
    client: TestClient,
    app: FastAPI,
    nflverse: FakeNflverseSource,
    app_store: RunStore,
    claude: FakeClaudeClient,
) -> None:
    """An upstream outage costs accuracy, not the whole summary."""
    warm_the_cache(client)
    age_the_cache(app, CACHE_TTL + timedelta(days=2))
    nflverse.error = RuntimeError("nflverse is unreachable")

    events = run_episode(client)

    assert sse.terminal(events).name == "done"
    warning = html.unescape(sse.one(events, "warning").data["html"])
    assert "2 days ago" in warning
    assert "nflverse" in warning
    assert app_store.recent(1)[0].summary == claude.summary


def test_a_run_against_a_current_reference_warns_about_nothing(
    client: TestClient,
) -> None:
    warm_the_cache(client)

    assert sse.named(run_episode(client), "warning") == []


def test_an_outage_with_no_cache_at_all_ends_the_run(
    client: TestClient, nflverse: FakeNflverseSource, claude: FakeClaudeClient
) -> None:
    """Summarizing against no player data at all is worse than not summarizing."""
    nflverse.error = RuntimeError("nflverse is unreachable")

    assert failure(client).data["kind"] == "nflverse"
    assert claude.requests == []


# --- What a failed run leaves behind --------------------------------------


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(
            lambda youtube, nflverse, claude: setattr(
                youtube, "captions_error", TranscriptsDisabled(VIDEO_ID)
            ),
            id="no_captions",
        ),
        pytest.param(
            lambda youtube, nflverse, claude: setattr(
                nflverse, "error", RuntimeError("nflverse is unreachable")
            ),
            id="nflverse",
        ),
        pytest.param(
            lambda youtube, nflverse, claude: setattr(
                claude, "error", RuntimeError("rate limited")
            ),
            id="claude",
        ),
    ],
)
def test_a_failed_run_leaves_nothing_behind_that_looks_like_a_summary(
    client: TestClient,
    youtube: FakeYouTubeSource,
    nflverse: FakeNflverseSource,
    claude: FakeClaudeClient,
    app_store: RunStore,
    break_it: object,
) -> None:
    """A half-written record in History reads exactly like a finished run."""
    break_it(youtube, nflverse, claude)  # type: ignore[operator]

    assert failure(client).name == "failed"
    assert app_store.recent(5) == []
    assert "No runs yet" in client.get("/history").text


# --- What a failure does not stop -----------------------------------------


def test_metadata_failing_where_captions_did_not_still_finishes_the_run(
    client: TestClient, youtube: FakeYouTubeSource, app_store: RunStore
) -> None:
    """One flaky yt-dlp call is not worth the summary the reader came for."""
    youtube.metadata_error = RuntimeError("HTTP Error 403: Forbidden")
    youtube.oembed_error = RuntimeError("HTTP Error 429: Too Many Requests")

    events = run_episode(client)

    assert sse.terminal(events).name == "done"
    assert "Untitled episode" in sse.transcript_html(events)
    assert "Upload date unknown" in sse.transcript_html(events)
    saved = app_store.recent(1)[0]
    assert saved.title == "Untitled episode"
    assert saved.upload_date is None
