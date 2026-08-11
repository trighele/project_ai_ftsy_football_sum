// Exploring the player reference: sorting, filtering, and searching it.
//
// The whole reference is already in the page, so none of this asks the server
// for anything. Every value a control reads is an attribute the server wrote on
// the row — nothing here parses a cell, and nothing keeps a copy of the table.
//
// Listeners are delegated from the document rather than bound to the controls,
// because **Sync now** replaces the whole section with a freshly rendered one:
// delegation means the new markup works without being wired up again.
(() => {
  "use strict";

  // The order the server sent the rows in, so that "Clear" can put them back
  // and every sort breaks its ties the same way. Held against the table
  // element rather than in a variable so that the table **Sync now** swaps in —
  // a different element, with different rows — starts with neither.
  const originalOrder = new WeakMap();
  // Which column the table is currently sorted by, and which way.
  const sortState = new WeakMap();

  // `input` covers all three controls — a checkbox and a select both fire it —
  // so the table narrows as a name is typed and the moment a box is ticked.
  document.addEventListener("input", (event) => {
    if (event.target.closest("[data-player-filters]")) apply();
  });

  document.addEventListener("click", (event) => {
    const header = event.target.closest("[data-player-sort]");
    if (header) {
      sortBy(header);
      return;
    }
    if (event.target.closest("[data-player-reset]")) reset();
  });

  function table() {
    return document.querySelector("[data-player-table]");
  }

  function rows(element) {
    return Array.from(element.querySelectorAll("[data-player-row]"));
  }

  // The rows as the server ordered them: team, position, depth rank, name.
  // Sorting always starts from here, so ties keep that order rather than the
  // order left behind by whichever column was sorted last.
  function asServed(element) {
    if (!originalOrder.has(element)) originalOrder.set(element, rows(element));
    return originalOrder.get(element);
  }

  // The row is the record: every value a control reads is an attribute the
  // server wrote on the `<tr>`, under the same key the column heading names.
  // `null` means the reference has no such value for that player.
  function value(row, key) {
    return row.getAttribute(`data-${key}`);
  }

  function checkedValues(facet) {
    const boxes = document.querySelectorAll(
      `[data-player-filter="${facet}"]:checked`,
    );
    return new Set(Array.from(boxes, (box) => box.value));
  }

  // Show the rows that pass every filter at once. An empty filter is not a
  // filter: filters narrow each other, they do not replace each other.
  function apply() {
    const element = table();
    if (!element) return;

    const search = document.querySelector("[data-player-search]");
    const cutoff = document.querySelector("[data-player-depth]");
    const narrowing = {
      query: search.value.trim().toLowerCase(),
      teams: checkedValues("team"),
      positions: checkedValues("position"),
      depth: Number(cutoff.value),
    };

    let shown = 0;
    for (const row of rows(element)) {
      const visible = matches(row, narrowing);
      row.hidden = !visible;
      if (visible) shown += 1;
    }

    document.querySelector("[data-player-shown]").textContent = String(shown);
    element.querySelector("[data-player-empty]").hidden = shown > 0;
  }

  function matches(row, { query, teams, positions, depth }) {
    const depthRank = value(row, "depth-rank");
    return (
      (!query || value(row, "player-name").includes(query)) &&
      (!teams.size || teams.has(value(row, "team"))) &&
      (!positions.size || positions.has(value(row, "position"))) &&
      // A player with no depth rank is below any cutoff, not above every one.
      (!depth || (depthRank !== null && Number(depthRank) <= depth))
    );
  }

  // Sort by this column, reversing if it is already the one being sorted by.
  function sortBy(header) {
    const element = table();
    if (!element) return;

    const column = header.dataset.playerSort;
    const numeric = header.hasAttribute("data-player-sort-numeric");
    const current = sortState.get(element);
    const descending = Boolean(
      current && current.column === column && !current.descending,
    );
    sortState.set(element, { column, descending });

    const ordered = asServed(element).slice();
    ordered.sort(comparing(column, numeric, descending));
    reorder(element, ordered);

    unmarkSorting(element);
    const cell = header.closest("th");
    cell.setAttribute("aria-sort", descending ? "descending" : "ascending");
    cell.querySelector("[data-player-arrow]").textContent = descending
      ? "↓"
      : "↑";
  }

  // Put the rows in this order, ahead of the row that says nothing matched.
  function reorder(element, ordered) {
    const moved = document.createDocumentFragment();
    for (const row of ordered) moved.append(row);
    element.querySelector("tbody").prepend(moved);
  }

  // No column is the sorted one. Said in the table for a screen reader and in
  // the heading for everyone else.
  function unmarkSorting(element) {
    for (const cell of element.querySelectorAll("th[aria-sort]")) {
      cell.setAttribute("aria-sort", "none");
      cell.querySelector("[data-player-arrow]").textContent = "↕";
    }
  }

  function comparing(key, numeric, descending) {
    return (left, right) => {
      const first = value(left, key);
      const second = value(right, key);
      // A missing value goes last whichever way the column is sorted: it is
      // not a low rank, it is the absence of one.
      if (first === null || second === null) {
        if (first === second) return 0;
        return first === null ? 1 : -1;
      }
      const order = numeric
        ? Number(first) - Number(second)
        : first.localeCompare(second);
      return descending ? -order : order;
    };
  }

  // Back to the whole reference in the order it arrived in.
  function reset() {
    const element = table();
    if (!element) return;

    document.querySelector("[data-player-search]").value = "";
    document.querySelector("[data-player-depth]").value = "";
    for (const box of document.querySelectorAll("[data-player-filter]")) {
      box.checked = false;
    }

    sortState.delete(element);
    reorder(element, asServed(element));
    unmarkSorting(element);
    apply();
  }

  // A browser that restores the controls from before a reload restores them
  // ticked, so the table has to be narrowed to match before it is looked at.
  apply();
})();
