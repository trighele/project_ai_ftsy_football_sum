# 07 — Players page becomes explorable

**What to build:** The Players page becomes something worth opening. Sort on any column, filter by one or more teams, filter by one or more positions, hide players below a chosen depth rank, and search by name. Filtering and sorting are instant — no round trip, no form submission — because the full reference is shipped to the browser and handled client-side. Roughly 2,800 rows; the payload is worth the responsiveness.

The column set is completed here: player, team, position, depth rank, ECR tier, ECR rank, bye week, and injury status. Injury status renders blank when the injury feed carries no current-week data, rather than showing a designation from weeks ago — a stale "questionable" is worse than no value at all, because it will be acted on.

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] Every column sorts, ascending and descending.
- [ ] Teams filter as a multi-select.
- [ ] Positions filter as a multi-select.
- [ ] A depth-rank cutoff hides players below the chosen depth.
- [ ] Name search narrows the table as it is typed.
- [ ] Filters combine rather than replacing one another.
- [ ] ECR tier, ECR rank, bye week, and injury status are all present as columns.
- [ ] Injury status renders blank when the feed has no current-week data for that player.
- [ ] Filtering and sorting happen client-side with no server round trip.
- [ ] Numeric columns use tabular numerals so they align down the column.
- [ ] Tests assert the page ships the full reference and renders the complete column set.
