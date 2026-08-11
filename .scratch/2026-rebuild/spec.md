# 2026 Rebuild: custom front end, nflverse player reference, caption-based transcripts

Status: ready-for-agent

## Problem Statement

The app works, but three things about it have gone stale.

Its interface is a Gradio `Blocks` page. It looks like a demo harness rather than a product, it can't show anything Gradio doesn't have a widget for, and it offers no way to look at the player data the summaries depend on.

Its player reference comes from a Postgres database this app does not own. A separate application scrapes ourlads.com and loads those tables out-of-band; if that application hasn't run, this one silently summarizes against whatever is left in the database. Worse, the depth-chart string number it stores is called `tier` and is described to Claude as a fantasy tier — so Claude is told a starting kicker is "Tier 1" in the same breath as a genuine WR1.

Its transcripts are produced the expensive way. Every run downloads the episode's audio with yt-dlp, splits it into four chunks with ffmpeg, resumes a Hugging Face Whisper endpoint, transcribes four chunks, then pauses the endpoint again — because it bills while running. That is several minutes and a metered GPU per run, to obtain text YouTube is already holding.

There is also nowhere to see a past run. Refresh the page and the summary is gone.

## Solution

A custom FastAPI web app with two pages and a saved history.

**Home** takes a YouTube URL and one click. The transcript panel fills within a couple of seconds from YouTube's own captions, and the summary streams in below it as Claude writes it, with live status as each stage completes. The five most recent runs sit underneath, one click to reopen.

**Players** shows the full current NFL player reference — every player, sortable and filterable by team, position, depth rank, and name, with ECR tier, ECR rank, bye week, and injury status. A header strip states which season is in use and when the data was last synced, with a **Sync now** button and a warning when the season shown isn't the current one.

**History** lists every past run and reopens any of them, transcript and summary intact, with a Markdown download.

Underneath: captions replace Whisper, nflverse replaces Postgres, and depth rank and ECR tier are carried as two separate, separately-named things.

## User Stories

### Running a summary

1. As a fantasy manager, I want to paste a YouTube URL and click once, so that I don't have to run two separate steps to get a summary.
2. As a fantasy manager, I want the transcript to appear within a few seconds, so that I know the app found the episode before I wait on Claude.
3. As a fantasy manager, I want to see the episode's title and upload date once it resolves, so that I can confirm I pasted the right link.
4. As a fantasy manager, I want the upload date shown prominently, so that I can tell whether the news predates the most recent slate of games.
5. As a fantasy manager, I want live status as the run progresses through fetching captions, loading the player reference, and summarizing, so that a long wait doesn't look like a hang.
6. As a fantasy manager, I want the summary to stream in as Claude writes it, so that I can start reading before it finishes.
7. As a fantasy manager, I want the transcript to stay visible while the summary streams, so that I can check a quote against the source.
8. As a fantasy manager, I want to see roughly how long the run took, so that I can tell a slow episode from a stuck one.
9. As a fantasy manager, I want the Summarize button disabled while a run is in flight, so that I don't accidentally fire two runs at once.
10. As a fantasy manager, I want a bad or non-YouTube URL rejected before anything else happens, so that I get a fast, clear error rather than a stack trace.

### Reading and keeping summaries

11. As a fantasy manager, I want each run saved automatically, so that a page refresh doesn't lose my summary.
12. As a fantasy manager, I want the five most recent runs on the home page, so that reopening last night's episode is one click.
13. As a fantasy manager, I want a History page listing every past run with title, channel, upload date, and when I summarized it, so that I can find an episode from weeks ago.
14. As a fantasy manager, I want to search or filter my run history by title, so that I can find a specific episode without scrolling.
15. As a fantasy manager, I want to reopen a past run and see both its transcript and its summary, so that the saved record is as useful as the original.
16. As a fantasy manager, I want to download a run's summary as Markdown, so that I can paste it into my notes.
17. As a fantasy manager, I want to delete a run, so that failed or junk runs don't clutter my history.
18. As a fantasy manager, I want my saved runs to survive a redeploy, so that upgrading the app doesn't wipe my history.

### The player reference

19. As a fantasy manager, I want a Players page showing every current NFL player, so that I can check the same data Claude is working from.
20. As a fantasy manager, I want each player's team, position, depth rank, ECR tier, ECR rank, bye week, and injury status, so that I get both the depth-chart picture and the fantasy-value picture in one table.
21. As a fantasy manager, I want depth rank and ECR tier shown as two distinct columns with distinct names, so that I am never misled into reading a depth-chart position as a fantasy ranking.
22. As a fantasy manager, I want to filter by one or more teams, so that I can look at a single matchup.
23. As a fantasy manager, I want to filter by one or more positions, so that I can look at just the running backs.
24. As a fantasy manager, I want to filter to players at or above a given depth rank, so that I can hide third-stringers.
25. As a fantasy manager, I want to search players by name, so that I can jump straight to someone the podcast mentioned.
26. As a fantasy manager, I want to sort by any column, so that I can rank by ECR or group by team as I choose.
27. As a fantasy manager, I want filtering and sorting to be instant, so that exploring the table doesn't feel like submitting a form.
28. As a fantasy manager, I want to see which season the displayed player reference belongs to, so that I know what I'm looking at.
29. As a fantasy manager, I want a prominent warning when the season shown isn't the current calendar season, so that I don't mistake last year's depth charts for this year's.
30. As a fantasy manager, I want to see when the player reference was last synced, so that I can judge how current it is.
31. As a fantasy manager, I want a **Sync now** button, so that I can pull fresh data immediately after a big trade or injury.
32. As a fantasy manager, I want the sync to happen automatically when the cached data is stale, so that a normal run doesn't require me to remember to refresh anything.
33. As a fantasy manager, I want injury status to show as blank rather than a stale designation when the injury feed has no current data, so that I don't act on a designation from three weeks ago.

### Summary quality

34. As a fantasy manager, I want Claude given a current player reference, so that a surname-only mention is attributed to the right player.
35. As a fantasy manager, I want Claude told each mentioned player's team and position, so that the summary reads correctly even when the hosts don't say them.
36. As a fantasy manager, I want Claude given depth rank and ECR tier as separate facts, so that it can distinguish "the starter" from "a player worth starting."
37. As a fantasy manager, I want the player reference narrowed to fantasy-relevant players, so that I'm not paying for thousands of rows of long-snappers on every run.
38. As a fantasy manager, I want the same structured summary sections I get today — news with sentiment, matchup analysis, player debates, waiver suggestions — so that the output format I'm used to doesn't change.
39. As a fantasy manager, I want the episode's title and upload date in the summary itself, so that a downloaded Markdown file stands on its own.

### When things go wrong

40. As a fantasy manager, I want a clear message when an episode has no captions, telling me auto-captions may still be generating, so that I know to try again later rather than assume the app is broken.
41. As a fantasy manager, I want a clear message when a video is private, members-only, or age-restricted, so that I understand the problem is the video, not the app.
42. As a fantasy manager, I want a clear message when YouTube blocks the request, so that I can recognise the bot-detection case rather than guessing.
43. As a fantasy manager, I want a run to still complete using the last cached player reference when nflverse is unreachable, with a visible warning about the data's age, so that an upstream outage costs me accuracy rather than the whole summary.
44. As a fantasy manager, I want a clear message when the Claude API fails or rate-limits, so that I know to retry rather than re-paste the URL.
45. As a fantasy manager, I want the raw error available behind a toggle, so that I can read the detail when I want it without it being shoved in my face when I don't.
46. As a fantasy manager, I want the title to fall back gracefully when metadata lookup fails but captions succeed, so that one flaky call doesn't cost me the whole run.

### Running and operating it

47. As the operator, I want the Hugging Face Whisper endpoint, the audio download, and the ffmpeg chunking gone, so that I stop paying for GPU time to obtain text YouTube already has.
48. As the operator, I want Postgres and its five environment variables gone, so that this app has one less external system to keep alive.
49. As the operator, I want the container built with uv against Python 3.14, so that the image matches the project's declared toolchain.
50. As the operator, I want the Kubernetes manifests and deploy workflow updated in the same change, so that the next deploy doesn't fail on environment variables that no longer exist.
51. As the operator, I want the app's data on a persistent volume, so that saved runs and the cached player reference survive a pod restart.
52. As the operator, I want the same app to run under Docker Compose locally with the same data path, so that local and deployed behaviour don't diverge.
53. As a developer, I want tests that assert on what Claude actually receives, so that a broken player reference fails a test rather than quietly degrading summaries.

## Implementation Decisions

### Application shape

- FastAPI application, server-rendered Jinja templates, HTMX for interactivity, Tailwind compiled to a committed stylesheet. No CDN references and no Node build step in the Docker image.
- Three routes-worth of UI: home (`/`), players, and history, plus a run-detail view and a Markdown download endpoint.
- The existing package directory keeps its shape. New modules sit alongside it: an app module, `templates/`, `static/`, and a `services/` package split into transcripts, players, summarize, and store. `main.py` and the `functions/` package are deleted.
- Dark visual theme: near-black surfaces, a single saturated accent, condensed uppercase headings, tabular numerals in data tables.

### Run execution and progress

- A run is started by a POST that returns immediately with a run identifier. The work executes in an in-process background task.
- Progress is delivered to the browser over Server-Sent Events. Event types cover stage transitions (captions fetched, metadata resolved, player reference loaded, summarization started), incremental summary text, terminal success, and terminal failure with a typed error kind.
- A pod restart loses an in-flight run. This is accepted; no queue, no worker process, no Redis.
- Both the transcript and the completed summary are persisted as part of the run record.

### Transcripts

- Captions are retrieved with `youtube-transcript-api` (v1.x instance-based API: construct the class, then `fetch` / `list`). Manually uploaded caption tracks are preferred over auto-generated ones; English is preferred.
- Caption segments are joined into a single running transcript. Timestamps are not retained.
- Episode title and upload date come from `yt-dlp` metadata extraction only — no audio download, no post-processors. If that call fails, fall back to YouTube's oEmbed endpoint for title and channel, and mark the upload date unknown rather than failing the run.
- ffmpeg, the staging directory, the audio chunking, the Hugging Face endpoint resume/poll/pause cycle, and all `HF_*` environment variables are removed.

### Player reference

- Sourced from `nflreadpy`: depth charts for depth rank, players for identity and bye week, fantasy rankings for ECR tier and ECR rank, injuries for status.
- `nflreadpy` returns Polars frames. Conversion happens at the service boundary; Polars frames do not leak into templates or the store.
- Cached in SQLite with a 12-hour TTL. A sync is triggered automatically when the cache is stale at the start of a run, and on demand from the Players page.
- Season resolution: attempt the current calendar season; if no depth-chart data exists for it, fall back to the most recent season that does. The resolved season is recorded with the cache and surfaced in the UI, and a mismatch against the current calendar season renders a warning.
- If a sync fails and a cached reference exists, the cached reference is used and the run proceeds with a staleness warning. If a sync fails and no cache exists, the run fails with the nflverse error kind.
- Injury status is rendered blank when the injury feed carries no data for the current week, rather than displaying an older designation.

### Two distinct player attributes

- **Depth rank** and **ECR tier** are separate fields, separately named, everywhere: in the store schema, in the Players page columns, and in the table handed to Claude. Nothing in the system is named simply `tier`. This corrects the existing conflation and is the reason ADR-0002 exists.

### Page data strategy

- The Players page ships the full player reference to the browser and does all filtering and sorting client-side. Roughly 2,800 rows; instant interaction is worth the payload. It ships as the rendered table, each row carrying its own values as `data-*` attributes, rather than as the JSON this said originally — see ADR-0003.
- The player reference handed to Claude is a deliberately narrower slice: fantasy-relevant positions at depth rank 3 or better, plus ECR tier and ECR rank. Approximately 700 rows.

### Claude integration

- Model defaults to `claude-sonnet-5`, overridable by the existing `CLAUDE_MODEL` environment variable.
- Streaming via the SDK's streaming helper, so the summary can be relayed over SSE and long generations don't hit HTTP timeouts.
- Adaptive thinking enabled; effort `medium`; `max_tokens` 16000.
- The player reference block in the system prompt is marked with `cache_control` so repeat runs within the cache window read it cheaply. It is byte-stable between runs by construction — deterministic ordering, no timestamps interpolated into it.
- The transcript, title, and upload date go in the user turn, after the cached prefix.
- The system prompt keeps the existing output contract: news items with player/team, description, and fantasy sentiment, followed by matchup analysis, player debates, waiver wire suggestions, and other relevant sections.

### Storage

- SQLite, single file, on a mounted volume path supplied by configuration.
- Two concerns: saved runs (URL, video identifier, title, channel, upload date, transcript, summary, model used, season used, created-at, duration) and the cached player reference (rows plus the resolved season and synced-at timestamp).
- Schema is created on startup if absent. No migration framework.

### Errors

- Failures are modelled as a small set of typed kinds rather than raw exceptions: no captions, video unavailable or restricted, YouTube blocked, nflverse unavailable, Claude failure, and invalid URL. Each maps to a specific user-facing message; the underlying error text is rendered behind a disclosure toggle.
- nflverse unavailability is the one kind that does not necessarily terminate a run — see the player reference decisions above.

### Injection points

- The three network edges — caption source, nflverse source, and the Claude client — are constructed through a small application-level dependency container rather than instantiated inline. This is what makes the HTTP-level tests possible without network access, and is the only reason the indirection exists.

### Packaging and deployment

- `pyproject.toml` gains `fastapi`, `uvicorn[standard]`, `jinja2`, `youtube-transcript-api`, and `nflreadpy`; it drops `gradio` and `psycopg2-binary`. `yt-dlp`, `anthropic`, `python-dotenv`, and `requests` stay.
- Dockerfile moves to a Python 3.14 slim base and `uv sync --frozen`. ffmpeg, `build-essential`, and `gcc` are removed from the image. `requirements.txt` is deleted; it has no remaining consumer.
- The served port moves off Gradio's 7860 to a conventional application port; Compose, the Kubernetes Service and Deployment, and the systemd port-forward reference are updated consistently.
- A PersistentVolumeClaim manifest is added and mounted at the data path. Docker Compose mounts a named volume at the same path.
- The deploy workflow's Secret and ConfigMap variable lists are updated to drop the `HF_*` and `PG_*` entries. The workflow is not executed as part of this work.

## Testing Decisions

### What a good test looks like here

A good test drives the application the way a browser does and asserts on what a user or a downstream system can observe: rendered page content, the sequence of SSE events, the record left in the store, and the exact payload handed to the Claude client. It does not reach into service internals, assert on function signatures, or touch the network.

The failure this suite exists to catch is a *plausible but wrong* player reference reaching Claude — wrong season, stale cache presented as fresh, depth rank and ECR tier transposed, or the narrowing filter silently dropping the wrong rows. Every one of those produces a summary that reads perfectly well and is wrong. Asserting on the payload the fake Claude client received catches all of them; asserting on intermediate return values catches only some.

### The seam

**One seam: the HTTP boundary.** Tests drive the FastAPI application through its test client. The three network edges are replaced at the dependency container with fakes backed by recorded fixtures — a caption payload, a set of nflverse frames, and a Claude client that records what it was given and replays a canned streamed response. Nothing in the suite makes a network call.

There is no second seam. The pure transforms are exercised through the same tests; a broken transform fails an HTTP-level assertion. This trades sharper failure messages for tests that survive refactoring, which is the right trade for a codebase that currently has no tests and an implementation about to be rewritten.

### Coverage

- A run against a fixture episode produces a saved run whose transcript and summary match expectations, emits SSE events in the correct order, and hands Claude a player reference containing the expected columns and excluding players below the depth cutoff.
- The player reference sent to Claude carries depth rank and ECR tier as distinct labelled columns.
- Repeated runs produce a byte-identical player reference block, so the prompt cache is not silently invalidated.
- The Players page renders the full reference with the season and last-synced strip, and shows the warning when the resolved season trails the calendar season.
- Season fallback: with nflverse holding no data for the current season, the page and any run both use the most recent season that has data, and say so.
- Each of the failure kinds renders its specific message with the raw error behind a toggle.
- An nflverse failure with a warm cache completes the run and shows the staleness warning; with a cold cache it fails with the nflverse message.
- Metadata failure with successful captions completes the run with a fallback title and an unknown upload date.
- Runs persist across an application restart; history lists them, the detail view reopens them, download returns Markdown, and delete removes them.

### Prior art

None — this repo has no test suite, no linter configuration, and no CI check. This is the first. Test layout, fixture conventions, and the fake implementations established here become the prior art for whatever follows.

## Out of Scope

- Any CI gate. `ruff` configuration and a GitHub Actions PR check were considered and deliberately deferred; the repo stays without one.
- Authentication, authorization, or multi-user support. Single-user app on a private network.
- A job queue, worker process, or any durability for in-flight runs across a restart.
- Editing a transcript before summarizing, or re-summarizing an existing run with a different model or prompt.
- Any Whisper fallback for caption-less episodes. Explicitly rejected in ADR-0001.
- Proxy configuration for datacenter-IP caption fetching. Not needed for the current self-hosted deployment; noted in ADR-0001 as the thing that would change if it ever moved.
- Migrating or preserving the existing Postgres data. The tables are seeded out-of-band and are being abandoned, not converted.
- Historical player data, week-by-week trends, or anything beyond the current player reference.
- Executing a deploy. The manifests and workflow are updated; running them stays with the operator.
- The `notebooks/` directory, including `nfl_extract.ipynb` and the ourlads CSV. They become dead weight once nflverse is the source, but removing them is not part of this change.

## Further Notes

- `CONTEXT.md` at the repo root holds the vocabulary this spec uses. Where this spec says depth rank, ECR tier, player reference, run, transcript, captions, sync, or season, it means what that file says.
- Three ADRs cover the irreversible parts: `docs/adr/0001-youtube-captions-over-whisper-transcription.md`, `docs/adr/0002-nflreadpy-instead-of-postgres-player-pipeline.md`, and `docs/adr/0003-the-players-table-is-html-the-browser-filters-in-place.md`. Neither the FastAPI choice nor the SQLite choice warranted one; both are ordinary and cheaply reversed.
- The dependency set resolves cleanly on Python 3.14 for linux — verified by dry-run resolution, including `nflreadpy` and its Polars runtime. Polars' PyPI classifiers stop at 3.13, which is a documentation lag rather than an incompatibility.
- `youtube-transcript-api` v1.x replaced the old static `get_transcript` call with an instance-based API. Code or documentation recalling the older shape is out of date.
- `yt-dlp` is now the only component that talks to YouTube's main site and therefore the only one exposed to bot detection. Its blast radius is deliberately limited to title and upload date, and the oEmbed fallback keeps a run alive when it fails. `--cookies-from-browser` remains the escape hatch if it becomes a recurring problem.
- Today is early August 2026 — preseason. nflverse may hold no 2026 depth charts yet. The season-fallback path is not an edge case at the time of writing; it is the path the app will take on its first run.
