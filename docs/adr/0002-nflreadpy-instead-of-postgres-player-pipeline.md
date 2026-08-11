# Player reference comes from nflreadpy, not a Postgres pipeline

Player data used to be scraped from ourlads.com by a notebook, loaded out-of-band into Postgres by a separate application, and read back by this app over a four-table join. We now read it directly from nflverse via `nflreadpy` (`load_depth_charts`, `load_players`, `load_ff_rankings`, `load_injuries`), cached locally in SQLite with a 12-hour TTL. Postgres, `psycopg2`, and five `PG_*` environment variables are removed entirely.

This also fixes a long-standing modelling error: the old pipeline stored depth-chart string number in a column named `tier` and the prompt then described it to Claude as a fantasy tier. Depth rank and ECR tier are now carried as separate, separately-named fields.

## What each table actually supplies

Implementing this turned up three gaps between what nflverse was expected to hold and what it holds:

- **ECR tier is derived, not published.** `load_ff_rankings` carries the expert consensus rank but no tier column — FantasyPros publishes tiers only on its own site. The tier is therefore computed from the consensus rank as the twelve-player band it falls in (`players.TIER_SIZE`), so tier 1 is who a manager spends a first-round pick on. This is a coarser instrument than FantasyPros' gap-based clustering, but it is deterministic, which the cached prompt prefix depends on, and it is genuinely independent of depth rank, which is the whole point of carrying it.
- **Bye week comes from the rankings, not the player table.** `load_players` has no bye week. The rankings rows carry one per player, and every team has ranked players, so a team-level bye is read off the same pass and applied to the players who have no ranking of their own.
- **The injury feed can be absent for a season that has depth charts.** nflverse refuses `load_injuries` for a season that has not kicked off, which in the preseason is the very season being read. That leaves the injury column blank rather than failing the sync, and blank is the right answer: last season's designations would be acted on.

Season resolution keys off nflverse's own mid-March roster rollover, so the new season's depth charts are looked for the moment they could exist.

## Consequences

- The app no longer depends on a second application being alive and having run recently.
- nflverse publishes depth charts on a roughly weekly in-season cadence, and a new season's data does not appear until the season is underway. The app falls back to the most recent season that actually has data and displays which season is in use, so a preseason run is never silently summarized against last year's rosters.
- If the nflverse fetch fails, a run proceeds against the last cached player reference with a visible staleness warning rather than aborting.
