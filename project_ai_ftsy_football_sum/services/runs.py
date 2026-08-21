"""Following a run while it happens, and telling the browser about it.

The work itself — resolve the episode, ensure the player reference, stream the
summary, save the run — is `services/pipeline.py`, and is shared with anything
else that summarizes an episode. What is here is the single-run *telling* of
it: one event per thing the pipeline reports, and exactly one terminal event
whatever happens — along with the machinery every telling shares, since a
batch (`services/batches.py`) is followed through the same buffered stream and
stops on the same rendered panel.

A run is started by a request that returns at once with an identifier for it.
The work then happens in an in-process background task, and its progress
reaches the browser as Server-Sent Events. Nothing about an in-flight run is
written down, so a restart loses it — accepted deliberately: there is no
queue, no worker process, and nothing to recover from.

The event protocol is the part every later ticket builds on, so it is stated
here in one place:

- `stage`      — a part of the run has landed, with the words to say so.
- `transcript` — the episode panel, rendered, once the episode is resolved.
- `warning`    — the run is going ahead on something less than it wanted.
- `summary`    — a piece of the summary, in the order Claude wrote it.
- `done`       — the run finished and was saved, with the summary rendered.
                 Terminal.
- `failed`     — the run did not finish, and why, by kind. Terminal.

Exactly one terminal event ends every run. A stream that merely stops is
indistinguishable from a hang, so the run engine never lets that happen.
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.failures import RunFailed
from project_ai_ftsy_football_sum.services.markdown import render_markdown
from project_ai_ftsy_football_sum.services.pipeline import (
    EpisodeProgress,
    Stage,
    summarize_episode,
)
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.players import ReferenceOutcome
from project_ai_ftsy_football_sum.services.store import Run, RunStore
from project_ai_ftsy_football_sum.services.transcripts import Episode
from project_ai_ftsy_football_sum.templating import fragment

#: The events that end a run. Every run emits exactly one of them.
#:
#: Which names are terminal is the *stream's* business rather than this
#: module's — a batch follows the same machinery under names of its own
#: (`services/batches.py`) — so it is handed to `LiveRun` rather than read off
#: this constant, and this is only the default a run gets.
TERMINAL_EVENTS = frozenset({"done", "failed"})

#: What the reader is told as each part of a run lands. The parts themselves
#: are the pipeline's (`pipeline.Stage`); what to call them is this file's.
STAGE_LABELS: Mapping[Stage, str] = {
    "captions": "Captions retrieved",
    "metadata": "Episode identified",
    "players": "Player reference loaded",
    "summarizing": "Summarizing with Claude…",
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

    def __init__(self, token: str, terminal: frozenset[str]) -> None:
        self.token = token
        self.terminal = terminal
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
        self.finished = event.name in self.terminal
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
    """The work in flight, and the last few pieces of it that have finished.

    A batch is followed through one of these too, under its own terminal event
    names: it is started by one request and followed by another exactly as a
    run is, so it wants the same buffering and the same retention rather than
    a second registry that would have to be kept in step with this one.
    """

    def __init__(self, terminal: frozenset[str] = TERMINAL_EVENTS) -> None:
        self._terminal = terminal
        self._runs: OrderedDict[str, LiveRun] = OrderedDict()

    def start(self) -> LiveRun:
        """Register a new run, ready to be followed."""
        run = LiveRun(token=uuid4().hex, terminal=self._terminal)
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


Publish = Callable[[Event], None]


class _RunEvents(EpisodeProgress):
    """The single-run telling of a pipeline: one event per thing it reports.

    This is the whole of what separates a run from any other caller of the
    pipeline — words for the stages, a rendered panel for the episode, and the
    summary a piece at a time because the reader watches it being written.
    """

    def __init__(self, publish: Publish) -> None:
        self._publish = publish

    def stage_reached(self, stage: Stage) -> None:
        self._publish(_stage_event(stage))

    def episode_resolved(self, episode: Episode) -> None:
        self._publish(
            Event(
                "transcript",
                {"html": fragment("fragments/episode.html", episode=episode)},
            )
        )

    def reference_stale(self, outcome: ReferenceOutcome) -> None:
        self._publish(_warning_event(outcome))

    def summary_written(self, text: str) -> None:
        self._publish(Event("summary", {"text": text}))


def perform(
    *,
    url: str,
    container: Container,
    store: RunStore,
    players: PlayerCache,
    model: str,
    publish: Publish,
    context_note: str | None,
) -> None:
    """Do a whole run, announcing each part of it as it lands.

    Blocking from end to end and meant for a worker thread, because the
    pipeline it drives is. Every failure the pipeline names is told to the
    reader rather than raised, because an exception here would leave the
    stream hanging open; anything it does not name — a failure of the store
    itself — ends the task, and `lost_event` is what closes the stream then.
    """
    try:
        finished = summarize_episode(
            url=url,
            container=container,
            store=store,
            players=players,
            model=model,
            context_note=context_note,
            progress=_RunEvents(publish),
        )
    except RunFailed as failure:
        publish(_failure_event(failure))
        return
    publish(_done_event(finished.run, finished.elapsed_seconds, finished.summary))


def lost_event() -> Event:
    """The terminal event for a run that stopped without saying why.

    `perform` reports its own failures, so this is only reached if the task
    running it died or was cancelled. Publishing it is what keeps a lost run
    from leaving its event stream open for as long as the browser waits.
    """
    return _failure_event(
        RunFailed(
            "unknown",
            detail="The task running this summary ended without reporting anything.",
        )
    )


def _stage_event(stage: Stage) -> Event:
    return Event("stage", {"stage": stage, "label": STAGE_LABELS[stage]})


def _warning_event(outcome: ReferenceOutcome) -> Event:
    """That the run is going ahead on a reference older than it wanted.

    Its own event rather than part of the summary, because it is true of the
    whole run and is worth reading before the summary it qualifies.
    """
    return Event(
        "warning",
        {
            "kind": "nflverse",
            "html": fragment(
                "fragments/stale_reference.html",
                reference=outcome.reference,
                detail=outcome.sync_detail,
            ),
        },
    )


def _done_event(run: Run, elapsed: float, summary: str) -> Event:
    """That the run finished, and the summary it finished with as prose.

    The rendered summary travels on the terminal event rather than being asked
    for afterwards, so the run the reader has just watched formats itself
    without a reload and without a second request. It is the whole of what was
    streamed, rendered once — the pieces the browser assembled and this HTML
    are the same summary or the page is lying about what it watched.

    `download_href` is here for the same reason every fragment is: the server
    says where a run's document lives, and Copy and Download are handed it
    rather than each assembling a URL out of the identifier beside it.
    """
    return Event(
        "done",
        {
            "run_id": run.id,
            "href": f"/runs/{run.id}",
            "download_href": f"/runs/{run.id}/download",
            "duration_seconds": round(elapsed, 1),
            "label": f"Summarized in {elapsed:.1f}s",
            "summary_html": render_markdown(summary),
        },
    )


def failure_event(name: str, failure: RunFailed, *, heading: str) -> Event:
    """That work stopped, and the panel saying why.

    Shared with a batch rather than written twice: what differs between the
    two is the event's name and the two words at the top of the panel, and
    everything a reader is actually told — the kind, the message, the error
    behind its toggle — is owed to them identically either way.
    """
    return Event(
        name,
        {
            "kind": failure.kind,
            "message": failure.message,
            "html": fragment(
                "fragments/failure.html",
                heading=heading,
                message=failure.message,
                detail=failure.detail,
            ),
        },
    )


def _failure_event(failure: RunFailed) -> Event:
    return failure_event("failed", failure, heading="Run stopped")
