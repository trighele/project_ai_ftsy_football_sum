---
title: Summarize several episodes from one submission
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

Episodes are summarized one at a time. A reader catching up on a week of podcasts pastes a URL, waits for the run, waits for the Summarize button to come back, pastes the next one, and repeats. The work is entirely unattended once it starts, but the reader is not: they have to be at the page to start each one.

## Solution

The home page offers two ways in. **Single episode** is what exists today, now with an optional context note. **Multiple episodes** takes a list of URLs and summarizes them one after another from a single click. What the page shows for a batch is a queue: one row per episode, each moving from queued to running to a link to its saved run, or to a failure that names its kind. The episodes that finish are ordinary saved runs and appear in History like any other.

A **batch** is ephemeral and in-process, exactly as a run is: no queue table, no worker process, and a restart loses it. See ADR-0003.

## User Stories

1. As a reader, I want to paste several episode URLs and start them with one click, so that a backlog is one submission rather than six.
2. As a reader, I want to choose between single and multiple submission, so that the simple case stays simple.
3. As a reader, I want the single form to keep its context note, so that choosing the batch form is the only thing that gives it up.
4. As a reader, I want the episodes summarized one after another, so that submitting six does not get me rate-limited by YouTube.
5. As a reader, I want them summarized in the order I listed them, so that the queue is predictable.
6. As a reader, I want each episode's progress visible in the queue, so that I can see which one is being worked on.
7. As a reader, I want a finished episode to become a link to its run immediately, so that I can start reading the first one while the rest are still going.
8. As a reader, I want one failing episode not to stop the others, so that a dead video does not cost me the batch.
9. As a reader, I want a failed episode to say why in the same terms a single run does, so that I know whether to retry it or give up on it.
10. As a reader, I want to see the underlying error for a failed episode, so that the disclosure I rely on elsewhere is there too.
11. As a reader, I want a duplicate URL summarized once, so that pasting the same episode twice does not cost me two runs.
12. As a reader, I want the same episode pasted in two different URL forms recognised as one episode, so that a share link and a watch link do not both run.
13. As a reader, I want blank lines ignored, so that a pasted list does not need tidying.
14. As a reader, I want an unusable URL flagged before anything starts, so that I find out in a second rather than eight minutes in.
15. As a reader, I want a limit on how many episodes one batch takes, so that a bad paste does not start an hour of work.
16. As a reader, I want the batch to keep going if I navigate away, so that leaving the page does not cancel the work.
17. As a reader, I want the finished episodes in History, so that losing the queue panel does not lose the work.
18. As a reader, I want the recent-runs list on the home page to be up to date when the batch ends, so that what I just produced is where I expect it.
19. As a reader, I want the batch to say when it has finished and how it went, so that I know it is safe to walk away from.
20. As a maintainer, I want a batch to reuse the run's event machinery, so that there is one way to follow work in this application rather than two.
21. As a maintainer, I want the summarizing work itself shared between a run and a batch item, so that the two paths cannot drift into producing different summaries.
22. As a maintainer, I want a batch to emit exactly one terminal event, so that a stream that merely stops stays impossible.

## Implementation Decisions

- **A batch is a first-class submission with its own route and its own event stream**, and it reuses the existing live-run machinery unchanged: a token, a buffered event list, and exactly one terminal event. Buffering matters for the same reason it does for a run — the browser starts the work and follows it in two separate requests.
- **The work is shared, the presentation is not.** The end-to-end summarizing of one episode is extracted so that both paths call it: the single run wraps it in the stage, transcript, warning, and summary events it emits today; a batch item wraps it in a queue-row update. Neither path re-implements the episode pipeline, and a change to it cannot affect only one of them.
- **Its own event names.** A batch emits one event per queue-row state change, carrying the server-rendered row, and one terminal event carrying the counts. It does not reuse the run's stage or summary event names: distinct names mean the two client scripts cannot misread each other's streams. The terminal event is emitted even when every episode failed — a batch that ran is a batch that finished. A batch whose driving task dies emits the same kind of lost-work failure a run does.
- **Summary text is not streamed for a batch.** The queue reports state, not prose; the summaries are read on their run pages.
- **Validation happens up front, before any work.** Lines are trimmed, blanks dropped, each URL parsed into a video identifier, duplicates collapsed keeping the first occurrence, and unparseable lines marked as failed rows immediately with the same invalid-URL failure kind a single run uses. No network call is made for a URL that could not be parsed.
- **A cap of ten episodes per batch.** Over the cap the submission is rejected with an error panel and nothing starts; an empty submission is rejected the same way.
- **Sequential execution on one worker thread.** Parallelism was considered and rejected in ADR-0003.
- **The player reference is ensured per episode**, through the existing call — the twelve-hour cache means that is one sync for the batch, and it keeps a long batch from working against a reference that went stale halfway through.
- **The two modes are tabs over two real forms**, each posting to its own route. Both work without JavaScript in the sense that the submission is a genuine form post; the live queue, like the live run panel, needs the script.
- **Nothing downstream knows about batches.** A saved run carries no batch identifier and History has no batch grouping; a batch is a way of starting work, not a thing the domain model keeps.

## Testing Decisions

A good test drives a batch the way the browser does — submit, then read the whole event stream — and asserts on the sequence of events and on what ended up saved. It does not assert on how many events a particular episode produced on the way.

- **Through the HTTP seam**, extending the existing event helpers to start and follow a batch as they already do for a run: three URLs are summarized in submitted order and three runs are saved; a middle episode whose captions fail leaves the other two saved and its own row failed with the right kind; every batch ends with exactly one terminal event; the terminal event's counts match what was saved.
- **Validation without the network**: a batch of duplicates in different URL forms runs the episode once; blank lines are ignored; an unparseable URL is a failed row and the captions fake records no call for it; an over-cap and an empty submission are rejected without starting anything.
- **The shared pipeline**: a single run's event sequence is unchanged by the extraction — the existing summary-stream tests must pass untouched, which is the evidence the two paths still share one implementation.
- **Prior art**: the existing summary-stream tests and the event helpers they use, which already start a run and read its whole stream in one call.

## Out of Scope

- Persisting a batch, resuming one after a restart, or reopening a past batch.
- Cancelling a batch or an episode within one, or reordering the queue.
- Parallel execution, or any concurrency control beyond one at a time.
- Context notes on batch episodes.
- Accepting a YouTube playlist or channel URL and expanding it into episodes.
- Any batch grouping in History, or a batch identifier on a saved run.

## Further Notes

The retained-runs registry already keeps the last few finished runs so a browser can follow work it started; batches use the same registry type and inherit that behaviour. A batch of ten holds one live entry, not ten.
