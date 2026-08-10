"""Fakes for the application's network edges, backed by recorded fixtures.

These stand in for the real edges at the dependency container. They record what
they were asked for so a test can prove a call did *not* happen — rejecting a
bad URL before any network call is a requirement, not an implementation detail.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeCaptionTrack:
    """One caption track on offer for an episode."""

    def __init__(
        self, *, language_code: str, is_generated: bool, snippets: list[dict[str, Any]]
    ) -> None:
        self.language_code = language_code
        self.is_generated = is_generated
        self.snippets = snippets
        self.fetches = 0

    def fetch(self) -> list[dict[str, Any]]:
        self.fetches += 1
        return list(self.snippets)


def manual_track(language_code: str = "en") -> FakeCaptionTrack:
    return FakeCaptionTrack(
        language_code=language_code,
        is_generated=False,
        snippets=fixture("captions_manual"),
    )


def generated_track(language_code: str = "en") -> FakeCaptionTrack:
    return FakeCaptionTrack(
        language_code=language_code,
        is_generated=True,
        snippets=fixture("captions_generated"),
    )


class FakeYouTubeSource:
    """Serves fixture captions and metadata in place of YouTube.

    Any of the three calls can be made to fail, which is how the fallback and
    failure paths are exercised without the network.
    """

    def __init__(
        self,
        *,
        tracks: list[FakeCaptionTrack] | None = None,
        metadata: dict[str, Any] | None = None,
        oembed: dict[str, Any] | None = None,
        captions_error: Exception | None = None,
        metadata_error: Exception | None = None,
        oembed_error: Exception | None = None,
    ) -> None:
        self.tracks = [manual_track(), generated_track()] if tracks is None else tracks
        self.metadata = fixture("metadata") if metadata is None else metadata
        self.oembed = fixture("oembed") if oembed is None else oembed
        self.captions_error = captions_error
        self.metadata_error = metadata_error
        self.oembed_error = oembed_error
        self.calls: list[tuple[str, str]] = []

    def list_tracks(self, video_id: str) -> list[FakeCaptionTrack]:
        self.calls.append(("list_tracks", video_id))
        if self.captions_error is not None:
            raise self.captions_error
        return list(self.tracks)

    def fetch_metadata(self, url: str) -> dict[str, Any]:
        self.calls.append(("fetch_metadata", url))
        if self.metadata_error is not None:
            raise self.metadata_error
        return dict(self.metadata)

    def fetch_oembed(self, url: str) -> dict[str, Any]:
        self.calls.append(("fetch_oembed", url))
        if self.oembed_error is not None:
            raise self.oembed_error
        return dict(self.oembed)


class FakeNflverseSource:
    """Stand-in for the nflverse edge. Wired up by ticket 06."""


#: A canned summary, in the pieces Claude would have written it in. It keeps
#: the shape the prompt asks for so a test can tell a real summary from an
#: empty one, and arrives in several chunks so streaming is observable.
SUMMARY_CHUNKS = (
    "# Week 1 Waiver Wire Targets\n\n_7 August 2026_\n\n## News Section\n\n",
    "- **Player/Team**: Bijan Robinson (ATL, RB)\n"
    "  - **News**: The Falcons are talking about a bigger role.\n"
    "  - **Sentiment**: Positive\n\n",
    "## Matchup Analysis\n\n- Atlanta's backfield is worth watching in Week 1.\n\n",
    "## Player Debates\n\n- Robinson over a mid-tier WR1 in PPR.\n\n",
    "## Waiver Wire Suggestions\n\n- Add the Falcons' pass-catching back.\n",
)


class FakeClaudeClient:
    """Records the request it was handed and replays a canned streamed summary.

    Recording the whole request, rather than checking a return value, is the
    point of this fake: the player reference ticket asserts on every byte that
    reached Claude, because a reference that is plausible and wrong produces a
    summary that reads perfectly and is wrong.
    """

    def __init__(
        self,
        *,
        chunks: tuple[str, ...] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.chunks = SUMMARY_CHUNKS if chunks is None else chunks
        self.error = error
        self.requests: list[Any] = []

    @property
    def request(self) -> Any:
        """The most recent request. Raises if nothing was ever asked for."""
        return self.requests[-1]

    @property
    def summary(self) -> str:
        """The whole of what this fake streams back."""
        return "".join(self.chunks)

    def stream(self, request: Any) -> Iterator[str]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        yield from self.chunks
