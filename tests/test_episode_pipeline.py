"""Summarizing one episode, with nobody watching.

The pipeline is the work; a run is one way of telling somebody about it. These
tests call the work directly — no application, no event stream — because that
is the whole point of the extraction: a second caller can wrap the same
pipeline in a different telling, and the two cannot drift into producing
different summaries. What a *run* makes of the same pipeline is
`test_summary_stream.py`'s subject and stays there.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from project_ai_ftsy_football_sum.config import DEFAULT_MODEL
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.failures import RunFailed
from project_ai_ftsy_football_sum.services.pipeline import (
    SILENT,
    EpisodeProgress,
    Stage,
    summarize_episode,
)
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.players import (
    CACHE_TTL,
    ReferenceOutcome,
    sync_reference,
)
from project_ai_ftsy_football_sum.services.store import RunStore
from project_ai_ftsy_football_sum.services.transcripts import Episode
from tests.events import EPISODE_URL
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "runs.db")
    store.initialize()
    return store


@pytest.fixture
def players(store: RunStore) -> PlayerCache:
    cache = PlayerCache(store.path)
    cache.initialize()
    return cache


class Recorder(EpisodeProgress):
    """A caller that writes down what it was told, in the order it was told.

    Stands in for the single-run path's events and the batch's queue rows
    alike: what either of them makes of a report is theirs, and what the
    pipeline reports is this.
    """

    def __init__(self) -> None:
        self.reported: list[str] = []
        self.episode: Episode | None = None

    def stage_reached(self, stage: Stage) -> None:
        self.reported.append(f"stage:{stage}")

    def episode_resolved(self, episode: Episode) -> None:
        self.episode = episode
        self.reported.append("episode")

    def reference_stale(self, outcome: ReferenceOutcome) -> None:
        self.reported.append("stale")

    def summary_written(self, text: str) -> None:
        if self.reported[-1:] != ["summary"]:
            self.reported.append("summary")


def summarize(
    container: Container,
    store: RunStore,
    players: PlayerCache,
    *,
    url: str = EPISODE_URL,
    progress: EpisodeProgress | None = None,
    context_note: str | None = None,
):
    """Summarize the fixture episode the way any caller would."""
    return summarize_episode(
        url=url,
        container=container,
        store=store,
        players=players,
        model=DEFAULT_MODEL,
        context_note=context_note,
        progress=progress or SILENT,
    )


def test_an_episode_is_summarized_and_saved_with_nobody_listening(
    container: Container,
    store: RunStore,
    players: PlayerCache,
    claude: FakeClaudeClient,
) -> None:
    """No publisher, no events, no application — and a saved run all the same."""
    finished = summarize(container, store, players)

    saved = store.recent(1)[0]
    assert finished.run.id == saved.id
    assert finished.summary == claude.summary
    assert saved.summary == claude.summary
    assert saved.model == DEFAULT_MODEL
    assert saved.season == finished.run.season
    assert finished.elapsed_seconds > 0


def test_the_pipeline_reports_each_part_of_the_work_as_it_lands(
    container: Container, store: RunStore, players: PlayerCache
) -> None:
    """What a run turns into its event sequence, before any of that."""
    recorder = Recorder()

    summarize(container, store, players, progress=recorder)

    assert recorder.reported == [
        "stage:captions",
        "stage:metadata",
        "episode",
        "stage:players",
        "stage:summarizing",
        "summary",
    ]


def test_the_resolved_episode_is_reported_whole(
    container: Container, store: RunStore, players: PlayerCache
) -> None:
    """The caller renders the episode; the pipeline hands over the episode."""
    recorder = Recorder()

    summarize(container, store, players, progress=recorder, context_note="Focus on WRs")

    assert recorder.episode is not None
    assert recorder.episode.title == "Week 1 Waiver Wire Targets"
    assert recorder.episode.context_note == "Focus on WRs"


def test_an_unusable_url_raises_its_kind_before_any_edge_is_touched(
    container: Container,
    store: RunStore,
    players: PlayerCache,
    youtube: FakeYouTubeSource,
) -> None:
    """A failure is the same kind here as it is on a run's event stream."""
    with pytest.raises(RunFailed) as failure:
        summarize(container, store, players, url="https://vimeo.com/123456789")

    assert failure.value.kind == "invalid_url"
    assert youtube.calls == []
    assert store.recent(1) == []


def test_a_claude_failure_raises_rather_than_saving_half_a_run(
    container: Container,
    store: RunStore,
    players: PlayerCache,
    claude: FakeClaudeClient,
) -> None:
    claude.error = RuntimeError("rate limited")

    with pytest.raises(RunFailed) as failure:
        summarize(container, store, players)

    assert failure.value.kind == "claude"
    assert store.recent(1) == []


def test_an_error_nothing_recognises_arrives_as_the_unknown_kind(
    container: Container, store: RunStore, tmp_path: Path
) -> None:
    """The pipeline raises `RunFailed` and nothing else, so no caller has to
    invent an answer for the exception it did not expect.

    A cache that cannot be opened is the case that proves it: the store is not
    an edge, so nothing on the way up classifies what it raises.
    """
    unusable = PlayerCache(tmp_path / "no" / "such" / "directory" / "cache.db")

    with pytest.raises(RunFailed) as failure:
        summarize(container, store, unusable)

    assert failure.value.kind == "unknown"
    assert failure.value.detail is not None
    assert store.recent(1) == []


def test_a_stale_reference_is_reported_and_the_episode_goes_ahead(
    container: Container,
    store: RunStore,
    players: PlayerCache,
    nflverse: FakeNflverseSource,
    claude: FakeClaudeClient,
) -> None:
    """An upstream outage costs accuracy, not the summary — and says so."""
    cached = sync_reference(container, players)
    players.save(replace(cached, synced_at=cached.synced_at - CACHE_TTL - timedelta(days=2)))
    nflverse.error = RuntimeError("nflverse is unreachable")
    recorder = Recorder()

    finished = summarize(container, store, players, progress=recorder)

    assert "stale" in recorder.reported
    assert recorder.reported.index("stale") == recorder.reported.index("stage:players") + 1
    assert finished.summary == claude.summary
