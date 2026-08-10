"""The real YouTube edge: captions from youtube-transcript-api, metadata from yt-dlp.

This is the implementation the container resolves for the `captions` edge. It
is deliberately thin — every decision about *which* track to read and how to
read metadata lives in `transcripts.py`, which needs no network to be tested.
Only the calls themselves live here.

`youtube-transcript-api` v1.x is instance-based: construct the class, then
`list` / `fetch`. The older static `get_transcript` call is gone.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

#: yt-dlp is asked for the episode's description only. It downloads nothing,
#: converts nothing, and never touches ffmpeg — the whole point of ADR-0001.
METADATA_OPTIONS: Mapping[str, Any] = {
    "skip_download": True,
    "postprocessors": [],
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}

OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
OEMBED_TIMEOUT_SECONDS = 10


class _Track:
    """Adapts one `youtube-transcript-api` transcript to our caption track."""

    def __init__(self, transcript: Any) -> None:
        self._transcript = transcript
        self.language_code: str = transcript.language_code
        self.is_generated: bool = transcript.is_generated

    def fetch(self) -> list[Mapping[str, Any]]:
        return self._transcript.fetch().to_raw_data()


class YouTubeSource:
    """Everything the app asks YouTube for, in one place.

    Captions and metadata come from two different libraries hitting two
    different YouTube surfaces, but they are one edge from the application's
    point of view: one thing to fake in tests, one thing to fail when YouTube
    is unhappy with us.

    The collaborators are injectable so the requirement that metadata
    retrieval downloads no audio can be asserted without the network.
    """

    def __init__(
        self,
        *,
        transcript_api: Any | None = None,
        ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
        http_get: Callable[..., Any] | None = None,
    ) -> None:
        self._transcript_api = transcript_api if transcript_api is not None else _api()
        self._ydl_factory = ydl_factory if ydl_factory is not None else _ydl_factory()
        self._http_get = http_get if http_get is not None else _http_get()

    def list_tracks(self, video_id: str) -> list[_Track]:
        """The caption tracks YouTube holds for an episode."""
        return [_Track(transcript) for transcript in self._transcript_api.list(video_id)]

    def fetch_metadata(self, url: str) -> Mapping[str, Any]:
        """The yt-dlp info dict for an episode. Metadata extraction only."""
        with self._ydl_factory(dict(METADATA_OPTIONS)) as ydl:
            return ydl.extract_info(url, download=False)

    def fetch_oembed(self, url: str) -> Mapping[str, Any]:
        """YouTube's oEmbed record: the title and channel, and nothing else.

        The fallback for when yt-dlp is blocked. oEmbed is a public endpoint
        that bot detection leaves alone, but it carries no upload date.
        """
        response = self._http_get(
            OEMBED_ENDPOINT,
            params={"url": url, "format": "json"},
            timeout=OEMBED_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()


def _api() -> Any:
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi()


def _ydl_factory() -> Any:
    from yt_dlp import YoutubeDL

    return YoutubeDL


def _http_get() -> Any:
    import requests

    return requests.get
