# 09 — Failures explain themselves

**What to build:** When something breaks, the page says what broke and what to do about it, instead of reading as "the app is broken."

Six typed failure kinds, each with its own message:

- **No captions** — the episode has no caption track. Say that auto-captions may still be generating and to try again later. There is no fallback; ADR-0001 records why.
- **Video unavailable** — private, members-only, age-restricted, or deleted. Make clear the problem is the video, not the app.
- **YouTube blocked** — the request was refused by bot detection or IP blocking. Name it, so it is recognisable rather than mysterious.
- **nflverse unavailable** — see below; this one usually does not end the run.
- **Claude failure** — API error or rate limit. Say it is worth retrying.
- **Invalid URL** — rejected before any network call.

Every message carries the underlying error text behind a disclosure toggle: available when wanted, not shoved in the face when not.

**The nflverse case is the important one.** If a sync fails and a cached player reference exists, the run proceeds against the cache and shows a visible staleness warning naming the data's age. An upstream outage should cost accuracy, not the whole summary. Only when there is no cache at all does the run fail.

Failures are modelled as a small set of kinds rather than raw exceptions, and travel to the browser on the SSE terminal-failure event established in ticket 04.

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] Each of the six failure kinds renders its own specific, actionable message.
- [ ] The raw underlying error is available behind a toggle on every failure.
- [ ] An nflverse failure with a warm cache completes the run and displays a staleness warning naming the data's age.
- [ ] An nflverse failure with no cache fails the run with the nflverse message.
- [ ] A metadata failure with successful captions still completes the run, with a fallback title and unknown upload date.
- [ ] Failures reach the browser over the existing terminal-failure event and carry the error kind.
- [ ] A failed run does not leave a half-written record that looks successful in History.
- [ ] Tests cover each failure kind end to end, plus both nflverse degradation paths.
