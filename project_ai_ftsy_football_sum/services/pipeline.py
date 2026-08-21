"""Summarizing one episode, end to end, apart from how it is told about.

Resolve the URL into an episode, make sure the player reference is current,
stream the summary out of Claude, save the run. That is the whole of the work,
and it is the same work whoever asked for it. It has two callers — a single
run, which wraps it in the events it publishes as it goes (`services/runs.py`),
and a batch, which wraps it in a queue row (`services/batches.py`) — and it is
a module of its own so that the second wraps this rather than re-implementing
it, which is the only thing that keeps the two from drifting into producing
different summaries.

What the pipeline owes a caller is a *report* rather than a rendering: which
part of the work has landed, the episode once it is known, that the player
reference is older than it wanted, and the summary as it is written. Those are
facts about the work. Words, markup, and event names are the caller's, because
they are what differs between the two callers and nothing else does.

Blocking from end to end and meant for a worker thread: every edge it uses is a
synchronous library. Everything that can go wrong out at an edge arrives as a
`RunFailed` carrying its kind, the `unknown` kind included, so no caller has to
invent an answer for an exception it did not expect. Saving the finished run is
the one step outside that: the store is local disk rather than an edge, and a
failure there is not one of the kinds a reader can act on, so it propagates and
is left to whatever the caller does with a task that died.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from project_ai_ftsy_football_sum.container import Container, Edge
from project_ai_ftsy_football_sum.services.failures import (
    FailureKind,
    RunFailed,
    classify_youtube_error,
)
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.players import (
    NflverseUnavailableError,
    PlayerReference,
    ReferenceOutcome,
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

#: The parts of the work, in the order they land. Named here rather than where
#: they are announced, because they are steps of the work itself — what each is
#: put to a reader as belongs to whoever is doing the telling.
Stage = Literal["captions", "metadata", "players", "summarizing"]


class EpisodeProgress:
    """What a caller is told while an episode is summarized.

    Every method does nothing by default, so a caller overrides the reports it
    has somewhere to put and stays silent about the rest — a queue row has no
    use for the summary a word at a time, and saying so should not cost it a
    method body. The default instance is the "nobody is watching" caller.
    """

    def stage_reached(self, stage: Stage) -> None:
        """A part of the work has landed."""

    def episode_resolved(self, episode: Episode) -> None:
        """The URL is now an episode: captions, title, channel, upload date."""

    def reference_stale(self, outcome: ReferenceOutcome) -> None:
        """The work is going ahead against a reference older than it wanted."""

    def summary_written(self, text: str) -> None:
        """A piece of the summary, in the order Claude wrote it."""


#: The caller that wants none of it. Stateless, so one is enough.
SILENT = EpisodeProgress()


@dataclass(frozen=True)
class Summarized:
    """An episode summarized and saved: what came of the work.

    The summary travels beside the saved run that already holds it because a
    caller that renders it should not have to know the column is nullable.
    """

    run: Run
    summary: str
    elapsed_seconds: float


def episode_id(url: str) -> str:
    """Which episode a submitted URL names, or the failure to report for it.

    Public because a batch validates a whole paste before it starts any of it
    (`services/batches.py`), and what a line that names no episode *is* must
    be one answer rather than two: the same `invalid_url` kind, and the URL
    parser's own words rather than the kind's generic ones, since it knows
    whether what was pasted was the wrong site, the wrong kind of link, or
    nothing at all.
    """
    try:
        return video_id_from_url(url)
    except InvalidUrlError as error:
        raise RunFailed.of("invalid_url", error, str(error)) from error


def summarize_episode(
    *,
    url: str,
    container: Container,
    store: RunStore,
    players: PlayerCache,
    model: str,
    context_note: str | None,
    progress: EpisodeProgress = SILENT,
) -> Summarized:
    """Summarize one episode and save the run, reporting as it goes.

    `context_note` arrives already made sense of — see
    `summarize.context_note_from` — because the page that starts a run shows
    the note back straight away, and a note shown differently from the one sent
    and kept would be a lie about what was asked for.

    Raises `RunFailed` for anything that goes wrong on the way to a summary,
    an error nothing recognises included — that one is given the `unknown` kind
    here rather than left for each caller to catch. A failure of the store
    itself propagates as it is; see the module docstring.
    """
    started = time.perf_counter()
    try:
        episode = _resolve_episode(url, container, progress, context_note=context_note)
        reference = _load_players(container, players, progress)
        summary, model_used = _write_summary(
            episode, reference, container, model, progress
        )
    except RunFailed:
        raise
    except Exception as error:  # noqa: BLE001 — a caller answers for one kind
        raise RunFailed.of("unknown", error) from error

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
    return Summarized(run=saved, summary=summary, elapsed_seconds=elapsed)


def _resolve_episode(
    url: str,
    container: Container,
    progress: EpisodeProgress,
    *,
    context_note: str | None,
) -> Episode:
    """Turn the submitted URL into the episode, reporting as it goes.

    What was pasted stays the episode's URL — it is what the reader will
    recognise in their history — but YouTube is always asked about the
    canonical watch URL, which every one of its services accepts.
    """
    video_id = episode_id(url)

    # `unknown` rather than one of the YouTube kinds: an edge that cannot be
    # built is a missing library or a bad configuration here, and telling the
    # reader that YouTube blocked them would send them to wait out an outage
    # that is ours. `unknown` says so and shows the error.
    source = _edge(container, "captions", kind="unknown")
    try:
        transcript = transcript_from(select_track(source.list_tracks(video_id)).fetch())
    except Exception as error:  # noqa: BLE001 — the kind is read off the error
        raise RunFailed.of(classify_youtube_error(error), error) from error
    progress.stage_reached("captions")

    metadata = describe_episode(source, watch_url(video_id))
    progress.stage_reached("metadata")

    episode = Episode(
        video_id=video_id,
        url=url.strip(),
        transcript=transcript,
        title=metadata.title,
        channel=metadata.channel,
        upload_date=metadata.upload_date,
        context_note=context_note,
    )
    progress.episode_resolved(episode)
    return episode


def _load_players(
    container: Container, players: PlayerCache, progress: EpisodeProgress
) -> PlayerReference:
    """Make sure the player reference is current before Claude is asked.

    A stale cache is synced here rather than on a schedule, so an episode is
    never summarized against last week's depth charts and nobody has to
    remember to press anything. A sync that fails but leaves a cached reference
    behind is not a failure — the work goes ahead against the older reference,
    and says out loud how old it is, because an upstream outage should cost
    accuracy rather than the whole summary.
    """
    try:
        outcome = ensure_reference(container, players)
    except NflverseUnavailableError as error:
        raise RunFailed.of("nflverse", error) from error
    progress.stage_reached("players")
    if outcome.sync_error is not None:
        progress.reference_stale(outcome)
    return outcome.reference


def _write_summary(
    episode: Episode,
    reference: PlayerReference,
    container: Container,
    model: str,
    progress: EpisodeProgress,
) -> tuple[str, str]:
    """Stream the summary out of Claude, reporting it as it is written."""
    claude: SummaryClient = _edge(container, "claude", kind="claude")
    request = summary_request(episode, reference, model=model)
    progress.stage_reached("summarizing")

    written: list[str] = []
    try:
        for text in claude.stream(request):
            written.append(text)
            progress.summary_written(text)
    except Exception as error:  # noqa: BLE001 — every API failure reads the same
        raise RunFailed.of("claude", error) from error
    return "".join(written), request.model


def _edge(container: Container, edge: Edge, *, kind: FailureKind) -> Any:
    """Resolve an edge, reporting a failure to build it as one of that edge."""
    try:
        return container.resolve(edge)
    except Exception as error:  # noqa: BLE001 — unwired, unconfigured, all one
        raise RunFailed.of(kind, error) from error
