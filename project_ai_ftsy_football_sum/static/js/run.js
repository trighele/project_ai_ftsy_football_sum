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
    const summaryPanel = panel.querySelector("[data-run-summary-panel]");
    const summary = panel.querySelector("[data-run-summary]");
    const failure = panel.querySelector("[data-run-failure]");
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

    events.addEventListener("summary", (event) => {
      summaryPanel.classList.remove("hidden");
      // `append` rather than innerHTML: this is Claude's text, not markup.
      summary.append(JSON.parse(event.data).text);
    });

    events.addEventListener("done", (event) => {
      status.textContent = JSON.parse(event.data).label;
      refreshRecentRuns();
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

  // The run just made the recent list out of date. Ask the server for it
  // again rather than assembling a row here.
  async function refreshRecentRuns() {
    const list = document.querySelector("#recent-runs");
    if (!list) return;
    const response = await fetch("/fragments/recent-runs");
    list.outerHTML = await response.text();
  }
})();
