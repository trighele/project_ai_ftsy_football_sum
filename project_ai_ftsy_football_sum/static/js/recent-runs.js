// Keeping the recent-runs list current when something has just added to it.
//
// A run and a batch both finish by making this list out of date, and both say
// so the same way: they dispatch `recent-runs-stale` and the list fetches
// itself again. Here rather than in either controller, because asking the
// server for the list instead of assembling a row in the browser is the rule,
// and a rule written down twice is one that can be followed only once.
(() => {
  "use strict";

  document.addEventListener("recent-runs-stale", async () => {
    const list = document.querySelector("#recent-runs");
    if (!list) return;
    const response = await fetch("/fragments/recent-runs");
    list.outerHTML = await response.text();
  });
})();
