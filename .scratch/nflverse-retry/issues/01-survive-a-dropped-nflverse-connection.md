# 01 — Survive a dropped nflverse connection

**What to build:** A **Sync now** that hits a reset connection retries on its own and succeeds, instead of showing the reader a `ConnectionResetError`. The four nflverse tables are cached on disk under the configured data directory, so a retry does not re-download what it already has and a second sync the same day is nearly free. A season nflverse has not published yet still fails on the first ask, so the preseason season walk-back stays fast.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] A transient failure (connection reset, timeout, HTTP 5xx) is retried up to three attempts with growing, jittered waits
- [ ] An HTTP 404 raises on the first attempt with no wait, and the library's out-of-range-season `ValueError` does the same
- [ ] Three consecutive transient failures raise, and the last failure is the one the caller sees
- [ ] Retry lives inside the nflverse edge; the module that interprets the tables and every existing fake are unchanged
- [ ] The edge takes its loader and its sleep by injection, both defaulting to the real thing
- [ ] The upstream filesystem cache is enabled from inside the edge at construction, pointed at a subdirectory of the configured data directory, with a duration matching the reference's staleness window
- [ ] The HTTP timeout is raised above the library's 30-second default
- [ ] A new direct test of the edge covers the cases above without waiting in real time
- [ ] Every existing Players page and run test passes untouched
- [ ] The reader-facing failure sentence and the `nflverse` failure kind are unchanged; the chained cause still appears under the disclosure toggle
