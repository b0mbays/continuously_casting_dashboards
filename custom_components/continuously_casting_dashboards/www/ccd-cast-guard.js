/* Generic cold-load custom-card recovery for Continuously Casting Dashboards.
 *
 * Served as a Home Assistant extra JavaScript module. It is deliberately inert
 * on normal browser dashboards. Only CCD-cast URLs with the explicit opt-in
 * query parameter are eligible for a SINGLE bounded page reload.
 *
 * A reload can recover HA's known custom-card resource/registration races in
 * which the view permanently displays hui-error-card after a cold load.
 * It cannot fix a genuinely invalid card configuration or missing resource.
 */
(() => {
  "use strict";

  const PARAMETER = "ccd_cast_guard";
  const STORAGE_PREFIX = "ccd_custom_card_recovery_";
  const RETRY_COOLDOWN_MS = 15 * 60 * 1000;
  const CHECK_DELAYS_MS = [6000, 14000, 24000, 36000];
  const MAX_NODES = 4000;

  // This is a passive module on other browsers or dashboards; no event
  // handlers, timers, or storage mutations should occur without opt-in.
  const query = new URLSearchParams(window.location.search);
  if (query.get(PARAMETER) !== "1") return;

  function errorCardPresent(root) {
    // Custom cards can sit inside arbitrary shadow roots. Keep traversal
    // bounded to prevent expensive work on large Lovelace dashboards.
    const pending = [root];
    let inspected = 0;

    while (pending.length && inspected < MAX_NODES) {
      const node = pending.pop();
      inspected += 1;
      if (!node) continue;

      if (node.tagName?.toLowerCase() === "hui-error-card") {
        return true;
      }
      if (node.shadowRoot) pending.push(node.shadowRoot);
      if (node.children) {
        for (let i = node.children.length - 1; i >= 0; i -= 1) {
          pending.push(node.children[i]);
        }
      }
    }
    return false;
  }

  function storageKey() {
    // Store no dashboard URL, token or query string, even in session storage.
    // A small deterministic hash identifies this location during one session.
    const identity = window.location.pathname + window.location.search;
    let hash = 2166136261;
    for (let i = 0; i < identity.length; i += 1) {
      hash ^= identity.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return STORAGE_PREFIX + (hash >>> 0).toString(16);
  }

  const key = storageKey();
  let errorObservations = 0;
  let complete = false;

  function check() {
    if (complete || !document.documentElement) return;
    const foundError = errorCardPresent(document.documentElement);
    if (!foundError) {
      errorObservations = 0;
      return;
    }
    errorObservations += 1;
    // Require two separate checks rather than reloading for transient errors.
    if (errorObservations < 2) return;

    // Storage must be writable. Fail closed when the browser disallows it:
    // reloading without a persisted guard can create an infinite loop.
    try {
      const previous = window.sessionStorage.getItem(key);
      if (previous !== null) {
        const age = Date.now() - Number(previous);
        if (Number.isFinite(age) && age >= 0 && age < RETRY_COOLDOWN_MS) {
          complete = true;
          return;
        }
      }
      window.sessionStorage.setItem(key, String(Date.now()));
    } catch (_error) {
      complete = true;
      console.warn("[CCD] Card recovery skipped: session storage unavailable");
      return;
    }

    complete = true;
    console.warn("[CCD] Persistent custom-card error: trying one guarded dashboard reload");
    // Mark the query flag as consumed *before* navigating. If the Cast
    // receiver drops sessionStorage during navigation, the new page still
    // cannot trigger another reload from this recovery attempt.
    const next = new URL(window.location.href);
    next.searchParams.set(PARAMETER, "done");
    window.location.replace(next.toString());
  }

  // Never hook customElements.define(), monkeypatch Home Assistant internals,
  // or alter user audio/media. Only an already-loaded CCD dashboard is checked.
  for (const delay of CHECK_DELAYS_MS) {
    window.setTimeout(check, delay);
  }
})();
