# The Players table is HTML the browser filters in place, not JSON it renders

The spec said the Players page would ship the player reference to the browser **as JSON** and render the table client-side. It ships it as the rendered table instead, with each row's values written onto its `<tr>` as `data-*` attributes, and `static/js/players.js` sorts and filters those rows where they stand. Filtering and sorting are still entirely client-side, which is the requirement the JSON was a means to.

Rendering client-side from JSON would have meant sending the whole reference twice — once as the table a reader sees on load, once as the JSON the script rebuilds it from — or sending no table at all until the script had run. The first is wasteful; the second makes the page's central content invisible to anything that is not a browser running our script, including the test suite, which drives every other page through its HTML. Ticket 06's tests already read player rows out of the rendered table, and they read the same rows a reader sees, which is the property worth keeping.

## Consequences

- The row is the record. Every value a control reads — name, team, position, depth rank, ECR tier, ECR rank, bye week, injury status — is an attribute on the `<tr>`, so the script never parses a cell and never holds a second copy of the table. A value the reference does not have is an absent attribute rather than an empty one: it filters out and sorts last, which `""` would not.
- The page is around 2,800 rows of HTML rather than 2,800 rows of JSON — a larger payload than the JSON alone, and smaller than the two together. It is served over a local network to one reader, and it is the reason no interaction after load costs a request.
- Filter and sort state does not survive a **Sync now**: the swap replaces the controls along with the table. Restoring it would mean keeping state the markup no longer holds, which is the arrangement this decision exists to avoid.
- Sorting and filtering are the one part of the app with no automated test — they run in a browser the suite does not have. What is pinned instead is the contract between the two halves: that every row is present, carries the attributes the script reads, and that each column offers a sort control.
