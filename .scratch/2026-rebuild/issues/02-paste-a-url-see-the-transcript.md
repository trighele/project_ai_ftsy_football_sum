# 02 — Paste a URL, see the transcript

**What to build:** Pasting a YouTube URL and clicking once retrieves the episode's captions and renders the transcript on the page, along with the episode title and upload date. No summarization yet — this ticket proves the app can turn a URL into readable text in a couple of seconds, replacing the audio-download-and-Whisper path with YouTube's own captions.

Captions come from `youtube-transcript-api` using its current instance-based API, not the older static call. Manually uploaded caption tracks are preferred over auto-generated ones, and English is preferred. Caption segments are joined into a single running transcript; timestamps are not retained.

Episode title and upload date come from `yt-dlp` metadata extraction only — no audio download and no post-processors. When that call fails, fall back to YouTube's oEmbed endpoint for the title and channel and mark the upload date unknown, rather than failing the whole run. The upload date matters to the reader: it is how they judge whether the episode's news predates the most recent slate of games, so surface it prominently.

Error handling in this ticket can be minimal — a generic failure message is acceptable. Ticket 09 replaces it with the typed error kinds.

**Blocked by:** 01.

**Status:** ready-for-agent

- [x] Submitting a valid YouTube URL renders the transcript on the page.
- [x] The episode title and upload date render alongside the transcript.
- [x] An uploaded caption track is chosen in preference to an auto-generated one when both exist.
- [x] Caption segments are joined into one continuous transcript with no timestamps.
- [x] Metadata retrieval performs no audio download and runs no post-processors.
- [x] When metadata retrieval fails but captions succeed, the run still completes with a fallback title and the upload date shown as unknown.
- [x] A malformed or non-YouTube URL is rejected before any network call is attempted.
- [x] Tests drive the real route through the test client with a fixture caption payload and a fixture metadata response, and make no network calls.
