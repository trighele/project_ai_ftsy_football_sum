# 07 — Players page becomes explorable

**What to build:** The Players page becomes something worth opening. Sort on any column, filter by one or more teams, filter by one or more positions, hide players below a chosen depth rank, and search by name. Filtering and sorting are instant — no round trip, no form submission — because the full reference is shipped to the browser and handled client-side. Roughly 2,800 rows; the payload is worth the responsiveness.

The column set is completed here: player, team, position, depth rank, ECR tier, ECR rank, bye week, and injury status. Injury status renders blank when the injury feed carries no current-week data, rather than showing a designation from weeks ago — a stale "questionable" is worse than no value at all, because it will be acted on.

**Blocked by:** 06.

**Status:** done

- [x] Every column sorts, ascending and descending.
- [x] Teams filter as a multi-select.
- [x] Positions filter as a multi-select.
- [x] A depth-rank cutoff hides players below the chosen depth.
- [x] Name search narrows the table as it is typed.
- [x] Filters combine rather than replacing one another.
- [x] ECR tier, ECR rank, bye week, and injury status are all present as columns.
- [x] Injury status renders blank when the feed has no current-week data for that player.
- [x] Filtering and sorting happen client-side with no server round trip.
- [x] Numeric columns use tabular numerals so they align down the column.
- [x] Tests assert the page ships the full reference and renders the complete column set.

**Notes:** The reference is shipped as the rendered table with each row's values on
its `<tr>` as `data-*` attributes, rather than as the JSON the spec named — see
ADR-0003. The interaction itself (`static/js/players.js`) has no automated test:
there is no browser in the suite, so what is pinned is the contract between the
markup and the script.
