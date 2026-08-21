"""Driving work the way the browser does, and reading back what it emitted.

A run is two requests: one that starts it, and one that follows it. The second
ends when the run does, so a test can ask for the whole stream in one call and
assert on it afterwards. A batch is started and followed the same way, under
its own event names, which is why the helpers for one sit beside the other.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.services.batches import (
    TERMINAL_EVENTS as BATCH_TERMINAL,
)
from project_ai_ftsy_football_sum.services.transcripts import watch_url
from tests.fakes import FakeYouTubeSource, fixture

EPISODE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

#: Three episodes a submission of several at once can tell apart. Eleven
#: characters because a YouTube identifier is, and spelt so that a saved run
#: says which line of the submission it came from.
BATCH_VIDEO_IDS = ("episode0001", "episode0002", "episode0003")
BATCH_URLS = tuple(watch_url(video_id) for video_id in BATCH_VIDEO_IDS)

#: Where the panel the server hands back says its events will arrive.
_EVENTS_URL = re.compile(r'data-run-events="([^"]+)"')
_BATCH_EVENTS_URL = re.compile(r'data-batch-events="([^"]+)"')


@dataclass(frozen=True)
class Event:
    """One Server-Sent Events frame, decoded."""

    name: str
    data: dict[str, Any]


def start(
    client: TestClient, url: str = EPISODE_URL, context_note: str | None = None
) -> str:
    """Start a run; hand back the URL its events arrive on.

    `context_note` is left out of the submission entirely when it is `None`,
    because a form without the field and a form with an empty one are two
    different things to have to behave the same way about.
    """
    submitted = {"youtube_url": url}
    if context_note is not None:
        submitted["context_note"] = context_note
    response = client.post("/runs", data=submitted)
    assert response.status_code == 202, response.text
    found = _EVENTS_URL.search(response.text)
    assert found is not None, response.text
    return found.group(1)


def start_batch(client: TestClient, urls: Sequence[str] = BATCH_URLS) -> str:
    """Submit several episodes at once; hand back the queue's event stream.

    The submission is the textarea's own text — one URL per line — rather than
    a list, because that is what the browser posts and what the server has to
    make sense of.
    """
    response = client.post("/batches", data={"youtube_urls": "\n".join(urls)})
    assert response.status_code == 202, response.text
    found = _BATCH_EVENTS_URL.search(response.text)
    assert found is not None, response.text
    return found.group(1)


def run_batch(
    client: TestClient, urls: Sequence[str] = BATCH_URLS
) -> list[Event]:
    """Start a batch and wait for the whole queue to finish."""
    return follow(client, start_batch(client, urls))


def follow(client: TestClient, events_url: str) -> list[Event]:
    """Every event a run emits, up to and including the one that ends it."""
    response = client.get(events_url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return decode(response.text)


def run_episode(
    client: TestClient, url: str = EPISODE_URL, context_note: str | None = None
) -> list[Event]:
    """Start a run and wait for it to finish."""
    return follow(client, start(client, url, context_note))


def run_titled(
    client: TestClient,
    youtube: FakeYouTubeSource,
    title: str,
    uploaded: str | None = None,
) -> None:
    """Run one episode that can be told apart from the others by its title.

    `uploaded` is the episode's own upload date in the `YYYYMMDD` form yt-dlp
    reports, for a test whose subject is the order episodes went up in rather
    than the order they were summarized in. `""` is an episode whose upload
    date never resolved.
    """
    metadata = {**fixture("metadata"), "title": title}
    if uploaded is not None:
        metadata["upload_date"] = uploaded
    youtube.metadata = metadata
    run_episode(client)


def decode(payload: str) -> list[Event]:
    """The events in a stream. Keep-alives are frames but not events."""
    events = []
    for frame in payload.split("\n\n"):
        if not frame.strip() or frame.startswith(":"):
            continue
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append(Event(fields["event"], json.loads(fields["data"])))
    return events


def outline(events: list[Event]) -> list[str]:
    """The event sequence as a protocol, with the summary's pieces collapsed.

    Stage events are named by the stage they announce; a run of summary events
    reads as one `summary`, because how many pieces Claude writes in is its
    business and not part of the protocol.
    """
    sequence = []
    for event in events:
        name = f"stage:{event.data['stage']}" if event.name == "stage" else event.name
        if name == "summary" and sequence[-1:] == ["summary"]:
            continue
        sequence.append(name)
    return sequence


def named(events: list[Event], name: str) -> list[Event]:
    return [event for event in events if event.name == name]


def one(events: list[Event], name: str) -> Event:
    """The single event of that name. Fails if there is not exactly one."""
    matching = named(events, name)
    assert len(matching) == 1, [event.name for event in events]
    return matching[0]


def summary_text(events: list[Event]) -> str:
    """The summary as the browser would have assembled it."""
    return "".join(event.data["text"] for event in named(events, "summary"))


def transcript_html(events: list[Event]) -> str:
    """The episode panel the run rendered."""
    return one(events, "transcript").data["html"]


def terminal(
    events: list[Event], names: Collection[str] = ("done", "failed")
) -> Event:
    """The event that ended the run, or the batch if its names are given.

    Exactly one of them, and last: a stream with a terminal event in the
    middle of it would be one the browser stopped reading early.
    """
    assert events, "the stream emitted nothing at all"
    ending = [event for event in events if event.name in names]
    assert len(ending) == 1, outline(events)
    assert ending[0] is events[-1], outline(events)
    return events[-1]


def batch_terminal(events: list[Event]) -> Event:
    """The event that ended a batch, whichever of its two it was."""
    return terminal(events, BATCH_TERMINAL)
