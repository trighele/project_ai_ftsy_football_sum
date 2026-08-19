---
title: Survive a dropped connection when syncing the player reference
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

Pressing **Sync now** on the Players page fails intermittently with a connection error, and the reader is shown the raw exception:

```
NflverseUnavailableError: The player reference could not be fetched from nflverse.
caused by: ConnectionError: Failed to download .../depth_charts_2026.parquet:
  ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
```

GitHub — where nflverse publishes its releases — resets a connection partway through a parquet download often enough to notice. Nothing retries it. One reset anywhere in the four-table sync fails the whole sync, and because the tables are cached in memory only, everything already downloaded in that attempt is thrown away too. When there is nothing in the local cache yet, the same reset ends a *run* with the `nflverse` failure kind, so a dropped TCP connection costs a summary.

## Solution

A transient failure is retried instead of reported. A sync that hits a reset waits a moment and asks again, up to three attempts, and only tells the reader it failed once the network has genuinely refused three times. Between attempts nothing already downloaded is re-fetched: the tables are cached on disk, on the same volume the runs and the reference already live on, so a retry resumes rather than restarts and a second sync the same day is nearly free.

Failures that are not transient — a season nflverse has not published yet — are not retried, because the preseason season walk-back depends on that answer arriving quickly.

## User Stories

1. As a reader, I want a sync that hits a dropped connection to try again on its own, so that a transient network fault does not look like a broken application.
2. As a reader, I want the retries to happen inside the one **Sync now** press, so that I am not the retry mechanism.
3. As a reader, I want a sync that genuinely cannot reach nflverse to still tell me so, so that a silent hang never replaces an honest failure.
4. As a reader, I want the underlying error still available behind the disclosure toggle after the retries are exhausted, so that I can see what actually happened.
5. As a reader, I want a run whose player reference sync drops a connection to still produce a summary, so that a network blip does not cost me the episode.
6. As a reader, I want a second sync on the same day to be fast, so that opening the Players page is not a minute of downloading.
7. As a reader, I want the cached tables to survive a container restart, so that a Watchtower update does not mean re-downloading everything.
8. As a reader in the preseason, I want the season walk-back to stay fast, so that a season nflverse has not published yet does not add pointless waiting for every season tried.
9. As a maintainer, I want retry behaviour to live at the network edge, so that the module holding what the tables mean stays free of transport concerns.
10. As a maintainer, I want retries covered by a test that does not wait in real time, so that the suite stays fast.
11. As a maintainer, I want the retry to be invisible to the rest of the application, so that no caller and no fake has to be taught about it.
12. As a maintainer, I want the disk cache pointed at the configured data directory, so that the deployment's single mounted volume holds everything worth keeping.

## Implementation Decisions

- **Retry lives in the nflverse edge**, alongside the four calls it wraps — not in the module that interprets the tables. Precedent: the captions edge already owns a transport-level fallback (the oEmbed lookup when the metadata call fails), for the same reason.
- **Three attempts, exponential backoff with jitter**: roughly one second, then two, then give up after the third failure. Jitter so two syncs started together do not retry in lockstep.
- **Only transient failures retry.** The upstream library wraps every `requests` exception in a single `ConnectionError` carrying the URL, so the classification reads the chained cause: a reset, a timeout, or an HTTP 5xx retries; an HTTP 404 does not, and neither does the library's `ValueError` for a season outside the range it holds or for a payload it could not parse.
- **The 404 decision is load-bearing.** A 404 is the *normal* preseason answer for the current season's depth charts, and the season walk-back tries up to five seasons. Retrying it would multiply the ordinary preseason path by the whole backoff schedule, once per season tried.
- **The edge takes its collaborators by injection**: the loader it calls and the sleep it waits with, both defaulting to the real thing. This is what makes the retry testable at all, since every other test replaces the whole edge with a fake.
- **The upstream filesystem cache is turned on** from inside the edge at construction, rather than through environment variables, so the edge configures itself and no deployment has to know. The cache directory is a subdirectory of the configured data directory — decided in the configuration module, which is the only place a path is decided — and the cache duration matches the reference's own twelve-hour staleness window.
- **The HTTP timeout is raised** from the library's thirty-second default, which is tight for a multi-megabyte parquet on a domestic connection.
- **Nothing above the edge changes.** `NflverseUnavailableError`, the fallback to a stale cached reference, the warning strip on a run, and the `nflverse` failure kind all behave exactly as they do now.
- **No new failure kind.** A retry-exhausted sync is the same failure it is today; the reader-facing sentence is unchanged, and the chained cause under the disclosure toggle still names the reset.

## Testing Decisions

A good test here asserts what the edge did, not how it decided to: how many times the loader was called, what came back, and how long it claimed to wait — never the internals of the backoff calculation.

- **New seam.** A direct test of the nflverse edge with an injected loader and an injected sleep, mirroring the existing direct test of the YouTube source. This is the second and last exception to the otherwise HTTP-only suite; it exists because the retry is by design invisible from outside the application.
- **Cases**: a loader that fails twice then succeeds returns the frame and was called three times; a loader that fails three times raises, and the last failure is the one that reaches the caller; a 404 raises on the first attempt with no sleep; the library's season `ValueError` raises on the first attempt; the recorded sleeps increase.
- **Unchanged**: every existing Players page and run test, which replace the whole edge with the existing fake. That they keep passing untouched is the evidence that nothing above the edge learned about retries.

## Out of Scope

- Mirroring nflverse data anywhere, or fetching it from anything but the upstream releases.
- Changing which four tables are read, or tolerating a missing one beyond the injury feed's existing exemption.
- Any background or scheduled sync. Syncing stays on demand and on staleness.
- Surfacing retry progress to the reader. A sync that is retrying looks like a sync that is slow.

## Further Notes

The upstream library's memory cache is per-process and lives for the life of the container, so today's behaviour is not "no cache" so much as "a cache a restart empties". The filesystem cache is strictly additive to it.
