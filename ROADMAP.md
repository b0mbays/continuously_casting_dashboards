# Development roadmap

This roadmap tracks work in [Continuously Casting Dashboards](https://github.com/anaschillin/continuously_casting_dashboards). It distinguishes **merged functionality**, **remaining work**, and **validation not yet performed on real Home Assistant/Cast hardware**. Merged does not necessarily mean released, deployed, or tested on every receiver.

**Version 3.0.0 merged baseline (6 November 2026):** `main` includes merged [PR #2](https://github.com/anaschillin/continuously_casting_dashboards/pull/2), [#3](https://github.com/anaschillin/continuously_casting_dashboards/pull/3), [#4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4), [#5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5), and [#6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6), plus the documentation update [#7](https://github.com/anaschillin/continuously_casting_dashboards/pull/7). The follow-up CATT update branch proposes version `3.0.1` with `catt==0.13.3`. Neither version metadata alone nor a merged pull request publishes a GitHub release/tag.

## Baseline — merged

- [x] Consolidate upstream [#152](https://github.com/b0mbays/continuously_casting_dashboards/pull/152), [#153](https://github.com/b0mbays/continuously_casting_dashboards/pull/153), and [#154](https://github.com/b0mbays/continuously_casting_dashboards/pull/154), including Google TV keepalive and timeout recovery.
- [x] Fix the Home Assistant 2026.11 `EntityCategory` import ([upstream #161](https://github.com/b0mbays/continuously_casting_dashboards/issues/161)).
- [x] Add automated Python smoke/regression tests and GitHub Actions.

## Milestone 1 — dashboard rules, scheduling and volume

**Merged:** [PR #2](https://github.com/anaschillin/continuously_casting_dashboards/pull/2).

- [x] Evaluate each dashboard's schedule **and** required entity state independently; a disabled dashboard does not hide a later eligible entry ([upstream #145](https://github.com/b0mbays/continuously_casting_dashboards/issues/145)).
- [x] Add opt-in `cast_continuously` to ignore time windows while respecting entity controls ([upstream #156](https://github.com/b0mbays/continuously_casting_dashboards/issues/156)).
- [x] Add opt-in `preserve_volume` to avoid CATT volume changes, including the initial mute ([upstream #142](https://github.com/b0mbays/continuously_casting_dashboards/issues/142)).
- [x] Normalize saved time-selector values and retain new settings through add/edit/reconfigure paths ([upstream #144](https://github.com/b0mbays/continuously_casting_dashboards/issues/144)).
- [x] Add regression tests for disabled/fallback dashboards, midnight windows, entity states, and volume preservation.
- [x] Preserve defaults for existing configurations until a new option is explicitly enabled.

## Milestone 2 — discovery, recovery and diagnostics

**Merged:** [PR #3](https://github.com/anaschillin/continuously_casting_dashboards/pull/3).

- [x] Use strict, unambiguous Cast-name matching, including a known Google manufacturer/model suffix ([upstream #146](https://github.com/b0mbays/continuously_casting_dashboards/issues/146)).
- [x] Share and serialize discovery scans; cap concurrent checks; add subprocess cleanup and per-device exponential backoff ([upstream #139](https://github.com/b0mbays/continuously_casting_dashboards/issues/139)).
- [x] Distinguish dashboard, idle, unreachable, media-playing and Assistant states using existing device/monitoring checks.
- [x] Expose retry delay and failure summaries through Home Assistant diagnostic sensors and config-entry diagnostics.
- [x] Add actionable Home Assistant Repairs for missing CATT and duplicate name-only device configurations ([PR #6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).
- [x] Review and propose the latest CATT `0.13.3` pin, confirm published Python requirement (3.11+) and PyChromecast compatibility with Home Assistant's 14.1.1, and add CLI smoke tests on Python 3.13/3.14 ([upstream #160](https://github.com/b0mbays/continuously_casting_dashboards/issues/160)).
- [ ] Validate CATT 0.13.3 on real Nest Hub/Chromecast receivers and verify integration operation with the installed Home Assistant runtime. Automated CLI tests do not certify hardware.

## Milestone 3 — smarter casting and controls

**Merged:** [PR #4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4).

- [x] Debounce relevant entity changes and re-evaluate dashboard eligibility ([upstream #159](https://github.com/b0mbays/continuously_casting_dashboards/issues/159)); periodic polling remains as a fallback.
- [x] Add `priority`, optional `rotation_seconds`, and temporary manual dashboard override/clear-override Home Assistant services.
- [x] Add a bundled optional Lovelace multi-device control panel with connection status, retries, pause/resume and manual dashboard actions ([PR #6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).
- [x] Add **in-memory** per-device pause/resume (until resumed/restart or a timed expiry), distinct from the one-off `stop_casting` action ([PR #6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).
- [ ] Evaluate compatible alternative Cast backends; do not assume Home Assistant Cast can replace CATT/DashCast in every situation.
- [x] Persist the disabled global notification setting and preserve other options ([upstream #155](https://github.com/b0mbays/continuously_casting_dashboards/issues/155), [PR #6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6)).

## Milestone 4 — optional dashboard readiness reporting

**Merged:** [PR #5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5).

- [x] Add an opt-in Lovelace companion card and authenticated heartbeat service for required custom-element registration.
- [x] Report `disabled`, `pending`, `ready`, `missing_elements`, `unconfirmed` and `stale` in runtime diagnostics.
- [ ] Verify **actual rendered dashboard content**. A registered custom element or successful Cast command alone does not prove rendering; any browser opening the same page may send a heartbeat.
- [ ] Explore bounded, safe troubleshooting/recovery for missing resources without interrupting media. **Automatic recasting from a missing heartbeat is deliberately not implemented.**
- [ ] Validate receiver-specific behaviour on multiple Cast devices, frontend reloads, kiosk layouts and supported Home Assistant versions.

## Outstanding compatibility and readiness work

- [ ] Validate the latest 3.0.x candidate in an actual Home Assistant installation across normal reloads/restarts, multiple devices, media interruptions, and frontend resource reloads.
- [ ] Verify the proposed CATT `0.13.3` upgrade on actual HAOS and Cast hardware, including media protection, status interpretation, discovery and Dashboard URLs. The feature branch contains the new pin; a successful CLI smoke test alone is not sufficient.
- [ ] Investigate alternative Cast backends with an opt-in adapter; [backend assessment](docs/CAST_BACKENDS.md) is design/evaluation, not a released backend.
- [ ] Verify receiver-specific, authenticated frontend readiness rather than accepting a heartbeat that could come from another browser.
- [ ] Design any automatic recovery from a missing frontend heartbeat to avoid unnecessary recasts or interrupting user media.
- [ ] Publish and validate a tagged 3.0.x release after hardware checks; changing version metadata alone does not publish one.

## Generic Cast custom-card recovery — under review

- [x] Implement a **default-off**, per-dashboard Cast-only recovery mode
  that detects persistent `hui-error-card` elements and requests one
  bounded browser reload after two observations, without another CATT cast.
- [x] Add protection against repeated reloads through a consumed URL flag
  and session storage, plus regression tests for nested shadow roots,
  transient errors, disabled mode and blocked browser storage.
- [ ] Test the guard on real Nest Hub / Chromecast browsers, including
  panel views, multiple third-party HACS custom cards, normal media
  interruptions, authentication and a deliberately broken card.
- [ ] Continue tracking upstream Home Assistant frontend resource/registry
  loading races; the guard is a mitigation, **not** a frontend core fix.

**Status:** code above is on a feature branch, not part of the merged
v3.0.1 release until its PR passes review and is merged.

## Startup reliability — 3.0.3 candidate

- [x] Remove the false 45-second limit from background initialization: the
  default 60-second delay used to guarantee a timeout after even one cast.
- [x] Apply the initial inter-device cast delay only between attempts and track
  background tasks for clean integration reload/unload.
- [ ] Confirm the revised startup sequence on HAOS and Cast devices.
- [ ] Diagnose persistent Lovelace **Configuration error** separately; it
  cannot be established from a CATT initialization timeout log.

## Continuous quality and release work

- [x] CI includes Python compilation, translation JSON checks, JavaScript syntax checks, Ruff checks on added modules and regression tests (the merged PR #5 branch passed 51 tests).
- [ ] Expand to a complete Home Assistant runtime test harness and verify migrations, restart/unload behaviour and multi-device isolation.
- [ ] Expand Ruff coverage to the older integration code as existing formatting is progressively cleaned up.
- [ ] Test a supported release on real Cast hardware before describing a feature as hardware-verified.
- [ ] Maintain documentation, UI translations, service definitions and release notes whenever features change.

For current setup and service examples see [README.md](README.md); for post-upgrade troubleshooting see [docs/update_help.md](docs/update_help.md).

**Status convention:** `[x]` means implemented in merged code and covered by the available project checks; it is not a blanket compatibility guarantee. `[ ]` means unfinished or requiring further validation.
