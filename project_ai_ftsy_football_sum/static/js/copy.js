// Putting a summary on the clipboard as the Markdown it was written in.
//
// The document is built on the server already — the download hands it over —
// so this asks for that URL and copies the response rather than rebuilding the
// front matter here. Nothing else can then disagree with the file.
//
// The document is fetched **before** the click that asks for it, which is the
// whole shape of this file. `navigator.clipboard` is a secure-context feature
// and is simply absent over plain HTTP, which is how this application is
// deployed, so the fallback is the old select-and-execCommand dance — and that
// only works inside the user gesture that asked for it. A fetch awaited on the
// click spends that gesture, so a button written the obvious way would copy in
// development, over HTTPS, and silently fail on the deployed box. Instead each
// control's document is fetched the moment its URL is known, and the copy
// itself is synchronous: no `await` stands between the click and the clipboard.
//
// Listeners are delegated from the document rather than bound to the button,
// because on a live run the button is inside markup the server swaps in after
// this file has run, and its URL is not known until the run ends.
(() => {
  "use strict";

  // Long enough to read, short enough that the button is ready again before
  // somebody presses it a second time.
  const CONFIRMATION_MS = 1600;

  // What each control will hand over, by the element that hands it over. The
  // text is kept beside the request that is fetching it, because the fallback
  // may only use a document that has already arrived.
  const documents = new WeakMap();

  // A control that arrives with the page is primed now. One that gains its URL
  // later says so itself: `run.js` fires this when a finished run fills its
  // buttons in.
  document.addEventListener("copy-url-set", (event) => prime(event.target));
  for (const control of document.querySelectorAll("[data-copy-url]")) {
    prime(control);
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-copy-url]");
    if (button) copy(button);
  });

  function prime(control) {
    if (!control || !control.dataset.copyUrl || documents.has(control)) return;
    const held = {};
    held.arriving = fetch(control.dataset.copyUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((text) => (held.text = text));
    // A document nobody has asked for yet has nobody to report a failure to.
    // The click reports it; this only stops the browser calling it unhandled.
    held.arriving.catch(() => {});
    documents.set(control, held);
  }

  function copy(button) {
    const label = button.querySelector("[data-copy-label]") || button;
    prime(button); // Nothing has asked for this one yet. Ask now.
    const held = documents.get(button);

    // Waiting is allowed here, so a click that beat the document still works.
    if (window.isSecureContext && navigator.clipboard) {
      held.arriving
        .then((text) => navigator.clipboard.writeText(text))
        .then(() => say(label, "Copied"))
        .catch(() => say(label, "Copy failed"));
      return;
    }

    // And not here: the gesture is spent the moment this returns, so a
    // document still in flight is one this click cannot copy. Saying so beats
    // a button that reports success and leaves the clipboard as it was.
    if (held.text === undefined) {
      say(label, "Copy failed");
      return;
    }
    say(label, legacyCopy(held.text) ? "Copied" : "Copy failed");
  }

  // Selecting text and asking the document to copy it: deprecated everywhere,
  // and the only thing that works outside a secure context.
  function legacyCopy(text) {
    const field = document.createElement("textarea");
    field.value = text;
    // Off-screen rather than hidden: a field the browser considers invisible
    // cannot be selected, and an unselected field cannot be copied from.
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.top = "-1000px";
    document.body.append(field);
    field.select();
    try {
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      field.remove();
    }
  }

  // Say what happened on the button itself, and put it back afterwards. The
  // original wording is read off the element rather than written down here, so
  // there is one place the button is named.
  function say(label, said) {
    if (label.dataset.copyRestore === undefined) {
      label.dataset.copyRestore = label.textContent;
    }
    label.textContent = said;
    clearTimeout(Number(label.dataset.copyTimer));
    label.dataset.copyTimer = setTimeout(() => {
      label.textContent = label.dataset.copyRestore;
    }, CONFIRMATION_MS);
  }
})();
