"""The real YouTube edge, exercised without the network.

This is the one place the suite steps inside the HTTP boundary. It has to: the
requirement that metadata retrieval downloads no audio and runs no
post-processors is invisible from outside — a run that quietly pulled a
two-hour audio file would render exactly the same page. The collaborators
yt-dlp, youtube-transcript-api, and requests are handed in; everything else
about the class is real.
"""

from typing import Any

from project_ai_ftsy_football_sum.services.youtube import OEMBED_ENDPOINT, YouTubeSource


class FakeYoutubeDL:
    """Records the options it was built with and how it was asked to extract."""

    last: "FakeYoutubeDL | None" = None

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options
        self.extract_calls: list[tuple[str, dict[str, Any]]] = []
        FakeYoutubeDL.last = self

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, **kwargs: Any) -> dict[str, Any]:
        self.extract_calls.append((url, kwargs))
        return {"title": "Week 1 Waiver Wire Targets", "upload_date": "20260807"}


class FakeFetchedTranscript:
    def __init__(self, raw: list[dict[str, Any]]) -> None:
        self.raw = raw

    def to_raw_data(self) -> list[dict[str, Any]]:
        return self.raw


class FakeLibraryTranscript:
    def __init__(self, *, language_code: str, is_generated: bool) -> None:
        self.language_code = language_code
        self.is_generated = is_generated

    def fetch(self) -> FakeFetchedTranscript:
        return FakeFetchedTranscript([{"text": "hello", "start": 0.0, "duration": 1.0}])


class FakeTranscriptApi:
    def __init__(self) -> None:
        self.listed: list[str] = []

    def list(self, video_id: str) -> list[FakeLibraryTranscript]:
        self.listed.append(video_id)
        return [
            FakeLibraryTranscript(language_code="en", is_generated=True),
            FakeLibraryTranscript(language_code="en", is_generated=False),
        ]


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.raised = False

    def raise_for_status(self) -> None:
        self.raised = True

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeHttpGet:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def source(**overrides: Any) -> YouTubeSource:
    defaults: dict[str, Any] = {
        "transcript_api": FakeTranscriptApi(),
        "ydl_factory": FakeYoutubeDL,
        "http_get": FakeHttpGet({"title": "t", "author_name": "c"}),
    }
    return YouTubeSource(**{**defaults, **overrides})


def test_metadata_retrieval_downloads_no_audio_and_runs_no_postprocessors() -> None:
    info = source().fetch_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    ydl = FakeYoutubeDL.last
    assert ydl is not None
    assert ydl.options["skip_download"] is True
    assert ydl.options["postprocessors"] == []
    assert ydl.options["noplaylist"] is True
    url, kwargs = ydl.extract_calls[0]
    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert kwargs["download"] is False
    assert info["title"] == "Week 1 Waiver Wire Targets"


def test_caption_tracks_carry_language_generation_and_raw_segments() -> None:
    api = FakeTranscriptApi()

    tracks = source(transcript_api=api).list_tracks("dQw4w9WgXcQ")

    assert api.listed == ["dQw4w9WgXcQ"]
    assert [(t.language_code, t.is_generated) for t in tracks] == [
        ("en", True),
        ("en", False),
    ]
    assert tracks[0].fetch() == [{"text": "hello", "start": 0.0, "duration": 1.0}]


def test_oembed_is_requested_from_youtube_for_the_episode_url() -> None:
    http_get = FakeHttpGet({"title": "Week 1", "author_name": "Fantasy Fallout"})

    payload = source(http_get=http_get).fetch_oembed(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

    url, kwargs = http_get.calls[0]
    assert url == OEMBED_ENDPOINT
    assert kwargs["params"]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert kwargs["params"]["format"] == "json"
    assert kwargs["timeout"] > 0
    assert payload["author_name"] == "Fantasy Fallout"
