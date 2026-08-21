# 08 — Extract the shared episode pipeline

**What to build:** A prefactor with no visible behaviour. Summarizing one episode end to end — resolve it, ensure the player reference, stream the summary, save the run — is currently welded to the events a single run publishes as it goes. This ticket separates the work from the telling: the pipeline becomes one thing that reports what happened, and the single-run path wraps it in exactly the stage, transcript, warning, and summary events it emits today.

Ticket 09 wraps the same pipeline in queue-row updates instead. Doing this first is what stops a run and a batch item drifting into producing different summaries.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [x] Summarizing one episode is callable independently of the events a single run publishes
- [x] The single-run path publishes the same events, in the same order, with the same payloads as before
- [x] The existing summary-stream tests pass without modification — that is the evidence the extraction was faithful
- [x] Failure handling is unchanged: every failure kind still reaches the reader the way it does now, and a run still always ends on exactly one terminal event
- [x] The stale-reference warning still reaches the page
- [x] No new module boundary is introduced beyond what the extraction needs
