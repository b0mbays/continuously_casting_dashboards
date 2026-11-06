# Updating and troubleshooting Continuously Casting Dashboards

This is the **current upgrade guide** for [anaschillin/continuously_casting_dashboards](https://github.com/anaschillin/continuously_casting_dashboards). It supersedes older instructions written for v1.1.4. Those older instructions advised removing and reinstalling everything; that is **not the normal upgrade path** and risks losing configuration.

The fork's `main` includes merged [PRs #2–#5](../ROADMAP.md), which introduce independent dashboard rules, continuous casting, volume preservation, improved discovery/retries, dashboard priority/rotation and optional frontend-readiness reporting. The manifest currently declares version `2.1.0`. Check the actual release shown in HACS before assuming a merged feature is installed.

## Before changing anything

1. Make a Home Assistant backup that includes configuration and the `continuously_casting_dashboards` integration settings.
2. Note each configured Cast device, its dashboard order, URL, entity controls, global schedule and any keepalive remote.
3. Verify whether your installation came from the [original upstream repository](https://github.com/b0mbays/continuously_casting_dashboards) or [this fork](https://github.com/anaschillin/continuously_casting_dashboards). They have the **same integration domain**; use a single installation source.
4. If you still use YAML, keep a copy of the `continuously_casting_dashboards:` section until the devices have appeared and been verified in the UI.

## Update an existing installation

1. In HACS, verify that the integration is sourced from the intended repository. For this fork, the custom repository URL is `https://github.com/anaschillin/continuously_casting_dashboards` (category **Integration**).
2. Update the integration using HACS, or manually replace only the integration files under `config/custom_components/continuously_casting_dashboards/` if that is how it was installed.
3. Restart Home Assistant.
4. Open **Settings → Devices & Services → Continuously Casting Dashboards**. Verify configured devices, schedules, dashboard order and state conditions.
5. Confirm at least one Cast display can load the expected dashboard. If using multiple dashboards, check an entity-controlled fallback and a scheduled transition.
6. Check **Developer Tools → Actions** for `select_dashboard` and `clear_dashboard_override`, and verify diagnostic sensor state and attributes where available.

**Migrating from upstream to this fork:** Do not leave two HACS sources managing one integration folder. Back up your config and choose the desired repository source before updating. If your HACS installation cannot switch source cleanly, remove the *old source association* according to your HACS version's instructions; do not delete Home Assistant config entries or YAML merely to switch source.

## What changed in merged PRs

| PR | Included in `main` | Key functionality |
| --- | --- | --- |
| [#2](https://github.com/anaschillin/continuously_casting_dashboards/pull/2) | Yes | Independent dashboard rules, continuous casting, preserve volume, editor persistence |
| [#3](https://github.com/anaschillin/continuously_casting_dashboards/pull/3) | Yes | Strict Cast discovery matching, shared scans, recoverable backoff, runtime diagnostics |
| [#4](https://github.com/anaschillin/continuously_casting_dashboards/pull/4) | Yes | Priorities, rotation, debounced entity switching, temporary dashboard override services |
| [#5](https://github.com/anaschillin/continuously_casting_dashboards/pull/5) | Yes | Optional custom-element readiness reporter and non-disruptive diagnostics |

All four were merged on 6 November 2026. **A merged feature is not automatically a published release or verified on every display.** See [the roadmap](../ROADMAP.md) for outstanding features and validation.

## Common checks

- **Device not found:** Try a valid explicit Cast IP. Name matching now supports exact case-insensitive names and a recognized Google suffix, but refuses ambiguous matches.
- **Frequent recasts:** Verify the target device's Home Assistant Cast entity, active third-party media, Google Assistant activity, and the DashCast app state. Check the current dashboard's priority, schedule and entity condition.
- **Dashboard not appearing:** Check the URL from the Cast device's network, authentication and certificates. A successful cast command does not prove the browser loaded custom cards.
- **JavaScript card error:** If `custom:ccd-readiness-card` is configured, confirm that `/ccd_cast/ccd-readiness-card.js` is registered as a JavaScript module resource and that `verify_readiness` is enabled. The reporter checks custom-element registration only and cannot fix frontend race conditions.
- **Volume changes unexpectedly:** Enable `preserve_volume` on the specific dashboard if you do not want CCD to issue volume commands.
- **Unreachable/retry delay:** Download the integration diagnostics and inspect the per-device status sensor's `last_error` / `retry_in_seconds`. Repeated failures use bounded exponential backoff rather than permanent lockout.
- **`stop_casting` did not stay stopped:** As of PR #5 it is a one-time stop, **not** a persistent pause. A lasting pause control is a separate roadmap item.
- **Home Assistant import failure:** This fork's `main` includes the Home Assistant 2026.11 `EntityCategory` import fix. Confirm that the installed copy is current and restart Home Assistant.

If updating fails, collect the exact Home Assistant Core version, integration version, relevant log excerpt (with tokens and addresses redacted), and integration diagnostics before opening an [issue in this fork](https://github.com/anaschillin/continuously_casting_dashboards/issues). Avoid repeated deletion/reinstallation unless a specific migration or repair procedure requires it.

For installations still using the old YAML layout, refer to the [historical v1.3.0 formatting note](update-help-1.3.0.md); it is **not** a general modern upgrade procedure.
