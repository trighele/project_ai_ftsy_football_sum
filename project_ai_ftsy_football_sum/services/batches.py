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

What a submission has to survive before any of that is a paste. `batch_from`
is the whole of it and asks YouTube nothing: blank lines go, two lines naming
one episode become one, a line naming no episode becomes a row that has
already failed, and a submission that is not a batch at all — empty, or over
the cap — is refused with a `BatchRejected` rather than started. So a batch
arrives whole, which is what lets the queue be rendered before any work and
is why the work runs over `Batch.queued` rather than every row.

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
    episode_id,
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

#: The most episodes one submission may ask for. A cap rather than a queue
#: that takes anything: a paste gone wrong is an hour of work started by
#: accident, and ten is comfortably more than an evening's podcasts.
MAX_BATCH_EPISODES = 10

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


class BatchRejected(Exception):
    """The submission is not a batch: nothing is queued and nothing starts.

    Not a `RunFailed`, because no episode failed and no work was begun — the
    reader is being told about what they pasted rather than about what became
    of it. It carries only its message, which is the whole of what the panel
    saying so needs.
    """


@dataclass
class BatchEpisode:
    """One episode of a batch, and how far it has got.

    Mutable, unlike almost everything else here, because it is the row: the
    browser is shown it queued, then running, then finished, and what changes
    between those is this object rather than three of them.

    `position` is its place in the batch and never changes — it is what the
    browser finds the row by, and it is why the episodes are numbered here
    rather than identified by URL: two lines of a paste can name one episode,
    and only one of them becomes a row.

    A row can arrive already `failed`: a line that is not a usable URL is
    failed while the batch is being made sense of, before anything starts.
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
    def queued(self) -> list[BatchEpisode]:
        """The episodes waiting to be summarized.

        Not every row of a queue is work waiting: a line that named no episode
        is a failed row before the batch starts, and it is there to be counted
        and read rather than to be summarized.
        """
        return [episode for episode in self.episodes if episode.state == "queued"]

    @property
    def starting_label(self) -> str:
        """What the panel says before any episode has finished.

        The episodes that are going to be worked on, which is not always every
        row: a queue that opens by promising to summarize three episodes with
        one of them already showing Failed has miscounted in front of the
        reader.
        """
        waiting = self.queued
        if not waiting:
            return "Nothing here could be summarized."
        return f"Summarizing {_episode_count(len(waiting))}…"

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
    """The submitted text as a batch, or a refusal to make one of it.

    A list pasted out of a notes app is rarely tidy, and every untidiness is
    dealt with here rather than out at the edges, because all of it is answered
    without asking YouTube anything:

    - Blank and whitespace-only lines are dropped. They are not episodes.
    - Each line is parsed into a video identifier, and a line that is not a
      usable YouTube URL becomes a failed row with the same `invalid_url` kind
      a single run would stop with. It is a row rather than a dropped line, so
      the reader is told which of their lines this app could make nothing of.
    - Two lines naming one episode become one row, the first of them, so a
      share link and a watch link of the same episode are summarized once.
      The URL kept is the one pasted first, because that is the one the reader
      wrote and the one they will recognise in their history.

    Raises `BatchRejected` for a submission that is not a batch at all: an
    empty one, or one asking for more than `MAX_BATCH_EPISODES` episodes.
    Nothing is started either way. The cap counts what would be summarized
    rather than the lines pasted, because it is a cap on the work a submission
    asks for: a second line naming an episode already listed is not more work,
    and neither is a line naming no episode — refusing ten good URLs over a
    typo among them would cost the reader the very thing failing that line
    early is meant to save.
    """
    episodes: list[BatchEpisode] = []
    seen: set[str] = set()
    for line in submitted.splitlines():
        url = line.strip()
        if not url:
            continue
        try:
            video_id = episode_id(url)
        except RunFailed as failure:
            episodes.append(
                _failed_row(position=len(episodes), url=url, failure=failure)
            )
            continue
        if video_id in seen:
            continue
        seen.add(video_id)
        episodes.append(BatchEpisode(position=len(episodes), url=url))

    if not episodes:
        raise BatchRejected("Paste at least one YouTube URL to summarize a batch.")

    batch = Batch(episodes=episodes)
    asked_for = len(batch.queued)
    if asked_for > MAX_BATCH_EPISODES:
        raise BatchRejected(
            f"A batch takes at most {MAX_BATCH_EPISODES} episodes, and this "
            f"submission asks for {asked_for}. Summarize them a few at a time."
        )
    return batch


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

    Only the queued episodes are worked on: a row `batch_from` already failed
    is not asked about again, and it is counted at the end with the rest.
    """
    for episode in batch.queued:
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


def _failed_row(*, position: int, url: str, failure: RunFailed) -> BatchEpisode:
    """A line that names no episode, as the row saying so.

    A row rather than a dropped line, and the pipeline's own failure rather
    than one written again here, so that a batch tells the reader exactly what
    a single run would have told them about the same paste.
    """
    return BatchEpisode(position=position, url=url, state="failed", failure=failure)


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
