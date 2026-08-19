---
title: Let a single episode carry a context note into its summary
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

Every episode is summarized the same way. A reader who wants a particular episode read with something specific in mind — a roster to weigh it against, a position group they are deciding on, a name they want tracked — has no way to say so. The only lever is the system prompt, which is shared by every run, cached, and not something to edit per episode.

## Solution

The single-episode form gains an optional note: a few sentences saying what this summary should pay attention to. The note travels with the episode into the summary request, is saved with the run, is shown when the run is reopened, and appears in the Markdown the run is downloaded or copied as — because what was asked for shaped what came back, and a file that hides that is misleading a month later.

A **context note** belongs to one episode. Episodes submitted as a batch have none.

## User Stories

1. As a reader, I want to add a note to a single episode before summarizing it, so that I can say what I want the summary to pay attention to.
2. As a reader, I want the note to be optional, so that the ordinary case stays a URL and one button.
3. As a reader, I want an empty or whitespace-only note treated as no note, so that an accidental space does not change the request.
4. As a reader, I want the note stored with the run, so that reopening it tells me what I asked for.
5. As a reader, I want the note shown on the run's page, so that I can judge the summary against the instruction that produced it.
6. As a reader, I want the note in the downloaded Markdown, so that a file I paste elsewhere still records what shaped it.
7. As a reader, I want the note in the copied Markdown too, so that copying and downloading do not disagree.
8. As a reader, I want a run without a note to look exactly as it does today, so that nothing gains an empty field for the sake of consistency.
9. As a reader, I want the note to sit next to the transcript in what the model reads, so that it is read as an instruction about this episode.
10. As a reader submitting a batch, I want no note field, so that the multi-episode form stays a list of links.
11. As a reader, I want an over-long note handled without losing my run, so that pasting a wall of text is not a failure.
12. As a maintainer, I want the note to leave the cached part of the prompt untouched, so that adding it cannot silently double the cost of every run.
13. As a maintainer, I want the new column added to an existing deployed database, so that the feature works on the live box and not only on a fresh install.
14. As a maintainer, I want the note recorded in exactly what reached the model, so that a test can prove where it landed.

## Implementation Decisions

- **The note goes in the user turn**, alongside the episode's title, upload date, and transcript — never in the system prompt. The system prompt's second block is marked for caching and must stay byte-identical between runs; a per-episode string there would invalidate the cache silently, at full price and with no error to explain it. This is the single most important decision in the feature.
- **Placement within the user turn**: after the title and upload date, before the transcript, under a short label naming it as the reader's own instruction. When there is no note, the user turn is byte-for-byte what it is today — no empty label, no blank line — so the existing prompt tests hold.
- **Storage**: a nullable text column on the runs table, added through the idempotent migration step introduced with the History ordering work. This is that pattern's first real use.
- **Trimmed on the way in**; blank becomes absent. A cap of a couple of thousand characters is enforced in the form and again on the server, where an over-long note is truncated rather than rejected: losing the tail of a note is a smaller harm than losing the run.
- **The run page shows the note** in its own labelled panel above the summary, present only when there is one.
- **The download document gains a front-matter field** when a note is present. A note can contain newlines, so it is written as a block scalar rather than an inline value — front matter that a reader or a tool can still parse.
- **The form**: a textarea on the single-episode tab only, with placeholder text that says what it is for. The batch form has no equivalent and the batch path never sets the field.
- **Nothing else reads the note.** It is not searched, not shown in History rows, and not used to decide anything — it is an input to one request and a record of that request.

## Testing Decisions

A good test here asserts what reached the model and what came back out of storage, not how the string was assembled on the way.

- **Through the HTTP seam with the recording Claude fake**, which already captures the whole request: a run started with a note has it in the user turn, in the stated position; a run started without one produces a user turn identical to today's; the system blocks are byte-identical in both cases, which is what proves the cache prefix was not disturbed.
- **Through the HTTP seam for persistence**: a run with a note reopens showing it; a run without one shows no panel; the downloaded document carries the note in its front matter, and a multi-line note survives the round trip.
- **Directly against the store**: the column is added to a database created before it existed, and rows written before the migration read back with no note rather than failing.
- **Truncation**: an over-long note is stored and sent truncated, and the run still completes.
- **Prior art**: the existing prompt test, which asserts on the recorded request byte for byte, and the existing saved-run tests for storage and download.

## Out of Scope

- Notes on batch episodes.
- Editing a note after a run, or re-running an episode with a different one.
- Saved or reusable notes, templates, or defaults.
- Searching History by note text.
- Any change to the system prompt, the output contract, or the player reference block.

## Further Notes

"Context note" is the name everywhere — the label on the form, the field on the run, the column, and the front-matter key. The player reference is also context handed to the model, and is never called that; keeping the name pinned to the reader's own addition is what stops the two blurring.
