# 02 — History in episode order, and a schema that can grow

**What to build:** History lists runs by the episode's own upload date, newest episode first, so an August episode summarized on Monday sits above a July episode summarized on Tuesday. A run whose upload date was never resolved sorts to the bottom. Searching and deleting return the list in that same order. The home page's recent five is untouched — it still answers "what did I just run".

Alongside it, startup gains an idempotent schema reconcile: it reads the columns the runs table already has and adds any that are missing. Nothing needs it yet; ticket 05 is its first user. Without it, a column added later never reaches the deployed database, because the schema is only created when absent.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] History orders by upload date descending with unknown dates last, then creation time descending, then identifier descending
- [ ] The search fragment and the post-delete list come back in the same order
- [ ] The home page's recent list still orders by creation time
- [ ] The two orderings are two separately named reads in the store, not one read with a flag
- [ ] An index covers the episode ordering and is created idempotently on startup
- [ ] Startup adds any column the runs table is missing, and is a no-op on a fresh database and on a second run
- [ ] A store created with an older schema keeps its rows through the reconcile
- [ ] Each History row still shows the episode's title, channel, upload date, and the date it was summarized
