# Player reference comes from nflreadpy, not a Postgres pipeline

Player data used to be scraped from ourlads.com by a notebook, loaded out-of-band into Postgres by a separate application, and read back by this app over a four-table join. We now read it directly from nflverse via `nflreadpy` (`load_depth_charts`, `load_players`, `load_ff_rankings`, `load_injuries`), cached locally in SQLite with a 12-hour TTL. Postgres, `psycopg2`, and five `PG_*` environment variables are removed entirely.

This also fixes a long-standing modelling error: the old pipeline stored depth-chart string number in a column named `tier` and the prompt then described it to Claude as a fantasy tier. Depth rank and ECR tier are now carried as separate, separately-named fields.

## Consequences

- The app no longer depends on a second application being alive and having run recently.
- nflverse publishes depth charts on a roughly weekly in-season cadence, and a new season's data does not appear until the season is underway. The app falls back to the most recent season that actually has data and displays which season is in use, so a preseason run is never silently summarized against last year's rosters.
- If the nflverse fetch fails, a run proceeds against the last cached player reference with a visible staleness warning rather than aborting.
