"""Turning a YouTube URL into an episode: its transcript, title, and date.

Everything here is pure with respect to the network. The one thing that talks
to YouTube is the `EpisodeSource` handed in, which the container resolves — a
fake in tests, `youtube.YouTubeSource` in production.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse


class CaptionTrack(Protocol):
    """One caption track YouTube holds for an episode."""

    language_code: str
    is_generated: bool

    def fetch(self) -> Sequence[Mapping[str, Any]]:
        """The track's caption segments, in order, each carrying `text`."""


class EpisodeSource(Protocol):
    """Everything the app asks YouTube for. The `captions` container edge."""

    def list_tracks(self, video_id: str) -> Sequence[CaptionTrack]: ...

    def fetch_metadata(self, url: str) -> Mapping[str, Any]: ...

    def fetch_oembed(self, url: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class EpisodeMetadata:
    """What the episode is: its title, channel, and when it went up."""

    title: str
    channel: str | None = None
    upload_date: date | None = None


@dataclass(frozen=True)
class Episode:
    """One podcast instalment, resolved: what we show and summarize.

    `context_note` is the one field here that YouTube knows nothing about —
    it is what the reader asked this episode be read with in mind. It rides
    with the episode because everything that wants it wants it per episode:
    the prompt, the saved run, and the file that run is downloaded as.
    """

    video_id: str
    url: str
    transcript: str
    title: str
    channel: str | None = None
    upload_date: date | None = None
    context_note: str | None = None

    @property
    def upload_date_label(self) -> str:
        """How this episode's upload date is put to the reader."""
        return upload_date_label(self.upload_date)


def date_label(value: date) -> str:
    """The one way a date is written anywhere in the interface."""
    return f"{value.day} {value:%B %Y}"


def upload_date_label(upload_date: date | None) -> str:
    """Put an upload date to the reader, or say that we don't know it.

    The date is how a reader tells whether an episode's news predates the most
    recent slate of games, so an unknown one says so out loud rather than
    rendering as a blank space. A live episode and a saved run phrase it
    identically because both go through here.
    """
    if upload_date is None:
        return "Upload date unknown"
    return date_label(upload_date)


class InvalidUrlError(ValueError):
    """The submitted text is not a YouTube episode URL."""


class NoCaptionsError(RuntimeError):
    """The episode has no caption track we can read."""


#: Shown when neither metadata source could name the episode.
FALLBACK_TITLE = "Untitled episode"

#: The hosts a YouTube episode can be linked from. Matched exactly — a host
#: that merely *contains* one of these belongs to somebody else.
YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
SHORT_HOST = "youtu.be"

#: A YouTube video identifier: exactly eleven URL-safe characters.
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: The one URL shape every YouTube service accepts. A share link, a scheme-less
#: paste, or a `/shorts/` link is rebuilt into this before it goes anywhere.
_WATCH_URL = "https://www.youtube.com/watch?v={}"

#: The paths that carry the identifier in the path rather than the query.
_ID_BEARING_PREFIXES = ("/live/", "/shorts/", "/embed/", "/v/")


def video_id_from_url(url: str) -> str:
    """Extract the episode's video identifier, or reject the URL.

    Every run starts here, before anything reaches out to YouTube, so a typo
    or a pasted Vimeo link costs a round trip to nobody.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise InvalidUrlError("Paste a YouTube URL to summarize an episode.")
    if "//" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise InvalidUrlError(f"{parsed.scheme} is not a YouTube link.")

    host = (parsed.hostname or "").lower()
    if host == SHORT_HOST:
        return _checked_id(parsed.path.lstrip("/").split("/")[0])
    if host in YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            return _checked_id(parse_qs(parsed.query).get("v", [""])[0])
        for prefix in _ID_BEARING_PREFIXES:
            if parsed.path.startswith(prefix):
                return _checked_id(parsed.path[len(prefix) :].split("/")[0])
    raise InvalidUrlError("That is not a YouTube episode URL.")


def _checked_id(candidate: str) -> str:
    if not _VIDEO_ID.match(candidate):
        raise InvalidUrlError("That YouTube link does not name an episode.")
    return candidate


def watch_url(video_id: str) -> str:
    """The canonical watch URL for an episode."""
    return _WATCH_URL.format(video_id)


def select_track(tracks: Sequence[CaptionTrack]) -> CaptionTrack:
    """Pick the track that makes the best transcript.

    An uploaded track beats an auto-generated one — it is punctuated and marks
    speaker changes — and English beats anything else, since the summary is
    written in English. Language wins over provenance: a manually uploaded
    Spanish track is worse input than English auto-captions.
    """
    if not tracks:
        raise NoCaptionsError("This episode has no caption track.")

    def rank(track: CaptionTrack) -> tuple[int, int]:
        english = 0 if track.language_code.split("-")[0].lower() == "en" else 1
        return (english, 1 if track.is_generated else 0)

    return min(tracks, key=rank)


def transcript_from(segments: Sequence[Mapping[str, Any]]) -> str:
    """Join caption segments into one running transcript.

    Timestamps are not retained: nothing downstream refers to them, and Claude
    reads the text better without them interleaved.
    """
    texts = (str(segment.get("text", "")).strip() for segment in segments)
    return " ".join(text for text in texts if text)


def _parse_upload_date(value: Any) -> date | None:
    """yt-dlp reports the upload date as a `YYYYMMDD` string, or not at all."""
    digits = str(value)
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except (TypeError, ValueError):
        return None


def metadata_from(info: Mapping[str, Any]) -> EpisodeMetadata:
    """Read a yt-dlp info dict as episode metadata."""
    return EpisodeMetadata(
        title=str(info.get("title") or FALLBACK_TITLE),
        channel=info.get("channel") or info.get("uploader"),
        upload_date=_parse_upload_date(info.get("upload_date")),
    )


def metadata_from_oembed(payload: Mapping[str, Any]) -> EpisodeMetadata:
    """Read a YouTube oEmbed response as episode metadata.

    oEmbed carries no upload date, so one is never claimed from it.
    """
    return EpisodeMetadata(
        title=str(payload.get("title") or FALLBACK_TITLE),
        channel=payload.get("author_name"),
    )


def describe_episode(source: EpisodeSource, url: str) -> EpisodeMetadata:
    """Resolve the episode's title, channel, and upload date.

    yt-dlp is the only component that talks to YouTube's main site and so the
    only one exposed to bot detection. When it fails, oEmbed can still name the
    episode; when that fails too the run continues unnamed, because the
    transcript is the part the reader came for.
    """
    try:
        return metadata_from(source.fetch_metadata(url))
    except Exception:  # noqa: BLE001 — any metadata failure falls back
        pass
    try:
        return metadata_from_oembed(source.fetch_oembed(url))
    except Exception:  # noqa: BLE001 — the run survives without a title
        return EpisodeMetadata(title=FALLBACK_TITLE)
