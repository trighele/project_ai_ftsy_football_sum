"""Summarizing several episodes from one submission, as a queue.

A batch is the second caller of `services/pipeline.py`. The work it does per
episode is the run's work, unchanged and unreimplemented — what differs is the
*telling*: a run narrates one episode in detail, and a batch reports which of
several it is on. So there are no stages here and no summary text; there is a
row per episode, and it changes state.

A batch is ephemeral and in-process exactly as a run is (ADR-0003): a token, a
buffered event list, exactly one terminal event, and nothing written down. It
is followed through the same `LiveRuns` registry a run is, under event names of
its own:

- `batch-episode` — one queue row changed state, rendered. Not terminal, and
                    emitted as many times per episode as the row changes.
- `batch-done`    — every episode is terminal, with the counts. Terminal.
- `batch-failed`  — the batch itself stopped, the way a lost run does.
                    Terminal.

Its own names rather than the run's, so the two client scripts cannot misread
each other's streams. `batch-done` is emitted even when every episode failed:
a batch that ran is a batch that finished, and the counts are what say how it
went.

A failing episode does not stop the ones after it — `RunFailed` is the whole
of what the pipeline raises for an episode that cannot be summarized, so it is
caught per episode and becomes that row's failure. Anything else the pipeline
lets through is a failure of the store rather than of an episode, and it ends
the batch the same way it ends a run: the driving task dies and `lost_event`
closes the stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.failures import RunFailed
from project_ai_ftsy_football_sum.services.pipeline import (
    EpisodeProgress,
    summarize_episode,
)
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.runs import (
    Event,
    Publish,
    failure_event,
)
from project_ai_ftsy_football_sum.services.store import RunStore
from project_ai_ftsy_football_sum.services.transcripts import Episode
from project_ai_ftsy_football_sum.templating import fragment

#: The events that end a batch. Handed to the registry that holds one, which
#: is how the same machinery ends a run on `done` and a batch on these.
TERMINAL_EVENTS = frozenset({"batch-done", "batch-failed"})

#: Where one episode of a batch has got to. `done` and `failed` are the two
#: an episode stops on; a batch is over when every row is on one of them.
EpisodeState = Literal["queued", "running", "done", "failed"]

#: What each state is put to the reader as, in the pill at the end of its row.
STATE_LABELS: dict[EpisodeState, str] = {
    "queued": "Queued",
    "running": "Summarizing…",
    "done": "Done",
    "failed": "Failed",
}


@dataclass
class BatchEpisode:
    """One episode of a batch, and how far it has got.

    Mutable, unlike almost everything else here, because it is the row: the
    browser is shown it queued, then running, then finished, and what changes
    between those is this object rather than three of them.

    `position` is its place in the submission and never changes — it is what
    the browser finds the row by, and it is why the episodes are numbered here
    rather than identified by URL, which ticket 10 will collapse duplicates of.
    """

    position: int
    url: str
    state: EpisodeState = "queued"
    title: str | None = None
    run_id: int | None = None
    failure: RunFailed | None = None

    @property
    def label(self) -> str:
        """What the row calls this episode.

        The title once YouTube has been asked, and until then what was pasted.
        Which means a row that never resolved — the one a reader might want to
        paste somewhere else and try again — shows the URL, and one that did
        shows the episode.
        """
        return self.title or self.url

    @property
    def state_label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def href(self) -> str | None:
        """Where this episode's saved run lives, once there is one."""
        return None if self.run_id is None else f"/runs/{self.run_id}"


@dataclass(frozen=True)
class BatchCounts:
    """How a batch went: the totals its terminal event carries."""

    total: int
    summarized: int
    failed: int

    @property
    def label(self) -> str:
        """How the batch's ending is put to the reader.

        Both halves only when there are both, because "2 summarized, 0 failed"
        makes a reader look for a failure that never happened.
        """
        if self.summarized and self.failed:
            return f"{self.summarized} summarized, {self.failed} failed"
        if self.failed:
            return f"{_episode_count(self.failed)} failed"
        return f"{_episode_count(self.summarized)} summarized"


@dataclass(frozen=True)
class Batch:
    """One submission: its episodes, in the order they were submitted.

    Episodes rather than a queue, because a queue is what the *page* shows —
    the batch itself is the set of episodes somebody asked for (CONTEXT.md).
    """

    episodes: list[BatchEpisode] = field(default_factory=list)

    @property
    def starting_label(self) -> str:
        """What the panel says before any episode has finished."""
        return f"Summarizing {_episode_count(len(self.episodes))}…"

    def counts(self) -> BatchCounts:
        return BatchCounts(
            total=len(self.episodes),
            summarized=sum(
                1 for episode in self.episodes if episode.state == "done"
            ),
            failed=sum(
                1 for episode in self.episodes if episode.state == "failed"
            ),
        )


def batch_from(submitted: str) -> Batch:
    """The submitted text as a queue: one episode per line, in that order.

    Lines are trimmed and empty ones dropped, which is the least a "one per
    line" field can do and not the guarantee ticket 10 makes of it. Nothing
    else is made of the text here: what a batch does about a line that is not
    a usable URL, about the same episode listed twice, and about a paste far
    longer than a batch is allowed to be, is all ticket 10's.
    """
    urls = [line.strip() for line in submitted.splitlines()]
    return Batch(
        episodes=[
            BatchEpisode(position=position, url=url)
            for position, url in enumerate(url for url in urls if url)
        ]
    )


def perform_batch(
    *,
    batch: Batch,
    container: Container,
    store: RunStore,
    players: PlayerCache,
    model: str,
    publish: Publish,
) -> None:
    """Summarize every episode of a batch, one after another, reporting rows.

    Blocking from end to end and meant for a worker thread, like the pipeline
    it drives. One episode at a time and in the order submitted: every edge is
    a blocking library, and serial turns YouTube's rate limiting into a slower
    batch rather than a dead one (ADR-0003).

    The player reference is ensured per episode through the pipeline's own
    call, which the twelve-hour cache makes one sync for the whole batch —
    and which keeps a long batch from working against a reference that went
    stale halfway through it.
    """
    for episode in batch.episodes:
        _summarize_episode(
            episode,
            container=container,
            store=store,
            players=players,
            model=model,
            publish=publish,
        )
    publish(_finished_event(batch.counts()))


def lost_event() -> Event:
    """The terminal event for a batch that stopped without saying why.

    Reached only if the task driving the batch died — every failure an episode
    can have is already a failed row — and publishing it is what keeps a lost
    batch from leaving its event stream open for as long as the browser waits.
    """
    return failure_event(
        "batch-failed",
        RunFailed(
            "unknown",
            detail="The task running this batch ended without reporting anything.",
        ),
        heading="Batch stopped",
    )


def _summarize_episode(
    episode: BatchEpisode,
    *,
    container: Container,
    store: RunStore,
    players: PlayerCache,
    model: str,
    publish: Publish,
) -> None:
    """One episode of the batch: run it, and leave its row saying how it went.

    `RunFailed` is caught rather than raised on, because it is the pipeline's
    word for an episode that cannot be summarized and one of those must not
    cost the reader the episodes after it. Anything else is not about this
    episode and is left to end the batch.
    """
    episode.state = "running"
    publish(_row_event(episode))
    try:
        finished = summarize_episode(
            url=episode.url,
            container=container,
            store=store,
            players=players,
            model=model,
            # A note is written about a particular episode, and a batch is the
            # case where the reader is not sitting with each one.
            context_note=None,
            progress=_RowTitle(episode),
        )
    except RunFailed as failure:
        episode.state = "failed"
        episode.failure = failure
    else:
        episode.state = "done"
        episode.run_id = finished.run.id
        episode.title = finished.run.title
    publish(_row_event(episode))


class _RowTitle(EpisodeProgress):
    """The batch's telling of a pipeline: the episode's name, and nothing else.

    A queue reports which episode is being worked on, not how it is going, so
    every other report the pipeline offers is deliberately left on the floor —
    the stages, the stale reference, and the summary a word at a time all
    belong to the run page each of these episodes is saved as.

    The row is not published from here: the title arriving is worth showing,
    but it is one of two changes that happen while an episode is running and
    `_summarize_episode` is where both are told about.
    """

    def __init__(self, episode: BatchEpisode) -> None:
        self._episode = episode

    def episode_resolved(self, resolved: Episode) -> None:
        self._episode.title = resolved.title


def _row_event(episode: BatchEpisode) -> Event:
    """That one row has changed, and the row.

    The row travels rendered, as every other fragment on an event stream does:
    the server owns the markup and the browser puts it where the position says.
    """
    return Event(
        "batch-episode",
        {
            "position": episode.position,
            "state": episode.state,
            "html": fragment("fragments/queue_row.html", episode=episode),
        },
    )


def _finished_event(counts: BatchCounts) -> Event:
    return Event(
        "batch-done",
        {
            "total": counts.total,
            "summarized": counts.summarized,
            "failed": counts.failed,
            "label": counts.label,
        },
    )


def _episode_count(count: int) -> str:
    """A number of episodes, in words that read for one of them too."""
    return f"{count} episode" if count == 1 else f"{count} episodes"
