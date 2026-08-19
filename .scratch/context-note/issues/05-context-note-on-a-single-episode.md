# 05 — A context note on a single episode

**What to build:** The single-episode form gains an optional note — a few sentences saying what this summary should pay attention to. The note travels with the episode into the summary request, is saved with the run, is shown when the run is reopened, and appears in the Markdown the run is downloaded as. A run submitted without one looks and behaves exactly as it does today.

The note goes in the user turn, never in the system prompt: the system prompt's second block is marked for caching and must stay byte-identical between runs. This is the decision the ticket exists to get right.

**Blocked by:** 02 — History in episode order, and a schema that can grow (for the startup schema reconcile that adds the column to the deployed database).

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] The single-episode form has an optional note field; submitting without one is unchanged in every respect
- [ ] The note appears in the user turn, after the title and upload date and before the transcript, under a label naming it as the reader's own instruction
- [ ] With no note, the user turn is byte-for-byte what it is today — no empty label, no stray blank line
- [ ] The system blocks are byte-identical with and without a note, proving the cached prefix was not disturbed
- [ ] The note is trimmed on the way in; whitespace-only becomes no note
- [ ] An over-long note is truncated rather than rejected, and the run still completes
- [ ] The note is stored on the run and survives a restart
- [ ] The run's page shows the note in its own panel above the summary, and shows no panel when there is none
- [ ] The downloaded document carries the note in its front matter as a block scalar, so a multi-line note survives the round trip
- [ ] A database created before the column existed gains it on startup, and its existing rows read back with no note
- [ ] Nothing searches, lists, or filters on the note
