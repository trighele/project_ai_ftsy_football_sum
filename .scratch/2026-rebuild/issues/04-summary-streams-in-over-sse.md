# 04 — Summary streams in over SSE

**What to build:** The same single click that fetched the transcript now also summarizes it. The transcript panel fills first, then the summary streams in below it as Claude writes it, with live status as each stage completes. The finished summary is saved to the run.

Starting a run returns immediately with a run identifier; the work happens in an in-process background task and progress reaches the browser over Server-Sent Events. The event protocol established here is used by every later ticket, so define it deliberately: stage transitions (captions retrieved, metadata resolved, summarization started), incremental summary text, terminal success, and terminal failure carrying an error kind. A pod restart losing an in-flight run is accepted — there is no queue and no worker process.

The prompt in this ticket uses the transcript, title, and upload date only. The player reference is wired in by ticket 08. Keep the existing output contract: news items with player or team, description, and fantasy sentiment, then matchup analysis, player debates, waiver wire suggestions, and other relevant sections.

Claude settings: model defaults to `claude-sonnet-5` and remains overridable by the existing model environment variable; use the SDK's streaming helper so long generations don't hit HTTP timeouts; adaptive thinking on, effort `medium`, `max_tokens` 16000.

This ticket also introduces the recording fake Claude client that ticket 08's assertions depend on — one that captures exactly what it was handed and replays a canned streamed response.

**Blocked by:** 03.

**Status:** ready-for-agent

- [x] One click produces both a transcript and a summary; there is no separate summarize step.
- [x] The transcript renders before summarization begins and stays visible while the summary streams.
- [x] Summary text appears incrementally rather than all at once on completion.
- [x] Stage transitions are visible to the user as the run progresses.
- [x] The Summarize button is disabled while a run is in flight.
- [x] The completed summary, the model used, and the run duration are saved to the run record.
- [x] Reopening a saved run shows its summary as well as its transcript.
- [x] The summary preserves the existing section structure and per-item fantasy sentiment.
- [x] A test asserts the SSE event sequence for a successful run.
- [x] The fake Claude client records the full request it received and is available to later tests.
