# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page Gradio app that takes a YouTube URL of a fantasy football podcast, downloads and transcribes the audio, and produces a structured Markdown summary using Claude. The summary is enriched with a player/team/tier reference table pulled from Postgres so Claude can correctly attribute news to the right player.

## Commands

Dependency management is Poetry-based; `requirements.txt` is a generated/pinned mirror used only for the Docker image build (`pip install -r requirements.txt`) — edit `pyproject.toml` and re-export rather than hand-editing `requirements.txt`.

```bash
# install deps
poetry install

# run the app locally (must run from repo root — see Working directory note below)
poetry run python project_ai_ftsy_football_sum/main.py

# run via Docker Compose (builds image, exposes UI on host port 9193 -> container 7860)
docker-compose up --build
```

### The 2026 rebuild app (in progress)

A FastAPI app is being built alongside the Gradio one, in the same `project_ai_ftsy_football_sum/` package (`app.py`, `container.py`, `templates/`, `static/`, `assets/`). It does not replace `main.py` until the cutover ticket; both live in the tree meanwhile. The spec and its tickets are in `.scratch/2026-rebuild/`. Dependencies are managed with **uv**, not Poetry.

```bash
# install deps (including the dev group)
uv sync

# run the new app (console script; --host/--port/--reload, or HOST/PORT env vars)
uv run ffsum --reload

# run it against a real Claude — the app never loads .env itself, so uv does it
uv run --env-file .env ffsum --reload

# run the test suite
uv run pytest

# recompile the Tailwind stylesheet after editing templates or assets/tailwind.css
./scripts/build-css.sh
```

`project_ai_ftsy_football_sum/static/css/app.css` is **generated** — edit `assets/tailwind.css` and rebuild. It is committed deliberately so neither the Docker image nor a plain `uv run` needs Node; `scripts/build-css.sh` downloads the Tailwind standalone CLI into the gitignored `.tools/`. `static/js/htmx.min.js` (official dist) and `static/fonts/oswald-latin-var.woff2` (SIL OFL, licence alongside it) are vendored for the same reason. There are no CDN references anywhere in the templates or the stylesheet.

The three network edges (captions, nflverse, Claude) resolve through `container.py` and nothing else, and all three are now wired (`container.UNWIRED_EDGES` is empty). The `captions` edge is everything the app asks YouTube for — caption tracks via `youtube-transcript-api` *and* title/upload-date via `yt-dlp`, plus the oEmbed fallback — all behind one object (`services/youtube.py`), so there is one thing to fake and one thing to fail when YouTube is unhappy. The `nflverse` edge (`services/nflverse.py`) is four `nflreadpy` calls and nothing else; it is the only place a Polars frame exists. The `claude` edge (`services/claude.py`) is one streamed summarization request; it deliberately refuses to build without credentials so the readiness pill reports a missing `ANTHROPIC_API_KEY` rather than a run failing halfway.

A run is started by `POST /runs`, which returns immediately with a panel naming the run's event stream. The work happens in an in-process background task (`services/runs.py`, run on a worker thread because every edge is a blocking library) and progress reaches the browser as Server-Sent Events on `GET /runs/{token}/events`: `stage` transitions, the rendered `transcript` panel, `summary` text a delta at a time, and exactly one terminal `done` or `failed` carrying an error kind. Events are buffered per run, because the browser starts a run and follows it in two separate requests. An in-flight run does not survive a restart; there is no queue and no worker process. `static/js/run.js` is one of the two pieces of client-side code (`players.js` is the other) — it moves server-rendered fragments into place and keeps the Summarize button disabled until the run ends.

What Claude is handed is built in `services/summarize.py` and nowhere else, as a `SummaryRequest` that is the whole of what the edge receives — so `tests/fakes.py`'s recording fake can be asserted on byte for byte, which is what `tests/test_player_reference_prompt.py` does. The system prompt is two blocks: the output contract, then the player reference as a Markdown table with the season named and depth rank, ECR tier, and ECR rank as separate labelled columns, plus the paragraph telling Claude that depth rank and ECR tier do not imply one another. That second block carries `cache_control` and so must be byte-stable between runs — no sync time, no run identifier, nothing per-episode inside it; the transcript, title, and upload date all sit in the user turn. The table is a deliberately narrower slice than the Players page shows (`summarize.PROMPT_POSITIONS` at `DEPTH_RANK_LIMIT` or better, ~700 rows of ~2,800): the page is for exploring, the prompt is for accuracy per token. The season the reference resolved to is saved on the run and shown on its detail view, because in the preseason a summary is written against last autumn's depth charts.

`GET /history` lists every saved run (the home page keeps only the five most recent), narrowed by a title search. The search box and a delete both swap in the same `fragments/history_list.html`, so the list markup exists once: `GET /fragments/history?q=` for live search, `DELETE /runs/{id}?q=` for a delete that comes back to the search it was made from. Delete is a real row deletion with no confirmation step. `GET /runs/{id}/download` hands over the run as Markdown; `services/download.py` builds that document with its own front matter — title, channel, upload date, source, summarized date — so the file stands on its own whatever Claude wrote at the top of the summary.

`GET /players` shows the player reference, assembled in `services/players.py` from the four nflverse tables — depth charts for **depth rank**, players for identity, fantasy rankings for ECR rank and bye week, injuries for status. nflverse publishes no tier column, so **ECR tier** is derived from ECR rank (`players.TIER_SIZE`) — see ADR-0002. Depth rank and ECR tier are two different facts and are never collapsed into a field called `tier`; ADR-0002 exists because the old app did exactly that. Polars frames are converted to records in `_records` and nothing past it sees one. Season resolution starts at the current calendar season (nflverse rolls rosters over mid-March) and walks back until a season has depth charts, because in the preseason the current year has none — the resolved season travels with the reference and the page warns when it trails. The injury feed is the one table allowed to be missing: nflverse refuses a season that has not kicked off, and a blank status column is the correct answer there. The reference is cached in SQLite for 12 hours (`services/player_cache.py`, `players.CACHE_TTL`), synced on demand from **Sync now** (`POST /players/sync`, which re-renders `fragments/player_reference.html`) and automatically at the start of a run when stale. A sync that fails with something cached is not a failure — the run proceeds against the older reference and its age is on show; a sync that fails with nothing cached ends the run with the `nflverse` kind.

The Players page is explorable entirely in the browser: sort on any column, filter by any number of teams or positions, cut off below a depth rank, and search by name, with the filters narrowing each other rather than replacing each other. Every row of the reference is in the page already, so none of it is a round trip — the server writes each row's values onto its `<tr>` as `data-*` attributes and `static/js/players.js` reads them, which is why nothing there parses a cell. See ADR-0003 for why the rows are HTML rather than the JSON the spec called for. The script is delegated from the document rather than bound to the controls, so the section **Sync now** swaps in works without being wired up again.

Saved runs live in one SQLite file (`services/store.py`), at `$FFSUM_DATA_DIR/ffsum.db` — a *directory* rather than a file path, because ticket 10 mounts one volume there and the cached player reference is already on it. `config.py` is the only place that path is decided; it defaults to `./data` (gitignored). The schema is created in the app's lifespan startup, not when the store is constructed, so importing `app.py` touches no disk. The store is not a container edge — it is local disk, and tests exercise the real thing against a `tmp_path`.

Tests drive the app through `TestClient` with fakes registered on the container; an autouse fixture in `tests/conftest.py` blocks sockets, so a test that reaches the network fails rather than hangs. Another autouse fixture points `FFSUM_DATA_DIR` at a temporary directory, so no test can write into the working tree. `tests/fakes.py` holds the edge fakes and `tests/fixtures/*.json` the recorded payloads they serve. `tests/test_youtube_source.py` is the single exception to the HTTP-only seam: yt-dlp downloading audio is invisible from outside the app, so its collaborators are injected and asserted on directly.

There is no linter config or CI check wired into this repo (`ruff` appears only as a transitive pin in `requirements.txt`, not a configured tool), and the Gradio app has no tests. The GitHub Actions workflow (`.github/workflows/deployment.yml`) is `workflow_dispatch`-only (manual) and deploys to a self-hosted k8s cluster — it is not a PR/CI gate.

### Working directory note

`main.py` reads/writes audio at relative path `./staging/audio*.mp3`. Locally that directory only exists at the **repo root** (`./staging/`), so the app must be launched with the repo root as cwd, as shown above — not by `cd`-ing into `project_ai_ftsy_football_sum/` first. In the Docker image, `Dockerfile` copies the *contents* of `project_ai_ftsy_football_sum/` to `/app` and creates `/app/staging`, so the same relative path works there for a different reason.

### Environment variables

Required at runtime (loaded via `dotenv` from a `.env` file at repo root):

- `HF_TOKEN`, `HF_NAMESPACE`, `HF_INFERENCE_ENDPOINT_NAME`, `HF_INFERENCE_ENDPOINT_URL` — Hugging Face Inference Endpoint hosting Whisper, used for transcription.
- `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` — Claude API access for summarization.
- `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD` — Postgres connection for the player/tier reference table (not documented in README.md, but required by `summarize_transcription`).

Read by the 2026 rebuild app, and **not** loaded from `.env` — that app never calls `load_dotenv`, so these have to be set in the real environment (Compose, the k8s ConfigMap, or the shell):

- `FFSUM_DATA_DIR` — optional. Directory holding the SQLite database of saved runs. Defaults to `./data`. Set it to the mounted volume path in a deployment.
- `ANTHROPIC_API_KEY` — required for a run to get past the transcript. Without it the readiness pill reads "Not ready".
- `CLAUDE_MODEL` — optional. Defaults to `claude-sonnet-5`. Same variable the Gradio app uses, so an existing deployment's value still applies.

Both are already in the repo-root `.env` for the Gradio app. To exercise the new app against a real Claude locally, hand that file to uv rather than to the app: `uv run --env-file .env ffsum --reload`. With `ANTHROPIC_API_KEY` set, all three edges build and the readiness pill reads "Ready"; without it, the pill names `claude`.

## Architecture

Everything lives in two files under `project_ai_ftsy_football_sum/`:

- `main.py` — Gradio UI plus the entire pipeline, wired to two buttons:
  - **Transcribe Audio** → `fn_transcribe` → `download_audio` (yt-dlp, falls back from `bestaudio/best` to `best` format) → `chunk_audio` (ffprobe/ffmpeg split into 4 equal parts, stream-copied with no re-encoding) → `transcribe_audio`.
  - **Summarize Transcript** → `fn_summarize` → `summarize_transcription`.
  - `transcribe_audio` explicitly **resumes** the HF Inference Endpoint before use, polls its status (up to 5 minutes) until `running`, sends each of the 4 audio chunks as base64 in separate requests, then **pauses** the endpoint again afterward and deletes everything in `staging/`. This start/stop dance exists because the HF endpoint is billed while running — don't remove the pause step or change the polling loop without preserving that behavior.
  - `summarize_transcription` fetches player reference data via `get_player_data_from_db(season_year=2025)` (season year is currently hardcoded), formats it as a Markdown table, and embeds it directly into the Claude system prompt so player mentions get matched to the right team/position/tier.
- `functions/pg_functions.py` — `get_player_data_from_db`: one query joining `players` → `teams` → `player_seasons` → `seasons`, optionally filtered by `season_year`. Returns list of dicts (`player_name`, `position`, `team`, `tier`).

### Data flow / external dependencies

The Postgres `players`/`teams`/`player_seasons`/`seasons` tables are not populated by this app — they're seeded out-of-band. `notebooks/nfl_extract.ipynb` scrapes depth charts from ourlads.com into a CSV (`notebooks/nfl_players_with_tiers_2025.csv`); that CSV is the source for whatever loads the DB tables the app queries. `notebooks/playground/` holds exploratory notebooks (transcription experiments, Postgres connectivity tests) — not part of the app runtime.

### Deployment

`deployment/*.yaml` are plain Kubernetes manifests (namespace, deployment, service) — not Helm. The Deployment pulls all env vars from a `project-ai-ftsy-football-sum-secrets` Secret and a `project-ai-ftsy-football-sum-config` ConfigMap (see `.github/workflows/deployment.yml` for exactly which vars go in which). The workflow builds the image, loads it into a local `kind` cluster, applies manifests, and restarts a systemd port-forward service — this is a self-hosted, single-node setup, not a generic cloud deploy pipeline.
