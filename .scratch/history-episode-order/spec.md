---
title: Order History by the episode's own date, not the day it was summarized
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

The History page lists every saved run newest-summarized first. That is the order the work happened in, not the order the episodes did. Catching up on a backlog — summarizing a July episode on Tuesday and an August episode on Monday — leaves the older episode sitting at the top of the list, because it was summarized more recently. What a reader is looking for is the most recent *episode*, and the list does not answer that question.

## Solution

History orders runs by the episode's upload date, newest episode first. A run whose upload date could not be determined sorts to the bottom rather than to the top, because an unknown date is not a recent one. Searching and deleting keep that order, since both re-render the same list.

The home page's recent runs are left alone: that list answers "what did I just run", which is a different question and is already answered correctly.

## User Stories

1. As a reader, I want History ordered by the episode's air date, so that the newest episode I have covered is the first thing I see.
2. As a reader summarizing a backlog out of order, I want the list unaffected by the order I did the work in, so that catching up does not scramble the list.
3. As a reader, I want a run whose upload date is unknown to sort last, so that a missing date never masquerades as a fresh episode.
4. As a reader, I want two episodes uploaded the same day to fall back to the order I summarized them in, so that ties resolve predictably rather than at random.
5. As a reader searching by title, I want matches in the same episode order, so that the search is a filter over the list rather than a different list.
6. As a reader deleting a run, I want the list that comes back in the same order, so that a delete does not reshuffle what I was looking at.
7. As a reader, I want the home page's recent five to keep showing what I most recently summarized, so that I can find the run I just started.
8. As a reader, I want each row to keep showing when it was summarized, so that the information the ordering no longer carries is still on the page.
9. As a maintainer, I want the two orderings named separately in the store, so that the next reader can see there are two questions being asked and which is which.
10. As a maintainer, I want the ordering supported by an index, so that a growing history does not turn the page into a table scan.
11. As a maintainer, I want the first schema migration to establish a repeatable pattern, so that the next column to be added has somewhere obvious to go.

## Implementation Decisions

- **Two orderings, named, in the store.** The single "newest first" ordering becomes two: one by episode date for History and its search, one by creation time for the home page's recent list. Neither is a parameter with a default — they are two different reads with two different names, because a boolean flag at every call site would leave the question "which order is this?" answered by an argument rather than by a name.
- **Episode ordering is** upload date descending with unknown dates last, then creation time descending, then identifier descending. SQLite here supports `NULLS LAST` directly (3.50), so the ordering is stated rather than emulated with a `CASE`.
- **An index covers the new ordering**, created with the existing schema statements on startup and therefore safe to re-run.
- **This feature introduces the migration pattern.** Schema creation is `CREATE TABLE IF NOT EXISTS`, which silently does nothing to a database that already exists — so a column added later never reaches the deployed database. Startup gains an idempotent step that reads the table's existing columns and adds any that are missing. It runs before the index is created and is a no-op on a fresh database. The next feature (the context note) is the first to add a column through it.
- **No user-facing control.** There is no toggle between the two orderings; History has one order and the home page has the other. A sort control on History is a bigger feature than this one and would want a stated default anyway.
- **Row content is unchanged.** Each row still shows the episode's title, channel, upload date, and the date it was summarized.

## Testing Decisions

A good test here drives the page and reads the order of what came back, rather than testing the SQL. The store is not a network edge, so tests exercise the real SQLite file in a temporary directory.

- **Through the HTTP seam**, in the existing History tests: three runs whose upload dates and summarized dates disagree come back in episode order; a run with no upload date comes back last; a search over the same set preserves that order; a delete returns the remaining rows in that order.
- **Directly against the store**, in the existing saved-runs tests: the recent-runs read still answers in creation order, so the two orderings are demonstrably different reads.
- **Migration**: a store created with an older schema, then initialized again, gains the missing column and keeps its rows. This test lands with the pattern rather than with its first use, because the pattern is the thing that must not be got wrong.
- **Prior art**: the existing History and saved-run tests, which already build runs with controlled titles through the run pipeline.

## Out of Scope

- A user-selectable sort on History, ascending order, or sorting by channel.
- Backfilling upload dates for runs that never resolved one.
- Changing what the home page's recent list shows or how many it shows.
- Grouping History by season, month, or channel.

## Further Notes

Upload date is stored as an ISO date string, which sorts correctly as text, so no column type change is involved.
