/* Optional Home Assistant Lovelace control card for Continuously Casting Dashboards.
 *
 * The card uses only existing Home Assistant state and service APIs.
 * No credentials, URLs or integration state are sent to a third party.
 */

const CCD_DOMAIN = "continuously_casting_dashboards";

class CcdControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._statusNodes = [];
    this._actions = [];
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.devices) || !config.devices.length) {
      throw new Error("CCD Control Panel requires a nonempty devices list");
    }
    const devices = config.devices.map((device) => {
      if (!device || typeof device.name !== "string" || !device.name.trim()) {
        throw new Error("Each CCD device requires its exact configured name");
      }
      if (typeof device.entity !== "string" || !device.entity.startsWith("sensor.")) {
        throw new Error("Each CCD device requires its HA status sensor entity ID");
      }
      const dashboards = Array.isArray(device.dashboards)
        ? device.dashboards.filter((label) => typeof label === "string").slice(0, 50)
        : [];
      return { name: device.name.trim(), entity: device.entity, dashboards };
    });
    this._config = {
      title: typeof config.title === "string" ? config.title : "Cast Dashboard Control",
      devices,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateStatus();
  }

  connectedCallback() {
    if (this._config && !this.shadowRoot.firstChild) this._render();
  }

  getCardSize() {
    return Math.max(2, this._config?.devices.length * 3 || 2);
  }

  _element(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  _actionButton(label, service, dataFactory, resultNode) {
    const button = this._element("button", "action", label);
    button.type = "button";
    button.addEventListener("click", async () => {
      if (!this._hass?.callService || button.disabled) return;
      button.disabled = true;
      resultNode.textContent = `Requesting ${label.toLowerCase()}…`;
      try {
        await this._hass.callService(CCD_DOMAIN, service, dataFactory());
        resultNode.textContent = "Action submitted to Home Assistant";
      } catch (error) {
        resultNode.textContent = `Action failed: ${error?.message || "unknown error"}`;
      } finally {
        button.disabled = false;
      }
    });
    this._actions.push(button);
    return button;
  }

  _render() {
    const root = this.shadowRoot;
    root.replaceChildren();
    this._statusNodes = [];
    this._actions = [];

    const style = this._element("style");
    style.textContent = `
      :host { display:block; color:var(--primary-text-color); }
      ha-card { padding:16px; }
      h2 { font-size:17px; margin:0 0 16px; line-height:1.4; }
      .device { border:1px solid var(--divider-color, #8885); padding:12px;
        border-radius:12px; margin-bottom:12px; display:grid; gap:8px; }
      .device:last-child { margin-bottom:0; }
      .heading { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
      .name { font-size:15px; font-weight:600; }
      .state { border-radius:16px; font-size:12px; padding:3px 9px;
        background:var(--secondary-background-color, #8882); }
      .meta { color:var(--secondary-text-color, #777); font-size:12px;
        overflow-wrap:anywhere; }
      .actions { display:flex; gap:7px; flex-wrap:wrap; align-items:center; }
      button { appearance:none; padding:7px 11px; border:1px solid
        var(--divider-color,#8885); border-radius:10px; background:
        var(--card-background-color,#222); color:var(--primary-text-color);
        font:inherit; font-size:12px; cursor:pointer; }
      button:hover { border-color:var(--primary-color,#03a9f4); }
      button:disabled { opacity:.5; cursor:wait; }
      select, input { color:var(--primary-text-color); background:
        var(--card-background-color,#222); border:1px solid var(--divider-color,#8885);
        border-radius:8px; font:inherit; font-size:12px; padding:6px; }
      input { width:85px; }
      .message { font-size:11px; color:var(--secondary-text-color,#777); min-height:1em; }
      label { display:flex; align-items:center; gap:5px; font-size:12px; }
    `;
    root.appendChild(style);

    const card = this._element("ha-card");
    card.appendChild(this._element("h2", "", this._config.title));

    for (const device of this._config.devices) {
      const section = this._element("section", "device");
      const heading = this._element("div", "heading");
      heading.appendChild(this._element("span", "name", device.name));
      const state = this._element("span", "state", "unknown");
      heading.appendChild(state);
      section.appendChild(heading);

      const dashboard = this._element("div", "meta", "Dashboard: unknown");
      const details = this._element("div", "meta", "Waiting for Home Assistant");
      const result = this._element("div", "message");
      result.setAttribute("role", "status");
      result.setAttribute("aria-live", "polite");

      section.appendChild(dashboard);
      section.appendChild(details);

      const actions = this._element("div", "actions");
      const data = () => ({ device_name: device.name });
      actions.appendChild(this._actionButton(
        "Resume/check", "resume_casting", data, result
      ));
      actions.appendChild(this._actionButton(
        "Pause", "pause_casting", () => ({
          device_name: device.name, duration_seconds: 0
        }), result
      ));
      actions.appendChild(this._actionButton(
        "Stop once", "stop_casting", data, result
      ));

      const durationLabel = this._element("label", "", "Pause for");
      const duration = this._element("select");
      for (const [label, seconds] of [
        ["15 min", 900], ["1 hour", 3600], ["4 hours", 14400]
      ]) {
        const option = this._element("option", "", label);
        option.value = String(seconds);
        duration.appendChild(option);
      }
      durationLabel.appendChild(duration);
      actions.appendChild(durationLabel);
      actions.appendChild(this._actionButton(
        "Timed pause", "pause_casting", () => ({
          device_name: device.name, duration_seconds: Number(duration.value)
        }), result
      ));

      if (device.dashboards.length) {
        const dashboardSelect = this._element("select");
        dashboardSelect.setAttribute("aria-label", `Dashboard for ${device.name}`);
        device.dashboards.forEach((name, index) => {
          const opt = this._element("option", "", name);
          opt.value = String(index);
          dashboardSelect.appendChild(opt);
        });
        const overrideMinutes = this._element("select");
        overrideMinutes.setAttribute("aria-label", `Override duration for ${device.name}`);
        for (const [label, seconds] of [["5 min", 300], ["15 min", 900], ["1 hour", 3600]]) {
          const opt = this._element("option", "", label);
          opt.value = String(seconds);
          overrideMinutes.appendChild(opt);
        }
        actions.appendChild(dashboardSelect);
        actions.appendChild(overrideMinutes);
        actions.appendChild(this._actionButton(
          "Show temporarily", "select_dashboard", () => ({
            device_name: device.name,
            dashboard_index: Number(dashboardSelect.value),
            duration_seconds: Number(overrideMinutes.value),
          }), result
        ));
        actions.appendChild(this._actionButton(
          "Auto selection", "clear_dashboard_override", data, result
        ));
      }

      section.appendChild(actions);
      section.appendChild(result);
      card.appendChild(section);
      this._statusNodes.push({ device, state, dashboard, details });
    }
    root.appendChild(card);
    this._updateStatus();
  }

  _updateStatus() {
    if (!this._hass || !this._statusNodes.length) return;
    for (const { device, state, dashboard, details } of this._statusNodes) {
      const entity = this._hass.states?.[device.entity];
      const attr = entity?.attributes || {};
      state.textContent = entity?.state || "unavailable";
      let current = attr.current_dashboard;
      if (typeof current === "string" && current) {
        try {
          current = new URL(current, location.origin).pathname;
        } catch (_error) {
          current = "unknown";
        }
      } else {
        current = "none";
      }
      dashboard.textContent = `Dashboard: ${current}`;
      const chunks = [
        `Reconnects: ${Number(attr.reconnect_attempts) || 0}`,
        `Retry in: ${Number(attr.retry_in_seconds) || 0}s`,
        `Frontend: ${attr.frontend_readiness || "disabled"}`,
      ];
      if (attr.last_error) chunks.push(`Last error: ${String(attr.last_error)}`);
      details.textContent = chunks.join("  ·  ");
    }
  }
}

if (!customElements.get("ccd-control-panel")) {
  customElements.define("ccd-control-panel", CcdControlPanel);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((item) => item.type === "ccd-control-panel")) {
  window.customCards.push({
    type: "ccd-control-panel",
    name: "CCD Control Panel",
    description: "Control Cast dashboards, pauses and temporary overrides",
  });
}
