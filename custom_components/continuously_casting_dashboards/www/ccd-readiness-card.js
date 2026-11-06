/* Optional Lovelace reporter for Continuously Casting Dashboards.
 *
 * Add this file as a JavaScript module dashboard resource and a
 * custom:ccd-readiness-card to a view. It never reloads or recasts.
 */
class CcdReadinessCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._timer = null;
    this._lastReport = 0;
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config || typeof config.device_name !== "string" || !config.device_name.trim()) {
      throw new Error("CCD readiness requires a device_name");
    }
    this._config = {
      device_name: config.device_name.trim(),
      required_elements: Array.isArray(config.required_elements)
        ? config.required_elements.filter((tag) => typeof tag === "string").slice(0, 10)
        : [],
      interval_seconds: Math.max(15, Math.min(120, Number(config.interval_seconds) || 30)),
      hide: Boolean(config.hide),
    };
    this._render();
    this._start();
  }

  set hass(hass) {
    this._hass = hass;
    this._report();
  }

  connectedCallback() {
    this._start();
  }

  disconnectedCallback() {
    this._stop();
  }

  getCardSize() {
    return 1;
  }

  _start() {
    if (!this.isConnected || !this._config) return;
    this._stop();
    this._timer = setInterval(() => this._report(), this._config.interval_seconds * 1000);
    this._report();
  }

  _stop() {
    if (this._timer != null) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  async _report() {
    if (!this.isConnected || !this._config || !this._hass?.callService) return;
    const now = Date.now();
    if (now - this._lastReport < this._config.interval_seconds * 1000) return;
    this._lastReport = now;

    const missing = this._config.required_elements.filter(
      (tag) => !customElements.get(tag)
    );
    const ready = missing.length === 0;

    try {
      await this._hass.callService(
        "continuously_casting_dashboards",
        "report_dashboard_ready",
        {
          device_name: this._config.device_name,
          dashboard_path: location.pathname,
          ready,
          missing_elements: missing,
        }
      );
      this._render(ready ? "Frontend elements registered" : "Waiting for custom elements");
    } catch (error) {
      this._render("Readiness report unavailable");
      console.debug("CCD readiness reporter:", error);
    }
  }

  _render(label = "Checking frontend registration") {
    if (!this._config) return;
    if (this._config.hide) {
      this.style.display = "none";
      return;
    }
    this.style.display = "";
    this.shadowRoot.innerHTML = `<ha-card>
      <div style="padding:6px 12px;font-size:11px;opacity:.75" role="status">
        ${label.replace(/[&<>"]/g, (character) => ({
          "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
        })[character])}
      </div>
    </ha-card>`;
  }
}

if (!customElements.get("ccd-readiness-card")) {
  customElements.define("ccd-readiness-card", CcdReadinessCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "ccd-readiness-card")) {
  window.customCards.push({
    type: "ccd-readiness-card",
    name: "CCD Readiness Reporter",
    description: "Optional dashboard registration heartbeat for Chromecast diagnostics",
  });
}
