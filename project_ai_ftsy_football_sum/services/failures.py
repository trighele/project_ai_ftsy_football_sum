"""Why a run stopped, in the words the reader is owed.

A failure is a *kind* before it is an exception message. There are six of them
and they are written down as a type, like the container's edges, so a misspelt
one is a mistake that can be seen rather than one that waits for the failure
path to be taken. Each kind says something the reader can act on: try again
later, try a different video, or nothing is wrong with the episode at all.

Two things stay out of the messages. They never blame the reader for something
YouTube did, and they never contain the underlying exception — that travels
alongside as `detail` and is rendered behind a disclosure toggle, available
when wanted and out of the way when not.

Classifying a caption failure is done on the exception's class name rather than
its message, because `youtube-transcript-api` gives every one of its errors the
same opening paragraph: "no captions", "this video is private" and "you have
been rate limited" are one string and three very different things to be told.
The names are the library's public API — they are what it documents and what
callers catch. Reading them here rather than importing them keeps the run
engine free of a caption library, which matters because the same function
classifies whatever a future edge raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

#: Why a run stopped. Six kinds the reader can act on, and `unknown` for a
#: failure that fits none of them — which is not a seventh kind of problem so
#: much as an admission that the raw error below is all we have.
FailureKind = Literal[
    "invalid_url",
    "no_captions",
    "video_unavailable",
    "youtube_blocked",
    "nflverse",
    "claude",
    "unknown",
]

#: What a failure of each kind is put to the reader as. An invalid URL is the
#: one that usually says something more specific than its entry here — the URL
#: parser knows exactly what was wrong with what was pasted.
FAILURE_MESSAGES: Mapping[FailureKind, str] = {
    "invalid_url": "That is not a YouTube episode URL. Check the link and paste it again.",
    "no_captions": (
        "This episode has no captions to read. YouTube generates them for a new "
        "upload within an hour or so of it going up, so if this one is recent it "
        "is worth trying again later. There is nothing else to transcribe from — "
        "this app reads captions and never downloads audio."
    ),
    "video_unavailable": (
        "YouTube will not hand this episode over. It is private, members-only, "
        "age-restricted, or has been taken down. The problem is with the video "
        "rather than with this app, so a different link will work."
    ),
    "youtube_blocked": (
        "YouTube refused the request — bot detection or a blocked address, not "
        "anything about this episode. It usually clears on its own; try again in "
        "a few minutes."
    ),
    "nflverse": (
        "The player reference could not be fetched from nflverse, and nothing "
        "has been cached yet. Without it a summary would attribute news to the "
        "wrong players, so the run stopped. Try again in a few minutes."
    ),
    "claude": (
        "Claude could not finish this summary — an API error or a rate limit. "
        "The transcript came back fine, so this is worth trying again."
    ),
    "unknown": (
        "Something went wrong during this run, and it is not one of the failures "
        "this app knows how to explain. The raw error is below. Trying again is "
        "the sensible next thing."
    ),
}

#: How long an underlying error may be before it is cut short. Long enough for
#: a stack of "most likely caused by" paragraphs, short enough that a toggle
#: opens onto something a person will read.
DETAIL_LIMIT = 2000

#: How far down the chain of causes to read. Deep enough to get past this app's
#: own wrapper to the library error underneath it, and no further: the third
#: link is somebody's socket, which explains nothing to anybody.
CAUSE_DEPTH = 3

#: What each `youtube-transcript-api` exception means for the reader, by class
#: name. The names are matched along the exception's ancestry, so a subclass
#: the library adds later lands on its parent's kind rather than on `unknown`.
_YOUTUBE_ERRORS: Mapping[str, FailureKind] = {
    # Nothing to read.
    "NoCaptionsError": "no_captions",
    "TranscriptsDisabled": "no_captions",
    "NoTranscriptFound": "no_captions",
    "NoTranscriptAvailable": "no_captions",
    "NotTranslatable": "no_captions",
    "TranslationLanguageNotAvailable": "no_captions",
    # Nothing wrong with us; the video is not on offer.
    "VideoUnavailable": "video_unavailable",
    "VideoUnplayable": "video_unavailable",
    "AgeRestricted": "video_unavailable",
    "InvalidVideoId": "video_unavailable",
    # YouTube declining to talk to this address.
    "IpBlocked": "youtube_blocked",
    "RequestBlocked": "youtube_blocked",
    "PoTokenRequired": "youtube_blocked",
    "YouTubeRequestFailed": "youtube_blocked",
}

#: The fallback for an error that arrived as something plainer than one of the
#: library's own classes — a `RuntimeError` from a wrapper, or yt-dlp, which
#: raises one `DownloadError` for everything and puts the reason in the text.
#: Ordered: the first phrase found decides, so the specific ones come first.
_YOUTUBE_PHRASES: tuple[tuple[str, FailureKind], ...] = (
    ("subtitles are disabled", "no_captions"),
    ("no transcript", "no_captions"),
    ("no captions", "no_captions"),
    ("members-only", "video_unavailable"),
    ("age-restricted", "video_unavailable"),
    ("age restricted", "video_unavailable"),
    ("sign in to confirm you're not a bot", "youtube_blocked"),
    ("too many requests", "youtube_blocked"),
    ("private video", "video_unavailable"),
    ("is private", "video_unavailable"),
    ("has been removed", "video_unavailable"),
    ("unavailable", "video_unavailable"),
    ("blocked", "youtube_blocked"),
    ("forbidden", "youtube_blocked"),
)


class RunFailed(Exception):
    """A run cannot go on: the kind of failure, and the error underneath it.

    Both halves travel together because the reader is shown both — the message
    as the panel, the detail behind its toggle.
    """

    def __init__(
        self,
        kind: FailureKind,
        message: str | None = None,
        *,
        detail: str | None = None,
    ) -> None:
        self.kind = kind
        self.message = message or FAILURE_MESSAGES[kind]
        self.detail = detail
        super().__init__(self.message)

    @classmethod
    def of(
        cls, kind: FailureKind, error: BaseException, message: str | None = None
    ) -> RunFailed:
        """A failure of that kind, carrying the error that caused it."""
        return cls(kind, message, detail=error_detail(error))


def classify_youtube_error(error: BaseException) -> FailureKind:
    """Which kind of failure a YouTube error actually is.

    An error nothing recognises is `unknown` rather than a guess: a reader told
    to wait for captions that are already there is worse off than one shown the
    error and told to try again.
    """
    for ancestor in type(error).__mro__:
        kind = _YOUTUBE_ERRORS.get(ancestor.__name__)
        if kind is not None:
            return kind

    text = str(error).lower()
    for phrase, kind in _YOUTUBE_PHRASES:
        if phrase in text:
            return kind
    return "unknown"


def error_detail(error: BaseException) -> str:
    """The underlying error as the toggle shows it: what it was, and what it said.

    The class name is kept because it is often the only part that identifies
    the failure — every `CouldNotRetrieveTranscript` says the same words. What
    an error was raised *from* is kept for the opposite reason: the exceptions
    this app raises around an edge all say the same generic sentence, and the
    one line worth reading is the library's underneath it.
    """
    lines = []
    cause: BaseException | None = error
    while cause is not None and len(lines) < CAUSE_DEPTH:
        prefix = "" if not lines else "caused by: "
        lines.append(prefix + _described(cause))
        cause = cause.__cause__ if cause.__cause__ is not cause else None
    return _capped("\n".join(lines))


def _described(error: BaseException) -> str:
    text = str(error).strip()
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _capped(detail: str) -> str:
    if len(detail) <= DETAIL_LIMIT:
        return detail
    return f"{detail[:DETAIL_LIMIT].rstrip()}…"
