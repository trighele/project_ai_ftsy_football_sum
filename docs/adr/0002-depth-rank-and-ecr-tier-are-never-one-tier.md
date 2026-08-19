# Depth rank and ECR tier are carried separately and never collapsed into "tier"

The player reference carries two numbers for every player: **depth rank**, their place on their own team's depth chart, and **ECR tier**, the band their expert consensus ranking falls in. They answer different questions — who is on the field, and who is worth starting — and neither implies the other. They are stored in two fields with two names, rendered as two columns, and described to Claude as two things in a paragraph that says outright that they are independent.

This is recorded because the app it replaced did the opposite: the Postgres-backed pipeline stored the depth-chart string number in a column named `tier` and handed it to the model described as a fantasy tier, so every summary it wrote called a team's starting kicker a tier-1 asset. The defect was invisible in the output — the summaries read perfectly — which is exactly why the correction is written down rather than left as a naming preference somebody could tidy away.

## Consequences

- Nothing in `players.py` or `summarize.py` may be named `tier` on its own. `ecr_tier` and `depth_rank` are the only spellings.
- nflverse publishes no tier column, so ECR tier is *derived* from ECR rank as the `TIER_SIZE`-player band it falls in. Deriving it the same way every time is also what the cached prompt prefix depends on.
- The two-numbers paragraph in the system prompt exists to stop the model recreating the collapse on its own, and is part of the byte-stable cached block.
