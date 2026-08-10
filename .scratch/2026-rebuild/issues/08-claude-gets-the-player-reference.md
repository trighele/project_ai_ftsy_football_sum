# 08 — Claude gets the player reference

**What to build:** Summaries start attributing players correctly. The player reference is narrowed and handed to Claude in the system prompt, so a surname-only mention lands on the right player, with the right team and position, and the summary can distinguish a starter from a player actually worth starting.

The slice sent to Claude is deliberately narrower than what the Players page shows: fantasy-relevant positions at **depth rank** 3 or better, carrying team, position, depth rank, and **ECR tier**. Roughly 700 rows rather than 2,800. The Players page is for exploring; the prompt is for accuracy per token.

Depth rank and ECR tier go in as two separately labelled columns, and the prompt explains the difference to Claude — that depth rank describes position on the depth chart and ECR tier describes fantasy value, and that they do not imply one another. The current app's habit of describing a depth-chart string as a fantasy tier is the specific defect being fixed.

The reference block is marked with `cache_control` and must be byte-stable between runs: deterministic row ordering, no timestamps or run identifiers interpolated into it. A single varying byte silently invalidates the cache and every run pays full price with no error to tell you. The transcript, title, and upload date belong in the user turn, after the cached prefix.

**This is the ticket the test seam exists for.** The failure mode being defended against is a plausible-but-wrong reference reaching Claude — wrong season, transposed depth rank and ECR tier, or the narrowing filter dropping the wrong rows. Each produces a summary that reads perfectly and is wrong. Assert on what the fake Claude client actually received.

Also: record on each run which season's player reference it used, and show it on the run detail view.

**Blocked by:** 04 and 06.

**Status:** ready-for-agent

- [ ] The system prompt contains the narrowed player reference as a table.
- [ ] Depth rank and ECR tier appear as separate labelled columns, and the prompt explains what each means and that they are independent.
- [ ] Only fantasy-relevant positions at depth rank 3 or better are included.
- [ ] The reference block carries `cache_control`.
- [ ] Two consecutive runs produce a byte-identical reference block — asserted by a test, not by inspection.
- [ ] The transcript, title, and upload date sit in the user turn, after the cached prefix.
- [ ] The season used is saved on the run record and shown on the run detail view.
- [ ] A test asserts the exact reference the fake Claude client received: expected columns present, players below the depth cutoff absent.
- [ ] A test asserts that when the resolved season is behind the calendar season, the run uses and records the resolved season rather than silently using nothing.
