# 04 — The Players page opens on fantasy positions

**What to build:** The Players page arrives showing quarterbacks, running backs, fullbacks, wide receivers, tight ends, and kickers — not the 2,800 rows that include every guard and linebacker. A pair of toggles above the filters says which buckets are showing: **Fantasy positions**, on; **Everything else**, off until the reader asks. The position toggles below are grouped into those two labelled columns, so which positions count as fantasy-relevant is visible rather than remembered.

Everything else about filtering is as it was: ticking no position inside an enabled bucket still means all of them, team and search and depth rank still narrow each other, sorting still acts on what is shown, and the whole reference is still in the page so nothing is a round trip. **Clear** returns to the page as it opens — fantasy on, everything else off — not to every player.

**Blocked by:** 03 — One definition of a fantasy position.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] Every row carries a server-written bucket attribute; a fantasy-position row and a defensive row carry different values
- [ ] The bucket derives from the player's position, never from the depth chart's formation group column
- [ ] The fantasy toggle renders checked and the other unchecked, in the server-rendered markup, before any script runs
- [ ] Position facets render in two labelled groups with the right positions in each
- [ ] A row shows only when its bucket is enabled and it passes every other filter; an empty filter is still not a filter
- [ ] Ticking a position in a disabled bucket does not re-enable that bucket
- [ ] The "showing X of Y" count reflects the default view on arrival
- [ ] Clear returns to the default view rather than to an unfiltered one
- [ ] The buckets and their default survive a **Sync now**, which replaces the whole section
- [ ] The reference still holds every player; nothing is dropped from what is fetched, cached, or rendered
- [ ] The prompt is unchanged and its tests pass untouched
