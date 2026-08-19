---
title: Show fantasy positions by default on the Players page, everything else on request
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

The Players page shows every player on every depth chart — roughly 2,800 rows, most of them linebackers, guards, and long snappers. A fantasy manager checking what the summarizer knows about a running back has to wade past players who will never be mentioned on a fantasy podcast. The position filter offers every position nflverse lists, in one long undifferentiated row of toggles, so narrowing to the positions that matter means ticking six boxes every time the page is opened.

## Solution

The page opens on **fantasy positions** — quarterback, running back, fullback, wide receiver, tight end, kicker — and everything else is one click away. The position toggles are grouped into two labelled columns, fantasy positions and everything else, so which is which is visible rather than remembered. Within whichever groups are enabled, the existing filters behave exactly as they do now: ticking nothing means all of them, and every filter narrows the others rather than replacing them.

The set of fantasy positions becomes a single definition shared with the prompt, so the page's default view and the slice of the reference Claude is given can never drift apart.

## User Stories

1. As a reader, I want the Players page to open on fantasy positions only, so that the page answers my question before I touch a control.
2. As a reader, I want defensive and offensive-line players available behind one toggle, so that they are out of the way without being hidden from me.
3. As a reader, I want the position toggles grouped into two labelled columns, so that I can see at a glance which positions the page considers fantasy-relevant.
4. As a reader, I want the kicker counted as a fantasy position, so that the one startable special-teams position is where I expect it.
5. As a reader, I want the "showing X of Y" count to reflect the default view, so that the number matches what is on the screen.
6. As a reader, I want team, search, and depth-rank filters to keep narrowing within the enabled groups, so that nothing about the existing filtering changes.
7. As a reader, I want ticking no position inside an enabled group to mean all of that group, so that the "empty means everything" rule I already rely on still holds.
8. As a reader, I want **Clear** to return to the default view rather than to every player, so that clearing gets me back to the page as it opens.
9. As a reader, I want sorting to act on what is currently shown, so that sorting and filtering compose the way they do today.
10. As a reader, I want the groups to survive a **Sync now**, so that a refresh does not dump every linebacker back onto the page.
11. As a reader, I want to be sure no defensive players are being fed to the summarizer, so that the model's attention is spent on players who might actually be discussed.
12. As a maintainer, I want one definition of "fantasy position" shared by the page and the prompt, so that changing it in one place cannot leave the other behind.
13. As a maintainer, I want the summaries themselves unchanged by this work, so that a filtering feature cannot quietly alter what Claude is told.

## Implementation Decisions

- **One definition, in the players module**: the set of fantasy positions is defined once where the reference is assembled, and the prompt builder imports it rather than declaring its own copy. Today the same six positions are written down twice; after this they are written down once.
- **Two buckets, not three.** Fantasy positions, and everything else. An offense/defense/special-teams split was considered and rejected: the reader's question is "can I start this player", and offensive linemen and defensive ends fall on the same side of that question.
- **Bucket membership is derived from position**, not from the depth chart's group column — that column holds formation names ("3WR 1TE", "Base 3-4"), not a side of the ball, and cannot answer this.
- **A row declares its bucket** as a data attribute written by the server, exactly like every other value the filters read. Nothing in the browser parses a cell or maps positions to buckets; the mapping exists in one place, server-side.
- **The bucket control is a pair of toggles above the position facets**, fantasy checked and everything-else unchecked when the page renders. The checked state is server-rendered, so a page that arrives before its script does still shows the intended default.
- **Filter semantics are preserved.** A row is shown when its bucket is enabled *and* it passes the position, team, search, and depth-rank filters, where an empty filter is not a filter. Position facets for a disabled bucket are still rendered, greyed or not, but ticking one does not re-enable its bucket — the bucket toggle is the thing that decides.
- **Clear resets to the default view**, not to an unfiltered one: fantasy bucket on, everything else off, all other filters emptied.
- **The reference itself is unchanged.** Every player on every depth chart is still fetched, cached, rendered into the page, and available — the buckets are a view over the same rows, which is what keeps the whole page a single payload with no round trips.
- **The prompt does not change at all.** It already restricts itself to the six fantasy positions at depth rank three or better; the kicker stays. This feature makes that restriction share its definition with the page, and nothing else. The byte-for-byte prompt tests are expected to pass untouched, and that is the point.

## Testing Decisions

A good test asserts what the server rendered — the attributes and the checked state the browser will act on — not the filtering itself, which is client-side and belongs to behaviour the suite has deliberately never driven.

- **Through the HTTP seam**, in the existing Players explorer tests: every row carries a bucket attribute; a fantasy-position row and a defensive row carry different ones; the fantasy toggle renders checked and the other unchecked; the position facets render in two labelled groups with the right positions in each.
- **Definition sharing**: a test asserting the prompt's position set is the players module's set — the same object, not an equal copy — so a future edit to one cannot silently fork them.
- **Unchanged and load-bearing**: the existing prompt tests, which assert the reference table handed to Claude byte for byte. They must pass without modification; if they need editing, this feature has changed the summaries and has gone wrong.
- **Prior art**: the existing Players explorer tests, which already assert on server-written data attributes rather than on rendered text.

## Out of Scope

- Changing which players are fetched from nflverse or what the reference holds.
- Changing the prompt, the depth-rank cut, or the kicker's presence in it.
- Testing the client-side filtering behaviour itself.
- Remembering the reader's bucket choice between visits.
- Per-position defaults finer than the two buckets.

## Further Notes

Fullback is in the fantasy bucket. It is a handful of players and is already in the prompt's position set; splitting it out would fork the shared definition this feature exists to create.
