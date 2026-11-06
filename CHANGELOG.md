# Changelog

All changes here refer to the [anaschillin fork](https://github.com/anaschillin/continuously_casting_dashboards). Home Assistant integration and HACS metadata are maintained together; a merged commit or version field does **not** automatically create a tagged GitHub release or HACS download.

## 3.0.2 — Generic custom-card recovery on Cast (candidate, 6 November 2026)

- Add opt-in `recover_custom_cards` for any dashboard, independent of
  custom-card vendor or Home Assistant integration.
- Register a passive HA frontend module that is active only on CCD-cast URLs
  with `ccd_cast_guard=1`.
- Watch for persistent `hui-error-card` nodes, including nested shadow roots,
  and attempt **one** receiver-page reload, never another CATT cast.
- Prevent reload loops with a consumed URL marker, per-dashboard
  15-minute session cooldown, and fail-closed behaviour without storage.
- Add Python URL-parameter tests and JavaScript simulated-DOM recovery tests.

**Default:** disabled. This mitigates some Home Assistant custom-resource
startup races but cannot fix invalid Lovelace YAML, unavailable modules, or
all Cast receiver limitations. Physical Chromecast/Nest Hub testing remains
required before merge.

## 3.0.1 — CATT compatibility update (merged code, 6 November 2026)

- Upgrade the Home Assistant integration requirement from `catt==0.12.13` to **`catt==0.13.3`**, the latest stable version published on PyPI as of 6 November 2026 (published 24 September 2026).
- CATT 0.13.3 requires Python 3.11+ and PyChromecast `>=14.0.1,<15`. Home Assistant's current Cast integration pins PyChromecast 14.1.1, within this range.
- Add CI installation/resolution and CLI contract tests on Python 3.13 and 3.14 for `scan`, `cast_site`, `status`, `stop` and `volume`. CLI-level tests do **not** verify Cast firmware, HA runtime behaviour or actual dashboard rendering.
- Refresh README, upgrade guide, Marketplace/HACS terminology and backend compatibility review.
- Keep all existing casting options, configuration data and service contracts unchanged. No native HA Cast replacement backend is introduced.

**Upgrade precaution:** restart Home Assistant after installing updated integration code, and verify casting on a noncritical receiver before switching production screens. If CATT 0.13.3 introduces a regression, return to a known-good integration version with `catt==0.12.13` using your backup and restart HA. Do not try to manage HA's Python packages manually inside HAOS.

**Publishing:** The version `3.0.1` and CATT update are merged into `main`; verify GitHub/HACS release availability separately. Hardware validation remains open.

---

## 3.0.0 — merged code (6 November 2026)

The major version reflects a large set of configuration, casting, and Lovelace improvements implemented in [PRs #2–#6](https://github.com/anaschillin/continuously_casting_dashboards/pulls?q=is%3Apr+is%3Amerged).

### Added

- Per-dashboard scheduling and entity-state selection, with opt-in continuous casting and preserved volume ([#2](https://github.com/anaschillin/continuously_casting_dashboards/pull/2)).
- Robust Cast discovery with strict Google-suffix matching, shared scans, retry backoff, better timeout cleanup, and diagnostic health attributes ([#3](https://github.com/anaschillin/continuously_casting_dashboards/pull/3)).
- Dashboard priorities and optional rotation; temporary manual overrides through Home Assistant services ([#4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4)).
- An **optional, diagnostic-only** Lovelace frontend readiness reporter; tracks custom-element registration/heartbeat states, **not** actual browser rendering ([#5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5)).
- Optional Lovelace multi-device control panel, manual timed/indefinite pause and resume, and Home Assistant Repairs for missing CATT or ambiguous name-only Cast device configurations ([#6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).

### Fixed and changed

- Home Assistant 2026.11 `EntityCategory` import compatibility and earlier DashCast/Google TV reliability improvements.
- Default dashboard-selection order is unchanged unless priorities/rotation are configured. Higher-priority eligible dashboards take precedence.
- Improved persistence of global notification options, including saving `enable_notifications: false` ([#6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).
- Updated README, HACS repository information, migration instructions and roadmap ([#7](https://github.com/anaschillin/continuously_casting_dashboards/pull/7)).

### Compatibility and upgrade notes

1. **Back up Home Assistant** before upgrading, especially if coming from the original upstream repository or YAML configuration.
2. Use only one HACS installation source for the `continuously_casting_dashboards` integration domain. This fork's custom repository is `https://github.com/anaschillin/continuously_casting_dashboards`.
3. In the **3.0.0 code baseline**, the manifest pinned `catt==0.12.13`; the proposed **3.0.1** update changes that pin to 0.13.3 and requires separate device validation.
4. Optional UI features require registering the JavaScript resources: `/ccd_cast/ccd-control-panel.js` for the control panel, and `/ccd_cast/ccd-readiness-card.js` for readiness reporting.
5. `stop_casting` remains a one-off stop. Use `pause_casting` for a temporary or indefinite pause. Indefinite pauses are **in memory** and end after a restart or explicit resume.
6. A frontend heartbeat cannot prove that a particular Chromecast rendered the dashboard. No automatic recast is initiated from a missing heartbeat.
7. Verify actual GitHub releases/HACS availability before treating 3.0.0 as a downloadable published release.

For setup and troubleshooting, see [README.md](README.md), [docs/update_help.md](docs/update_help.md), and [ROADMAP.md](ROADMAP.md).

### Validation

The feature PRs passed the repository's available automated checks. That does **not** replace testing on real Cast receivers or a full Home Assistant runtime integration suite. Hardware-specific validation remains tracked in the roadmap.
