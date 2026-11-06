# Development roadmap

This roadmap tracks work in [Continuously Casting Dashboards](https://github.com/anaschillin/continuously_casting_dashboards). It distinguishes **merged functionality**, **remaining work**, and **validation not yet performed on real Home Assistant/Cast hardware**. Merged does not necessarily mean released, deployed, or tested on every receiver.

**Repository baseline:** `main` includes [PR #2](https://github.com/anaschillin/continuously_casting_dashboards/pull/2), [PR #3](https://github.com/anaschillin/continuously_casting_dashboards/pull/3), [PR #4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4), and [PR #5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5). All four were merged on 6 November 2026. The integration manifest currently declares version `2.1.0`; do not treat a merged PR as evidence that a new release has been published.

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
- [ ] Implement actionable Home Assistant Repairs for enduring configuration problems; **in follow-up development, not yet merged**.
- [ ] Evaluate a CATT dependency upgrade against Home Assistant Python compatibility and actual Cast hardware ([upstream #160](https://github.com/b0mbays/continuously_casting_dashboards/issues/160)); continue using the pinned version until validated.

## Milestone 3 — smarter casting and controls

**Merged:** [PR #4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4).

- [x] Debounce relevant entity changes and re-evaluate dashboard eligibility ([upstream #159](https://github.com/b0mbays/continuously_casting_dashboards/issues/159)); periodic polling remains as a fallback.
- [x] Add `priority`, optional `rotation_seconds`, and temporary manual dashboard override/clear-override Home Assistant services.
- [ ] Offer a dedicated Lovelace multi-device control panel with status and actions; **in follow-up development, not yet merged**.
- [ ] Add durable per-device pause/resume behaviour; **in follow-up development, not yet merged**. Current `stop_casting` is a one-off action, not a lasting pause.
- [ ] Evaluate compatible alternative Cast backends; do not assume Home Assistant Cast can replace CATT/DashCast in every situation.
- [ ] Fix global notification-option persistence ([upstream #155](https://github.com/b0mbays/continuously_casting_dashboards/issues/155)); **in follow-up development, not yet merged**.

## Milestone 4 — optional dashboard readiness reporting

**Merged:** [PR #5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5).

- [x] Add an opt-in Lovelace companion card and authenticated heartbeat service for required custom-element registration.
- [x] Report `disabled`, `pending`, `ready`, `missing_elements`, `unconfirmed` and `stale` in runtime diagnostics.
- [ ] Verify **actual rendered dashboard content**. A registered custom element or successful Cast command alone does not prove rendering; any browser opening the same page may send a heartbeat.
- [ ] Explore bounded, safe troubleshooting/recovery for missing resources without interrupting media. **Automatic recasting from a missing heartbeat is deliberately not implemented.**
- [ ] Validate receiver-specific behaviour on multiple Cast devices, frontend reloads, kiosk layouts and supported Home Assistant versions.

## Continuous quality and release work

- [x] CI includes Python compilation, translation JSON checks, JavaScript syntax checks, Ruff checks on added modules and regression tests (the merged PR #5 branch passed 51 tests).
- [ ] Expand to a complete Home Assistant runtime test harness and verify migrations, restart/unload behaviour and multi-device isolation.
- [ ] Expand Ruff coverage to the older integration code as existing formatting is progressively cleaned up.
- [ ] Test a supported release on real Cast hardware before describing a feature as hardware-verified.
- [ ] Maintain documentation, UI translations, service definitions and release notes whenever features change.

For current setup and service examples see [README.md](README.md); for post-upgrade troubleshooting see [docs/update_help.md](docs/update_help.md).

**Status convention:** `[x]` means implemented in merged code and covered by the available project checks; it is not a blanket compatibility guarantee. `[ ]` means unfinished or requiring further validation.
