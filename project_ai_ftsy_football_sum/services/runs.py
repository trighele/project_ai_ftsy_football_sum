"""Running an episode end to end, and following it while it happens.

A run is started by a request that returns at once with an identifier for it.
The work then happens in an in-process background task, and its progress
reaches the browser as Server-Sent Events. Nothing about an in-flight run is
written down, so a restart loses it — accepted deliberately: there is no
queue, no worker process, and nothing to recover from.

The event protocol is the part every later ticket builds on, so it is stated
here in one place:

- `stage`      — a part of the run has landed, with the words to say so.
- `transcript` — the episode panel, rendered, once the episode is resolved.
- `summary`    — a piece of the summary, in the order Claude wrote it.
- `done`       — the run finished and was saved. Terminal.
- `failed`     — the run did not finish, and why, by kind. Terminal.

Exactly one terminal event ends every run. A stream that merely stops is
indistinguishable from a hang, so the run engine never lets that happen.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from project_ai_ftsy_football_sum.container import Container, Edge
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.players import (
    NflverseUnavailableError,
    PlayerReference,
    ensure_reference,
)
from project_ai_ftsy_football_sum.services.store import Run, RunStore
from project_ai_ftsy_football_sum.services.summarize import (
    SummaryClient,
    summary_request,
)
from project_ai_ftsy_football_sum.services.transcripts import (
    Episode,
    InvalidUrlError,
    describe_episode,
    select_track,
    transcript_from,
    video_id_from_url,
    watch_url,
)
from project_ai_ftsy_football_sum.templating import fragment

#: The events that end a run. Every run emits exactly one of them.
TERMINAL_EVENTS = frozenset({"done", "failed"})

#: The parts of a run the reader is told about.
Stage = Literal["captions", "metadata", "players", "summarizing"]

#: Why a run stopped. The failures ticket completes this set — written down as
#: a type, like the container's edges, so a misspelt kind is a mistake that can
#: be seen rather than one that waits for the failure path to be taken.
FailureKind = Literal["invalid_url", "captions", "nflverse", "claude", "unknown"]

#: What the reader is told as each part of a run lands.
STAGE_LABELS: Mapping[Stage, str] = {
    "captions": "Captions retrieved",
    "metadata": "Episode identified",
    "players": "Player reference loaded",
    "summarizing": "Summarizing with Claude…",
}

#: What a failure of each kind is put to the reader as. The failures ticket
#: gives each kind its own wording; until then anything that is not an unusable
#: URL says one of these. An unusable URL says what was wrong with it, which is
#: the only failure the reader can do anything about, so it has no entry here.
FAILURE_MESSAGES: Mapping[FailureKind, str] = {
    "captions": (
        "Something went wrong retrieving this episode from YouTube. "
        "Check the link and try again."
    ),
    "nflverse": (
        "The player reference could not be fetched from nflverse, and nothing "
        "has been cached yet. Try again in a few minutes."
    ),
    "claude": (
        "Claude could not finish this summary. The transcript came back fine, "
        "so this is worth trying again."
    ),
    "unknown": "Something went wrong during this run. Try again.",
}

#: How many finished runs stay followable. A run is started by one request and
#: followed by another, so a finished one cannot be dropped the moment it ends.
RETAINED_RUNS = 32

#: How long a stream may go quiet before it says something anyway. Claude can
#: think for a minute before writing its first word, and an idle connection is
#: what a proxy between here and the browser closes.
KEEPALIVE_SECONDS = 15.0

#: A Server-Sent Events comment. Every client ignores it; every proxy counts
#: it as traffic.
KEEPALIVE_FRAME = ": keep-alive\n\n"


@dataclass(frozen=True)
class Event:
    """One thing that happened during a run, on its way to the browser."""

    name: str
    data: Mapping[str, Any]

    def encode(self) -> str:
        """The event as a single Server-Sent Events frame."""
        return f"event: {self.name}\ndata: {json.dumps(self.data)}\n\n"


class LiveRun:
    """One run in flight: what it has emitted, and how to follow it.

    Events are buffered rather than handed straight to a follower, because the
    browser starts a run and opens its event stream in two separate requests.
    Anything emitted in between would otherwise be lost, and on a fast episode
    that is most of the run.
    """

    def __init__(self, token: str) -> None:
        self.token = token
        self.events: list[Event] = []
        self.finished = False
        #: The background task, held onto so it is not collected mid-run.
        self.task: asyncio.Task[None] | None = None
        self._arrival = asyncio.Event()

    def publish(self, event: Event) -> None:
        """Record an event and wake every follower.

        Called on the event loop's thread only — the run itself is on a worker
        thread and reaches this through `call_soon_threadsafe`.
        """
        if self.finished:
            return
        self.events.append(event)
        self.finished = event.name in TERMINAL_EVENTS
        # Setting then clearing wakes whoever is waiting now and leaves the
        # flag down for the next wait. Nothing can slip between a follower's
        # buffer check and its wait: both run on this one loop, with no await
        # in between.
        self._arrival.set()
        self._arrival.clear()

    async def frames(
        self, keepalive: float = KEEPALIVE_SECONDS
    ) -> AsyncIterator[str]:
        """Everything this run has emitted, then everything it goes on to.

        Frames rather than events, because a run that is thinking rather than
        writing still has to say something often enough to keep the connection
        open, and a keep-alive is a frame that is not an event.
        """
        delivered = 0
        while True:
            while delivered < len(self.events):
                yield self.events[delivered].encode()
                delivered += 1
            if self.finished:
                return
            try:
                await asyncio.wait_for(self._arrival.wait(), keepalive)
            except TimeoutError:
                yield KEEPALIVE_FRAME


class LiveRuns:
    """The runs in flight, and the last few that have finished."""

    def __init__(self) -> None:
        self._runs: OrderedDict[str, LiveRun] = OrderedDict()

    def start(self) -> LiveRun:
        """Register a new run, ready to be followed."""
        run = LiveRun(token=uuid4().hex)
        self._runs[run.token] = run
        while len(self._runs) > RETAINED_RUNS:
            self._runs.pop(self._oldest_droppable())
        return run

    def _oldest_droppable(self) -> str:
        """The run to forget when there are too many.

        A finished run is only worth keeping until somebody has read it, so
        the oldest of those goes first. A run still in flight is dropped only
        when every retained run is in flight, which would mean something has
        gone much more wrong than a full registry.
        """
        for token, run in self._runs.items():
            if run.finished:
                return token
        return next(iter(self._runs))

    def get(self, token: str) -> LiveRun | None:
        """The run with that identifier, or `None` once it has aged out."""
        return self._runs.get(token)


class RunFailed(Exception):
    """A run cannot go on, and this is the kind of failure that stopped it."""

    def __init__(self, kind: FailureKind, message: str | None = None) -> None:
        self.kind = kind
        self.message = message or FAILURE_MESSAGES.get(
            kind, FAILURE_MESSAGES["unknown"]
        )
        super().__init__(self.message)


Publish = Callable[[Event], None]


def perform(
    *,
    url: str,
    container: Container,
    store: RunStore,
    players: PlayerCache,
    model: str,
    publish: Publish,
) -> None:
    """Do a whole run, announcing each part of it as it lands.

    Blocking from end to end and meant for a worker thread: every edge it uses
    is a synchronous library. It never raises — a failure is something the
    reader is told about, not something that leaves the stream hanging open.
    """
    started = time.perf_counter()
    try:
        episode = _resolve_episode(url, container, publish)
        reference = _load_players(container, players, publish)
        summary, model_used = _write_summary(episode, container, model, publish)
    except RunFailed as failure:
        publish(_failure_event(failure))
        return
    except Exception:  # noqa: BLE001 — a run must always end on the stream
        publish(_failure_event(RunFailed("unknown")))
        return

    elapsed = time.perf_counter() - started
    saved = store.save(
        Run.of(
            episode,
            duration_seconds=elapsed,
            summary=summary,
            model=model_used,
            season=reference.season,
        )
    )
    publish(_done_event(saved, elapsed))


def _load_players(
    container: Container, players: PlayerCache, publish: Publish
) -> PlayerReference:
    """Make sure the player reference is current before Claude is asked.

    A stale cache is synced here rather than on a schedule, so a run is never
    summarized against last week's depth charts and nobody has to remember to
    press anything. A sync that fails but leaves a cached reference behind is
    not a failure — see `ensure_reference`.
    """
    try:
        reference = ensure_reference(container, players)
    except NflverseUnavailableError as error:
        raise RunFailed("nflverse") from error
    publish(_stage_event("players"))
    return reference


def _resolve_episode(url: str, container: Container, publish: Publish) -> Episode:
    """Turn the submitted URL into the episode, telling the reader as it goes.

    What was pasted stays the episode's URL — it is what the reader will
    recognise in their history — but YouTube is always asked about the
    canonical watch URL, which every one of its services accepts.
    """
    try:
        video_id = video_id_from_url(url)
    except InvalidUrlError as error:
        raise RunFailed("invalid_url", str(error)) from error

    source = _edge(container, "captions", kind="captions")
    try:
        transcript = transcript_from(select_track(source.list_tracks(video_id)).fetch())
    except Exception as error:  # noqa: BLE001 — typed kinds arrive in ticket 09
        raise RunFailed("captions") from error
    publish(_stage_event("captions"))

    metadata = describe_episode(source, watch_url(video_id))
    publish(_stage_event("metadata"))

    episode = Episode(
        video_id=video_id,
        url=url.strip(),
        transcript=transcript,
        title=metadata.title,
        channel=metadata.channel,
        upload_date=metadata.upload_date,
    )
    publish(
        Event("transcript", {"html": fragment("fragments/episode.html", episode=episode)})
    )
    return episode


def _write_summary(
    episode: Episode, container: Container, model: str, publish: Publish
) -> tuple[str, str]:
    """Stream the summary out of Claude, publishing it as it is written."""
    claude: SummaryClient = _edge(container, "claude", kind="claude")
    request = summary_request(episode, model=model)
    publish(_stage_event("summarizing"))

    written: list[str] = []
    try:
        for text in claude.stream(request):
            written.append(text)
            publish(Event("summary", {"text": text}))
    except Exception as error:  # noqa: BLE001 — typed kinds arrive in ticket 09
        raise RunFailed("claude") from error
    return "".join(written), request.model


def _edge(container: Container, edge: Edge, *, kind: FailureKind) -> Any:
    """Resolve an edge, reporting a failure to build it as one of that edge."""
    try:
        return container.resolve(edge)
    except Exception as error:  # noqa: BLE001 — unwired, unconfigured, all one
        raise RunFailed(kind) from error


def lost_event() -> Event:
    """The terminal event for a run that stopped without saying why.

    `perform` reports its own failures, so this is only reached if the task
    running it died or was cancelled. Publishing it is what keeps a lost run
    from leaving its event stream open for as long as the browser waits.
    """
    return _failure_event(RunFailed("unknown"))


def _stage_event(stage: Stage) -> Event:
    return Event("stage", {"stage": stage, "label": STAGE_LABELS[stage]})


def _done_event(run: Run, elapsed: float) -> Event:
    return Event(
        "done",
        {
            "run_id": run.id,
            "href": f"/runs/{run.id}",
            "duration_seconds": round(elapsed, 1),
            "label": f"Summarized in {elapsed:.1f}s",
        },
    )


def _failure_event(failure: RunFailed) -> Event:
    return Event(
        "failed",
        {
            "kind": failure.kind,
            "message": failure.message,
            "html": fragment("fragments/failure.html", message=failure.message),
        },
    )
