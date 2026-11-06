import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {join, dirname} from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const script = readFileSync(join(
  dirname(fileURLToPath(import.meta.url)),
  "..", "custom_components", "continuously_casting_dashboards",
  "www", "ccd-cast-guard.js"
), "utf8");

function element(tagName, children = [], shadowRoot = null) {
  return {tagName, children, shadowRoot};
}

function dashboard(withError) {
  const nested = element("HUI-VIEW", [], {
    children: withError ? [element("HUI-ERROR-CARD")] : [element("HUI-ENTITY-CARD")],
  });
  return element("HTML", [element("BODY", [nested])]);
}

function runGuard({
  search = "?ccd_cast_guard=1",
  root = dashboard(false),
  storage = new Map(),
  currentTime = 100_000,
  blockStorage = false,
  hassAvailable = true,
} = {}) {
  const callbacks = [];
  const warnings = [];
  const result = {
    reloads: 0, lastUrl: null, callbacks, warnings, storage, root,
    reports: [], errorHandlers: [],
  };
  const sessionStorage = {
    getItem(key) {
      if (blockStorage) throw new Error("storage denied");
      return storage.get(key) ?? null;
    },
    setItem(key, value) {
      if (blockStorage) throw new Error("storage denied");
      storage.set(key, value);
    },
  };
  const window = {
    location: {
      href: "https://ha.example/dashboard-test/kiosk" + search,
      pathname: "/dashboard-test/kiosk",
      search,
      replace(url) {
        result.reloads += 1;
        result.lastUrl = url;
      },
    },
    setTimeout(fn, delay) { callbacks.push({fn, delay}); },
    sessionStorage,
    addEventListener() {},
    customCards: [
      {type: "example-custom-card"}, {type: "missing-custom-card"}
    ],
    performance: {
      getEntriesByType: () => [
        {initiatorType: "script"}, {initiatorType: "link"}
      ],
    },
  };
  const hass = hassAvailable ? {
    callService(_domain, _service, payload) {
      result.reports.push(payload);
      return Promise.resolve();
    },
  } : null;
  const document = {
    documentElement: root,
    readyState: "complete",
    querySelector: () => hass ? {hass} : null,
    addEventListener(name, handler) {
      result.errorHandlers.push({name, handler});
    },
  };
  class FakeDate extends Date {
    static now() { return currentTime; }
  }
  vm.runInNewContext(script, {
    window, document, customElements: {
      get: tag => tag === "example-custom-card" ? class {} : undefined,
    },
    URL, URLSearchParams, Date: FakeDate, Math,
    console: {warn: msg => warnings.push(msg)},
  });
  return result;
}

test("unflagged dashboard does not schedule a check or reload", () => {
  const r = runGuard({search: "", root: dashboard(true)});
  assert.equal(r.callbacks.length, 0);
  assert.equal(r.reloads, 0);
  assert.equal(r.storage.size, 0);
});

test("clean dashboard never reloads or touches storage", () => {
  const r = runGuard({root: dashboard(false)});
  assert.equal(r.callbacks.length, 4);
  for (const check of r.callbacks) check.fn();
  assert.equal(r.reloads, 0);
  assert.equal(r.storage.size, 0);
});

test("persistent error behind shadow roots triggers only one soft reload", () => {
  const r = runGuard({root: dashboard(true)});
  assert.deepEqual(r.callbacks.map(c => c.delay), [6000, 14000, 24000, 36000]);
  r.callbacks[0].fn();
  assert.equal(r.reloads, 0, "single transient failure is not enough");
  r.callbacks[1].fn();
  assert.equal(r.reloads, 1, "second error observation permits one reload");
  r.callbacks[2].fn();
  r.callbacks[3].fn();
  assert.equal(r.reloads, 1);
  assert.equal(r.storage.size, 1);
  const reloaded = new URL(r.lastUrl);
  assert.equal(reloaded.searchParams.get("ccd_cast_guard"), "done");
  assert.equal(reloaded.pathname, "/dashboard-test/kiosk");
});

test("error must remain visible across two checks", () => {
  const r = runGuard({root: dashboard(true)});
  r.callbacks[0].fn();
  r.root.children[0].children[0].shadowRoot.children = [element("HUI-ENTITY-CARD")];
  r.callbacks[1].fn();
  assert.equal(r.reloads, 0);
  r.root.children[0].children[0].shadowRoot.children = [element("HUI-ERROR-CARD")];
  r.callbacks[2].fn();
  assert.equal(r.reloads, 0);
  r.callbacks[3].fn();
  assert.equal(r.reloads, 1);
});

test("reload is throttled across browser reloads within cooldown", () => {
  const sharedStorage = new Map();
  const first = runGuard({root: dashboard(true), storage: sharedStorage});
  first.callbacks[0].fn();
  first.callbacks[1].fn();
  assert.equal(first.reloads, 1);

  const second = runGuard({
    root: dashboard(true),
    storage: sharedStorage,
    currentTime: 100_050,
  });
  for (const check of second.callbacks) check.fn();
  assert.equal(second.reloads, 0, "same receiver cannot reload in a loop");
  const exhausted = runGuard({
    search: "?ccd_cast_guard=done",
    root: dashboard(true),
    storage: new Map(),
  });
  assert.equal(exhausted.callbacks.length, 0, "spent query flag also prevents loops");
});

test("storage denial fails closed: never reload without a persistent guard", () => {
  const r = runGuard({root: dashboard(true), blockStorage: true});
  for (const check of r.callbacks) check.fn();
  assert.equal(r.reloads, 0);
  assert.match(r.warnings.join(" "), /storage unavailable/);
});

test("different or disabled query flags cannot enable recovery", () => {
  for (const search of ["?ccd_cast_guard=0", "?other=1", ""]) {
    const r = runGuard({search, root: dashboard(true)});
    assert.equal(r.callbacks.length, 0);
    assert.equal(r.reloads, 0);
  }
});

test("opted-in browser reports startup, error cards, and registry/resource counts", () => {
  const r = runGuard({
    search: "?ccd_cast_guard=1&ccd_cast_target=0123456789abcdef",
    root: dashboard(true),
  });
  assert.equal(r.callbacks.length, 9);
  assert.equal(r.errorHandlers.length, 1);
  const reportTime = r.callbacks.find(item => item.delay === 1500);
  reportTime.fn();
  assert.equal(r.reports.length, 1);
  assert.equal(r.reports[0].phase, "observing");
  assert.equal(r.reports[0].dashboard_path, "/dashboard-test/kiosk");
  assert.equal(r.reports[0].metrics.error_cards, 1);
  assert.equal(r.reports[0].metrics.script_resources, 2);
  assert.equal(r.reports[0].metrics.registered_custom_cards, 1);
  assert.equal(r.reports[0].metrics.listed_custom_cards, 2);
  assert.equal(r.reports[0].cast_target, "0123456789abcdef");
  assert.equal(JSON.stringify(r.reports).includes("https://"), false);
});

test("browser reports script load failures only as counts, never URLs", () => {
  const r = runGuard({
    search: "?ccd_cast_guard=1&ccd_cast_target=0123456789abcdef",
  });
  const error = r.errorHandlers.find(item => item.name === "error");
  error.handler({
    target: {tagName: "SCRIPT", src: "https://ha.example/private/key.js?token=secret"},
  });
  const reportTime = r.callbacks.find(item => item.delay === 1500);
  reportTime.fn();
  assert.equal(r.reports[0].metrics.resource_errors, 1);
  assert.equal(JSON.stringify(r.reports).includes("secret"), false);
  assert.equal(JSON.stringify(r.reports).includes("/private/"), false);
});

test("spent recovery URL continues reporting without triggering another reload", () => {
  const r = runGuard({
    search: "?ccd_cast_guard=done&ccd_cast_target=0123456789abcdef",
    root: dashboard(true),
  });
  assert.equal(r.callbacks.length, 5);
  for (const item of r.callbacks) item.fn();
  assert.equal(r.reloads, 0);
  assert.equal(r.reports.length, 5);
  assert.ok(r.reports.every(report => report.phase === "after_reload"));
});

test("frontend with no HA authenticated hass cannot send reports or make raw fetch", () => {
  const r = runGuard({
    search: "?ccd_cast_guard=1&ccd_cast_target=0123456789abcdef",
    hassAvailable: false,
  });
  for (const reportTime of r.callbacks.filter(item => item.delay === 1500)) {
    reportTime.fn();
  }
  assert.equal(r.reports.length, 0);
});
