# Fantasy Football Podcast Summarizer

Paste the YouTube URL of a fantasy football podcast episode and get back a structured Markdown summary — news items with fantasy sentiment, matchup analysis, player debates, waiver suggestions. The transcript comes from YouTube's own captions, and Claude writes the summary against a current NFL player reference so that a name in the audio is attributed to the right team, position, and standing.

## Features

- Reads an episode's captions from YouTube — no audio download, no transcription step
- Summarizes with Claude, streamed into the page as it is written
- Hands Claude a player reference synced from [nflverse](https://github.com/nflverse): depth rank, ECR tier and rank, bye week, injury status
- Saves every run: history, search, re-open, download as Markdown, delete
- A Players page you can sort, filter, and search entirely in the browser
- Server-rendered HTML with htmx; no build step to run the app

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker (optional)
- An Anthropic API key

## Environment variables

The application does not read a `.env` file itself — these have to be set in the real environment (your shell, Compose, or the Kubernetes ConfigMap and Secret). Locally, hand the file to uv instead: `uv run --env-file .env ffsum --reload`.

```env
ANTHROPIC_API_KEY=your_anthropic_key   # required; without it the readiness pill reads "Not ready"
CLAUDE_MODEL=claude-sonnet-5           # optional; this is the default
FFSUM_DATA_DIR=./data                  # optional; directory holding the SQLite database
```

`FFSUM_DATA_DIR` is a *directory*, not a file. It holds the saved runs and the cached player reference, and is the path a deployment mounts a volume at.

## Installation

### Local development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/project_ai_ftsy_football_sum.git
cd project_ai_ftsy_football_sum
```

2. Install dependencies:
```bash
uv sync
```

3. Run the application:
```bash
uv run --env-file .env ffsum --reload
```

It listens on `http://127.0.0.1:8000` by default; `--host`, `--port`, and the `HOST`/`PORT` environment variables override that.

4. Run the tests:
```bash
uv run pytest
```

### Using Docker

```bash
docker-compose up --build
```

The application will be available at `http://localhost:9193`, and its data lives in the `ffsum-data` named volume.

## Usage

1. Open the web interface
2. Paste a YouTube URL of a fantasy football podcast and press **Summarize**
3. The transcript appears first; the summary streams in beneath it
4. Find it again later under **History**, where it can be re-opened, downloaded as Markdown, or deleted

## Output format

The summary is generated in Markdown with the following sections:
- Date and Title
- News Section (with Player/Team, News, and Sentiment)
- Matchup Analysis
- Player Debates
- Waiver Wire Suggestions
- Additional relevant sections based on content

## Project structure

```
project_ai_ftsy_football_sum/
├── app.py            # FastAPI routes
├── cli.py            # the `ffsum` console entry point
├── config.py         # what the environment gets to decide
├── container.py      # the three network edges: captions, nflverse, Claude
├── services/         # transcripts, runs, player reference, summarization, storage
├── templates/        # Jinja pages and htmx fragments
├── static/           # generated CSS, htmx, vendored font, page scripts
└── assets/           # Tailwind source for static/css/app.css
docs/adr/             # architecture decision records
deployment/           # Kubernetes manifests
tests/                # HTTP-level tests, network blocked
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
