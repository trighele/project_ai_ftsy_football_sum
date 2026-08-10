# YouTube captions instead of self-hosted Whisper transcription

We previously downloaded each episode's audio with yt-dlp, split it into four chunks with ffmpeg, and transcribed it against a Hugging Face Inference Endpoint running Whisper — resuming the endpoint before use and pausing it afterwards, because it bills while running. We now fetch YouTube's own captions with `youtube-transcript-api` instead, which removes the audio download, ffmpeg, the staging directory, the endpoint start/stop dance, and four HF environment variables.

## Considered Options

- **Keep Whisper as a fallback for caption-less videos.** Rejected: it keeps every piece of the machinery we set out to delete, to cover a case that essentially does not occur on the established podcast channels this app is pointed at.
- **Local `faster-whisper` in the container.** Rejected: CPU transcription of a two-hour episode is not viable in a 512Mi pod.

## Consequences

- Auto-generated captions have no punctuation and no speaker labels, so Claude receives lower-quality input than Whisper produced. In practice the summaries hold up, but this is the real cost of the trade.
- An episode with no captions at all cannot be summarized — there is no fallback. The UI says so explicitly rather than failing opaquely.
- `youtube-transcript-api` works from residential IPs but YouTube blocks most datacenter IP ranges. This is fine for the current self-hosted, single-node deployment and would need rotating residential proxies if the app ever moved to a cloud provider.
