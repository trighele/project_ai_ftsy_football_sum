# Specs and tickets

One directory per feature, `spec.md` inside it, tickets under `issues/`. See [docs/agents/issue-tracker.md](../docs/agents/issue-tracker.md).

Everything below came out of one design session on 2026-08-18 and is `ready-for-agent`.

## Specs

- [nflverse-retry](./nflverse-retry/spec.md) — retry dropped connections when syncing the player reference, and cache the tables on disk. Fixes a live failure.
- [history-episode-order](./history-episode-order/spec.md) — order History by the episode's own date. Introduces the schema migration pattern the context note depends on.
- [fantasy-position-buckets](./fantasy-position-buckets/spec.md) — Players page defaults to fantasy positions; one shared definition with the prompt.
- [context-note](./context-note/spec.md) — an optional per-episode instruction, saved and carried into the request.
- [markdown-preview](./markdown-preview/spec.md) — render the summary as prose, copy it as Markdown. Includes the stylesheet build fix that unblocks it.
- [batches](./batches/spec.md) — several episodes from one submission.

## Tickets, in dependency order

Ticket numbers are global across the six features, because the blocking edges cross them. Four tickets have no blockers and can start immediately: 01, 02, 03, 06, 08.

| # | Ticket | Blocked by |
|---|---|---|
| 01 | [Survive a dropped nflverse connection](./nflverse-retry/issues/01-survive-a-dropped-nflverse-connection.md) | — |
| 02 | [History in episode order, and a schema that can grow](./history-episode-order/issues/02-history-in-episode-order.md) | — |
| 03 | [One definition of a fantasy position](./fantasy-position-buckets/issues/03-one-definition-of-a-fantasy-position.md) *(prefactor)* | — |
| 04 | [The Players page opens on fantasy positions](./fantasy-position-buckets/issues/04-players-page-opens-on-fantasy-positions.md) | 03 |
| 05 | [A context note on a single episode](./context-note/issues/05-context-note-on-a-single-episode.md) | 02 |
| 06 | [Build the stylesheet on Windows](./markdown-preview/issues/06-build-the-stylesheet-on-windows.md) *(prefactor)* | — |
| 07 | [Read a summary as prose, and copy it as Markdown](./markdown-preview/issues/07-markdown-preview-and-copy.md) | 06 |
| 08 | [Extract the shared episode pipeline](./batches/issues/08-extract-the-shared-episode-pipeline.md) *(prefactor)* | — |
| 09 | [Summarize several episodes from one submission](./batches/issues/09-summarize-several-episodes-from-one-submission.md) | 05, 08 |
| 10 | [A batch that survives a messy paste](./batches/issues/10-a-batch-that-survives-a-messy-paste.md) | 09 |

## Decisions recorded alongside

ADR-0002 (depth rank and ECR tier stay separate), ADR-0003 (batches are ephemeral), ADR-0004 (Markdown rendered on the server). Terms added to [CONTEXT.md](../CONTEXT.md): batch, context note, fantasy position.
