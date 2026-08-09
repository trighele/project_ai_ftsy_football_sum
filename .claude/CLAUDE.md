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

There is no test suite, linter config, or CI check wired into this repo (`ruff` appears only as a transitive pin in `requirements.txt`, not a configured tool). The GitHub Actions workflow (`.github/workflows/deployment.yml`) is `workflow_dispatch`-only (manual) and deploys to a self-hosted k8s cluster — it is not a PR/CI gate.

### Working directory note

`main.py` reads/writes audio at relative path `./staging/audio*.mp3`. Locally that directory only exists at the **repo root** (`./staging/`), so the app must be launched with the repo root as cwd, as shown above — not by `cd`-ing into `project_ai_ftsy_football_sum/` first. In the Docker image, `Dockerfile` copies the *contents* of `project_ai_ftsy_football_sum/` to `/app` and creates `/app/staging`, so the same relative path works there for a different reason.

### Environment variables

Required at runtime (loaded via `dotenv` from a `.env` file at repo root):

- `HF_TOKEN`, `HF_NAMESPACE`, `HF_INFERENCE_ENDPOINT_NAME`, `HF_INFERENCE_ENDPOINT_URL` — Hugging Face Inference Endpoint hosting Whisper, used for transcription.
- `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` — Claude API access for summarization.
- `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD` — Postgres connection for the player/tier reference table (not documented in README.md, but required by `summarize_transcription`).

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
