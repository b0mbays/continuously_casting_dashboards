# Changelog

All changes here refer to the [anaschillin fork](https://github.com/anaschillin/continuously_casting_dashboards). Home Assistant integration and HACS metadata are maintained together; a merged commit or version field does **not** automatically create a tagged GitHub release or HACS download.

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
3. The manifest still pins `catt==0.12.13`. A newer CATT version has **not** been adopted and needs compatibility testing.
4. Optional UI features require registering the JavaScript resources: `/ccd_cast/ccd-control-panel.js` for the control panel, and `/ccd_cast/ccd-readiness-card.js` for readiness reporting.
5. `stop_casting` remains a one-off stop. Use `pause_casting` for a temporary or indefinite pause. Indefinite pauses are **in memory** and end after a restart or explicit resume.
6. A frontend heartbeat cannot prove that a particular Chromecast rendered the dashboard. No automatic recast is initiated from a missing heartbeat.
7. Verify actual GitHub releases/HACS availability before treating 3.0.0 as a downloadable published release.

For setup and troubleshooting, see [README.md](README.md), [docs/update_help.md](docs/update_help.md), and [ROADMAP.md](ROADMAP.md).

### Validation

The feature PRs passed the repository's available automated checks. That does **not** replace testing on real Cast receivers or a full Home Assistant runtime integration suite. Hardware-specific validation remains tracked in the roadmap.
