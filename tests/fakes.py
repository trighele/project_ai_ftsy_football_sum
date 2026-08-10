"""Fakes for the application's network edges, backed by recorded fixtures.

These stand in for the real edges at the dependency container. They record what
they were asked for so a test can prove a call did *not* happen — rejecting a
bad URL before any network call is a requirement, not an implementation detail.
"""

from __future__ import annotations

import json
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


class FakeClaudeClient:
    """Stand-in for the Claude client edge. Wired up by ticket 04."""
