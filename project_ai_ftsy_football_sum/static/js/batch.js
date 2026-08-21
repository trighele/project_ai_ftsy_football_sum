// Starting a batch and following its queue to the end.
//
// The same arrangement as `run.js` — submit, then read an event stream until
// its one terminal event — over a different protocol, because a batch reports
// state rather than prose. Every piece of markup involved is rendered by the
// server: each event carries the row it re-rendered, and this file decides
// only which row it replaces.
(() => {
  "use strict";

  const form = document.querySelector("[data-batch-form]");
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
      follow(target.querySelector("[data-batch-events]"));
    } catch (error) {
      button.disabled = false;
      throw error;
    }
  });

  // Read one batch's event stream until it ends. Every stream ends: the server
  // sends `batch-done` or `batch-failed` and closes, so `onerror` here means
  // the batch was lost rather than that it is worth reconnecting for.
  function follow(panel) {
    const status = panel.querySelector("[data-batch-status]");
    const failure = panel.querySelector("[data-batch-failure]");
    const events = new EventSource(panel.dataset.batchEvents);

    const finish = () => {
      events.close();
      button.disabled = false;
      // Whichever way the batch ended, the episodes that got through are
      // ordinary saved runs and the list below is out of date — a batch that
      // died halfway still summarized the ones before it. The list knows how
      // to fetch itself again.
      document.dispatchEvent(new CustomEvent("recent-runs-stale"));
    };

    // One row changed. It arrives whole and replaces the one at its position,
    // which is why the position rather than the URL is what identifies it:
    // the row is re-rendered, so nothing in it is safe to match on.
    events.addEventListener("batch-episode", (event) => {
      const row = JSON.parse(event.data);
      const existing = panel.querySelector(`[data-batch-row="${row.position}"]`);
      if (existing) existing.outerHTML = row.html;
    });

    events.addEventListener("batch-done", (event) => {
      status.textContent = JSON.parse(event.data).label;
      finish();
    });

    // The batch itself stopped. The rows it managed stay where they are: the
    // episodes already summarized are saved runs and still worth opening.
    events.addEventListener("batch-failed", (event) => {
      failure.innerHTML = JSON.parse(event.data).html;
      status.hidden = true;
      finish();
    });

    events.onerror = () => {
      status.textContent = "Lost contact with this batch.";
      finish();
    };
  }
})();
