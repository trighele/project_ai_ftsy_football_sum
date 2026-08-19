# 10 — A batch that survives a messy paste

**What to build:** A list of URLs pasted out of a notes app is rarely tidy. Blank lines are ignored. The same episode listed twice — including once as a share link and once as a watch link — is summarized once. A line that is not a usable YouTube URL is marked failed in the queue before any work starts, so the reader finds out in a second rather than eight minutes in, and nothing asks YouTube about it.

A batch is capped at ten episodes: over the cap, nothing starts and the reader is told. An empty submission is refused the same way.

**Blocked by:** 09 — Summarize several episodes from one submission.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] Blank and whitespace-only lines are dropped
- [ ] Duplicates are collapsed by resolved video identifier, keeping the first occurrence, so two URL forms of one episode run once
- [ ] An unparseable line becomes a failed row with the same invalid-URL failure kind a single run uses, before any episode is worked on
- [ ] No caption or metadata call is made for a URL that could not be parsed
- [ ] A submission over the cap of ten is rejected with an error panel and starts nothing
- [ ] An empty submission is rejected the same way
- [ ] Validation happens up front, so the queue panel shows the full set of rows — failures included — from the moment it renders
