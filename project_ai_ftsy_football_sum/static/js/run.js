// Starting a run and following it to the end.
//
// The server owns every piece of markup involved: each event carries either a
// fragment it rendered or the text Claude just wrote. This file decides only
// where each one goes, and keeps the Summarize button disabled until the run
// is over so a second run cannot be fired on top of the first.
(() => {
  "use strict";

  const form = document.querySelector("[data-run-form]");
  if (!form) return;

  const button = form.querySelector("button[type=submit]");
  const target = document.querySelector("#episode");

  form.addEventListener("submit", async (submission) => {
    submission.preventDefault();
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
      });
      target.innerHTML = await response.text();
      follow(target.querySelector("[data-run-events]"));
    } catch (error) {
      button.disabled = false;
      throw error;
    }
  });

  // Read one run's event stream until it ends. Every stream ends: the server
  // sends `done` or `failed` and closes, so `onerror` here means the run was
  // lost rather than that it is worth reconnecting for.
  function follow(panel) {
    const status = panel.querySelector("[data-run-status]");
    const episode = panel.querySelector("[data-run-episode]");
    const warning = panel.querySelector("[data-run-warning]");
    const summaryPanel = panel.querySelector("[data-run-summary-panel]");
    const summary = panel.querySelector("[data-run-summary]");
    const failure = panel.querySelector("[data-run-failure]");
    // Every part of the summary panel the end of a run rearranges, in one
    // place: they are found together, they are only ever used together, and
    // the run is over by the time any of them is touched.
    const summaryParts = {
      actions: panel.querySelector("[data-run-summary-actions]"),
      copy: panel.querySelector("[data-run-copy]"),
      download: panel.querySelector("[data-run-download]"),
      streamed: summary,
      rendered: panel.querySelector("[data-run-summary-rendered]"),
      source: panel.querySelector("[data-run-summary-source]"),
      markdown: panel.querySelector("[data-run-summary-source] code"),
    };
    const events = new EventSource(panel.dataset.runEvents);

    const finish = () => {
      events.close();
      button.disabled = false;
    };

    events.addEventListener("stage", (event) => {
      status.textContent = JSON.parse(event.data).label;
    });

    events.addEventListener("transcript", (event) => {
      episode.innerHTML = JSON.parse(event.data).html;
    });

    // The run is going ahead on less than it wanted. It is not a failure and
    // does not close the stream, so it sits above the summary it qualifies.
    events.addEventListener("warning", (event) => {
      warning.innerHTML = JSON.parse(event.data).html;
    });

    events.addEventListener("summary", (event) => {
      summaryPanel.classList.remove("hidden");
      // `append` rather than innerHTML: this is Claude's text, not markup.
      summary.append(JSON.parse(event.data).text);
    });

    events.addEventListener("done", (event) => {
      const done = JSON.parse(event.data);
      status.textContent = done.label;
      showFinishedSummary(summaryParts, done);
      // The run just made the recent list out of date. The list knows how to
      // fetch itself again — see `recent-runs.js`.
      document.dispatchEvent(new CustomEvent("recent-runs-stale"));
      finish();
    });

    // The failure goes below whatever the run had already produced, not over
    // it: a transcript that arrived is still worth reading.
    events.addEventListener("failed", (event) => {
      failure.innerHTML = JSON.parse(event.data).html;
      status.hidden = true;
      finish();
    });

    events.onerror = () => {
      status.textContent = "Lost contact with this run.";
      finish();
    };
  }

  // The run has ended: what has been read as it was written becomes what a
  // saved run shows. The prose arrives rendered on the terminal event — the
  // browser still builds no markup — and the text that was streamed becomes
  // the source underneath it, so the disclosure holds exactly what was watched
  // rather than a second copy of it. The identifier arrives on the same event,
  // which is what lets Copy and Download point at a run that did not exist
  // when this panel was rendered.
  function showFinishedSummary(parts, done) {
    parts.markdown.textContent = parts.streamed.textContent;
    parts.rendered.innerHTML = done.summary_html;
    parts.streamed.classList.add("hidden");
    parts.rendered.classList.remove("hidden");
    parts.source.classList.remove("hidden");
    parts.download.href = done.download_href;
    parts.copy.dataset.copyUrl = done.download_href;
    parts.actions.classList.remove("hidden");
    // `copy.js` has the document in hand before the click that asks for it —
    // see the note there on why it cannot fetch one afterwards. Nothing else
    // knows a copy control has just been given a URL, so this says so.
    parts.copy.dispatchEvent(new CustomEvent("copy-url-set", { bubbles: true }));
  }
})();
