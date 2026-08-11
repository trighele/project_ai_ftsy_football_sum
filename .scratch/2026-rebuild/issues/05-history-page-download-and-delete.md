# 05 — History page, download, and delete

**What to build:** A History page listing every past run, so finding an episode from weeks ago doesn't mean scrolling the home page. Each row shows the episode title, channel, upload date, and when it was summarized. A title search narrows the list. Clicking a row reopens the run with its transcript and summary. Each run can be downloaded as Markdown or deleted.

The downloaded Markdown must stand on its own — episode title and upload date included in the document, not just in the page around it.

Delete is a real deletion of the run record, and should not require a confirmation dance; the home page and History list both reflect it immediately.

**Blocked by:** 04.

**Status:** ready-for-agent

- [x] A History page lists all saved runs, most recent first.
- [x] Each row shows episode title, channel, upload date, and when the run was summarized.
- [x] Searching by title narrows the list.
- [x] Opening a run from History shows its transcript and summary.
- [x] A run's summary downloads as a Markdown file that includes the episode title and upload date.
- [x] A run can be deleted, and disappears from both History and the home page's recent list.
- [x] Navigation between Home, Players, and History works from every page.
- [x] Tests cover listing, search, reopen, download content, and delete.
