"""Pasting a YouTube URL and clicking once renders the episode's transcript.

Driven through the HTTP boundary with the captions edge faked, as the spec's
single seam requires: a run is started and followed, and the transcript is
read out of the panel the run streamed back.
"""

import pytest
from fastapi.testclient import TestClient

from tests import events as sse
from tests.events import EPISODE_URL, run_episode
from tests.fakes import FakeYouTubeSource, generated_track, manual_track

MANUAL_TEXT = "Welcome back to the Fantasy Fallout podcast."
GENERATED_TEXT = "welcome back to the fantasy fallout"


def transcript(client: TestClient, url: str = EPISODE_URL) -> str:
    """The episode panel a run rendered for that URL."""
    return sse.transcript_html(run_episode(client, url))


def test_submitting_a_url_renders_the_transcript(client: TestClient) -> None:
    body = transcript(client)

    assert "Welcome back to the Fantasy Fallout podcast." in body
    assert "the Falcons are talking about a bigger role." in body


def test_title_channel_and_upload_date_render_alongside_the_transcript(
    client: TestClient,
) -> None:
    body = transcript(client)

    assert "Week 1 Waiver Wire Targets" in body
    assert "Fantasy Fallout" in body
    assert "7 August 2026" in body


def test_segments_are_joined_into_one_transcript_with_no_timestamps(
    client: TestClient,
) -> None:
    body = transcript(client)

    assert "podcast. Bijan Robinson looked electric in the preseason opener," in body
    assert "3.2" not in body
    assert "7.3" not in body


def test_uploaded_track_is_preferred_over_an_auto_generated_one(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """Both exist for the fixture episode; the uploaded one is the better text."""
    youtube.tracks = [generated_track(), manual_track()]

    body = transcript(client)

    assert MANUAL_TEXT in body
    assert GENERATED_TEXT not in body


def test_auto_generated_track_is_used_when_nothing_was_uploaded(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.tracks = [generated_track()]

    body = transcript(client)

    assert GENERATED_TEXT in body


def test_english_is_preferred_over_other_languages(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    spanish = manual_track(language_code="es")
    spanish.snippets = [{"text": "Bienvenidos de nuevo.", "start": 0.0, "duration": 2.0}]
    youtube.tracks = [spanish, generated_track(language_code="en")]

    body = transcript(client)

    assert GENERATED_TEXT in body
    assert "Bienvenidos" not in body


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "https://vimeo.com/123456789",
        "https://www.youtube.com/",
        "https://www.youtube.com/@fantasyfallout",
        "https://www.youtube.com/watch?v=tooshort",
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "javascript:alert(1)",
    ],
)
def test_a_malformed_or_non_youtube_url_is_rejected_before_any_network_call(
    client: TestClient, youtube: FakeYouTubeSource, url: str
) -> None:
    failure = sse.terminal(run_episode(client, url))

    assert failure.data["kind"] == "invalid_url"
    assert "YouTube" in failure.data["html"]
    assert youtube.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "  www.youtube.com/watch?v=dQw4w9WgXcQ  ",
    ],
)
def test_recognised_url_forms_all_resolve_to_the_same_episode(
    client: TestClient, youtube: FakeYouTubeSource, url: str
) -> None:
    assert sse.terminal(run_episode(client, url)).name == "done"
    assert ("list_tracks", "dQw4w9WgXcQ") in youtube.calls


def test_metadata_failure_falls_back_to_oembed_and_an_unknown_upload_date(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """One flaky yt-dlp call must not cost the whole run."""
    youtube.metadata_error = RuntimeError("HTTP Error 403: Forbidden")

    body = transcript(client)

    assert MANUAL_TEXT in body
    assert "Week 1 Waiver Wire Targets" in body
    assert "Fantasy Fallout" in body
    assert "Upload date unknown" in body
    assert "7 August 2026" not in body
    assert ("fetch_oembed", EPISODE_URL) in youtube.calls


def test_both_metadata_sources_failing_still_renders_the_transcript(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.metadata_error = RuntimeError("HTTP Error 403: Forbidden")
    youtube.oembed_error = RuntimeError("HTTP Error 404: Not Found")

    body = transcript(client)

    assert MANUAL_TEXT in body
    assert "Untitled episode" in body
    assert "Upload date unknown" in body


def test_a_captions_failure_reports_a_failure_rather_than_a_stack_trace(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """Which kinds a caption failure comes in is `test_failures.py`'s subject.
    What matters here is that a run that cannot read captions ends in words."""
    youtube.captions_error = RuntimeError("Subtitles are disabled for this video")

    failure = sse.terminal(run_episode(client))

    assert failure.name == "failed"
    assert failure.data["kind"] == "no_captions"
    assert "Traceback" not in failure.data["html"]


def test_metadata_is_requested_for_a_canonical_watch_url(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """A shortened or scheme-less paste still has to reach yt-dlp and oEmbed
    as a URL they accept."""
    youtube.metadata_error = RuntimeError("HTTP Error 403: Forbidden")

    run_episode(client, " youtu.be/dQw4w9WgXcQ ")

    assert ("fetch_metadata", EPISODE_URL) in youtube.calls
    assert ("fetch_oembed", EPISODE_URL) in youtube.calls
