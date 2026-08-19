# 09 — Summarize several episodes from one submission

**What to build:** The home page offers two ways in. **Single episode** is what exists today, keeping its context note. **Multiple episodes** takes a list of URLs, one per line, and summarizes them one after another from a single click.

What the page shows for a batch is a queue: one row per episode, moving from queued to running to a link to its saved run, or to a failure naming its kind with the underlying error behind the usual disclosure. A failing episode does not stop the ones after it. Summary text is not streamed for a batch — the queue reports state, and the summaries are read on their run pages. When the batch ends it says so, and the recent-runs list is up to date.

A batch is ephemeral and in-process, exactly as a run is (ADR-0003): a reload loses the queue, the finished episodes are in History. This ticket assumes well-formed input; ticket 10 handles a messy paste.

**Blocked by:** 05 — A context note on a single episode (the single tab has to keep carrying it); 08 — Extract the shared episode pipeline.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] The home page presents single and multiple submission as two tabs over two real forms, each posting to its own route
- [ ] The single tab is unchanged, context note included
- [ ] A batch submission returns at once with a queue panel naming the stream to follow
- [ ] Episodes are summarized one at a time, in the order submitted
- [ ] Each episode's row updates as it starts and as it finishes, and becomes a link to its saved run immediately on success
- [ ] A failed episode's row names its failure kind and offers the underlying error, and the batch carries on
- [ ] Each finished episode is saved as an ordinary run and appears in History
- [ ] The batch emits exactly one terminal event, carrying the counts, even when every episode failed
- [ ] A batch whose driving task dies still ends its stream, the way a lost run does
- [ ] The batch's event names are its own, distinct from a run's
- [ ] The recent-runs list is refreshed when the batch ends
- [ ] Navigating away does not cancel the batch
- [ ] A saved run carries no batch identifier, and History has no batch grouping
- [ ] The existing single-run tests pass untouched
