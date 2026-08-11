# 06 — Player reference syncs from nflverse

**What to build:** A Players page showing the current player reference, sourced from nflverse instead of Postgres. The page carries a header strip stating which season the data belongs to, when it was last synced, and a **Sync now** button. When the season shown is not the current calendar season, a prominent warning says so — this is not a rare edge case, it is what happens in the preseason before nflverse publishes the new year's depth charts.

The reference is assembled from nflreadpy: depth charts for **depth rank**, players for identity and bye week, fantasy rankings for **ECR tier** and ECR rank, injuries for status. It is cached in SQLite with a 12-hour TTL, synced automatically when stale at the start of a run, and on demand from the page.

**Depth rank and ECR tier are two different things and must never be collapsed into a single field named `tier`.** Depth rank says who is on the field; ECR tier says who is worth starting. They are stored separately, named separately, and displayed separately. Correcting this conflation is why ADR-0002 exists — read it before starting.

Season resolution: attempt the current calendar season; if nflverse holds no depth charts for it, fall back to the most recent season that does. The resolved season is stored with the cache and surfaced everywhere the reference is shown.

nflreadpy returns Polars frames. Convert at the service boundary — Polars frames must not reach templates or the store.

The table in this ticket can be plain: all rows, fixed column order, no filtering or sorting. Ticket 07 makes it explorable.

**Blocked by:** 03.

**Status:** done

- [x] A Players page renders the full current player reference.
- [x] Depth rank and ECR tier appear as distinct columns with distinct names; nothing in the schema, page, or code is named simply `tier`.
- [x] The header strip shows the season in use and how long ago the reference was synced.
- [x] A warning renders when the resolved season is behind the current calendar season.
- [x] **Sync now** refreshes the reference immediately and updates the last-synced time.
- [x] A stale cache triggers an automatic sync; a fresh one does not.
- [x] With no nflverse data for the current season, the app resolves to the most recent season that has data and says which.
- [x] Polars frames do not escape the player service.
- [x] The nflverse source is resolved through the dependency container and is replaced by fixture frames in tests.
- [x] Tests cover a cold sync, a cached read within TTL, a stale-cache refresh, and the season fallback path.
