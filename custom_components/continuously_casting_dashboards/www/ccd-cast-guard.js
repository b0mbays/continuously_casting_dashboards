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
  const guardMode = query.get(PARAMETER);
  if (guardMode !== "1" && guardMode !== "done") return;

  // A short hash of the configured Cast IP associates browser reports with
  // one active receiver. Never include resource URLs or console text.
  const target = query.get("ccd_cast_target");
  const canReport = /^[a-f0-9]{16}$/.test(target || "");
  const counters = {resource_errors: 0, javascript_errors: 0};
  if (canReport) {
    document.addEventListener("error", (event) => {
      const tag = event.target?.tagName?.toLowerCase();
      if (tag === "script" || tag === "link") {
        counters.resource_errors = Math.min(999, counters.resource_errors + 1);
      } else if (event.target === window) {
        counters.javascript_errors = Math.min(999, counters.javascript_errors + 1);
      }
    }, true);
    window.addEventListener?.("unhandledrejection", () => {
      counters.javascript_errors = Math.min(999, counters.javascript_errors + 1);
    });
  }

  function snapshot() {
    const registered = Array.isArray(window.customCards) ? window.customCards : [];
    const tagNames = registered
      .map(item => item && item.type)
      .filter(tag => typeof tag === "string" && /^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(tag));
    let registeredCount = 0;
    for (const tag of tagNames.slice(0, 100)) {
      if (customElements.get(tag)) registeredCount += 1;
    }
    let scriptCount = 0;
    try {
      const resources = window.performance?.getEntriesByType?.("resource") || [];
      scriptCount = resources.filter(item =>
        item.initiatorType === "script" || item.initiatorType === "link"
      ).length;
    } catch (_error) {
      // Performance entries are optional on older Cast receiver browsers.
    }
    return {
      error_cards: countErrorCards(document.documentElement),
      resource_errors: counters.resource_errors,
      javascript_errors: counters.javascript_errors,
      script_resources: Math.min(999, scriptCount),
      listed_custom_cards: Math.min(999, tagNames.length),
      registered_custom_cards: Math.min(999, registeredCount),
    };
  }

  function report(phase) {
    if (!canReport || !document.querySelector) return;
    // HA's root exposes its authenticated hass object on supported frontend
    // versions. If it isn't available, do not attempt a raw unauthenticated
    // fetch. The backend's no_report status distinguishes this condition.
    const hass = document.querySelector("home-assistant")?.hass;
    if (!hass || typeof hass.callService !== "function") return;
    try {
      const promise = hass.callService(
        "continuously_casting_dashboards",
        "report_cast_frontend",
        {
          cast_target: target,
          dashboard_path: window.location.pathname,
          phase,
          document_state: document.readyState || "unknown",
          metrics: snapshot(),
        }
      );
      Promise.resolve(promise).catch(() => {});
    } catch (_error) {
      // This diagnostic path must never interrupt the Lovelace receiver.
    }
  }

  if (canReport) {
    for (const delay of [1500, 9000, 20000, 40000, 65000]) {
      window.setTimeout(
        () => report(guardMode === "done" ? "after_reload" : "observing"),
        delay
      );
    }
  }
  if (guardMode === "done") return;

  function countErrorCards(root) {
    // Traverse bounded shadow DOM to count Lovelace errors. This captures
    // symptoms, not private error text or potentially sensitive card config.
    const pending = [root];
    let inspected = 0;
    let count = 0;

    while (pending.length && inspected < MAX_NODES) {
      const node = pending.pop();
      inspected += 1;
      if (!node) continue;
      if (node.tagName?.toLowerCase() === "hui-error-card") {
        count += 1;
        if (count >= 100) return count;
      }
      if (node.shadowRoot) pending.push(node.shadowRoot);
      if (node.children) {
        for (let i = node.children.length - 1; i >= 0; i -= 1) {
          pending.push(node.children[i]);
        }
      }
    }
    return count;
  }

  function errorCardPresent(root) {
    return countErrorCards(root) > 0;
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
    report("reload_requested");
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
