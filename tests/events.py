"""Driving a run the way the browser does, and reading back what it emitted.

A run is two requests: one that starts it, and one that follows it. The second
ends when the run does, so a test can ask for the whole stream in one call and
assert on it afterwards.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

EPISODE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

#: Where the panel the server hands back says its events will arrive.
_EVENTS_URL = re.compile(r'data-run-events="([^"]+)"')


@dataclass(frozen=True)
class Event:
    """One Server-Sent Events frame, decoded."""

    name: str
    data: dict[str, Any]


def start(client: TestClient, url: str = EPISODE_URL) -> str:
    """Start a run; hand back the URL its events arrive on."""
    response = client.post("/runs", data={"youtube_url": url})
    assert response.status_code == 202, response.text
    found = _EVENTS_URL.search(response.text)
    assert found is not None, response.text
    return found.group(1)


def follow(client: TestClient, events_url: str) -> list[Event]:
    """Every event a run emits, up to and including the one that ends it."""
    response = client.get(events_url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return decode(response.text)


def run_episode(client: TestClient, url: str = EPISODE_URL) -> list[Event]:
    """Start a run and wait for it to finish."""
    return follow(client, start(client, url))


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


def terminal(events: list[Event]) -> Event:
    """The event that ended the run."""
    assert events, "the run emitted nothing at all"
    assert events[-1].name in {"done", "failed"}, outline(events)
    return events[-1]
