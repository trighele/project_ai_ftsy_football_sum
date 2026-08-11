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

  // The order the server sent the rows in, per table, so that "Clear" can put
  // them back and every sort breaks its ties the same way.
  const originalOrder = new WeakMap();
  // Which column each table is currently sorted by, and which way.
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

  function control(selector) {
    return document.querySelector(selector);
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

    const search = control("[data-player-search]");
    const depthControl = control("[data-player-depth]");
    const query = search ? search.value.trim().toLowerCase() : "";
    const teams = checkedValues("team");
    const positions = checkedValues("position");
    const depth = depthControl ? Number(depthControl.value) : 0;

    let shown = 0;
    for (const row of rows(element)) {
      const visible = matches(row, { query, teams, positions, depth });
      row.hidden = !visible;
      if (visible) shown += 1;
    }

    const count = control("[data-player-shown]");
    if (count) count.textContent = String(shown);
    const empty = element.querySelector("[data-player-empty]");
    if (empty) empty.hidden = shown > 0;
  }

  function matches(row, { query, teams, positions, depth }) {
    const depthRank = Number(row.getAttribute("data-depth-rank"));
    return (
      (!query || row.dataset.playerName.includes(query)) &&
      (!teams.size || teams.has(row.getAttribute("data-team"))) &&
      (!positions.size || positions.has(row.getAttribute("data-position"))) &&
      // A player with no depth rank is below any cutoff, not above every one.
      (!depth || (row.hasAttribute("data-depth-rank") && depthRank <= depth))
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
    ordered.sort(comparing(`data-${column}`, numeric, descending));
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

  function comparing(attribute, numeric, descending) {
    return (left, right) => {
      const first = left.getAttribute(attribute);
      const second = right.getAttribute(attribute);
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

    const search = control("[data-player-search]");
    if (search) search.value = "";
    const depth = control("[data-player-depth]");
    if (depth) depth.value = "";
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
