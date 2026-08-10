# 03 — Runs are saved and reopenable

**What to build:** Every run is saved, so refreshing the page no longer loses work. The home page lists the five most recent runs beneath the input, and clicking one reopens it with its transcript intact. Saved runs survive an application restart.

Storage is a single SQLite file at a path supplied by configuration — this matters, because ticket 10 mounts a persistent volume at that path and should not have to change any application code to do it. The schema is created on startup when absent; no migration framework.

A run record carries the submitted URL, the video identifier, title, channel, upload date, transcript, the season of the player reference used, the model used, when it was created, and how long it took. The summary and model fields will be empty until ticket 04 fills them, and the season field until ticket 08 — define them now so those tickets don't need a schema change.

**Blocked by:** 02.

**Status:** ready-for-agent

- [x] A completed run is persisted automatically, with no explicit save action.
- [x] The five most recent runs appear on the home page with enough detail to identify the episode.
- [x] Clicking a recent run opens a detail view showing its transcript, title, channel, and upload date.
- [x] The SQLite file location is read from configuration, not hardcoded.
- [x] The schema is created on first startup when the database file does not exist.
- [x] A test proves runs written by one application instance are readable by a fresh one.
- [x] Tests continue to make no network calls.
