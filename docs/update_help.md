# Updating and troubleshooting Continuously Casting Dashboards

This is the **current upgrade guide** for [anaschillin/continuously_casting_dashboards](https://github.com/anaschillin/continuously_casting_dashboards). It supersedes older instructions written for v1.1.4. Those older instructions advised removing and reinstalling everything; that is **not the normal upgrade path** and risks losing configuration.

The fork's v3.0.0 baseline includes [PRs #2–#6](../ROADMAP.md), covering dashboard rules, discovery, readiness reporting, controls, pause/resume and Repairs. The follow-up **3.0.1 candidate** upgrades CATT from 0.12.13 to **0.13.3** and updates documentation. The integration and Marketplace metadata match, but check actual published GitHub releases before assuming a tagged 3.0.1 download exists. Hardware compatibility remains unverified.

## Before changing anything

1. Make a Home Assistant backup that includes configuration and the `continuously_casting_dashboards` integration settings.
2. Note each configured Cast device, its dashboard order, URL, entity controls, global schedule and any keepalive remote.
3. Verify whether your installation came from the [original upstream repository](https://github.com/b0mbays/continuously_casting_dashboards) or [this fork](https://github.com/anaschillin/continuously_casting_dashboards). They have the **same integration domain**; use a single installation source.
4. If you still use YAML, keep a copy of the `continuously_casting_dashboards:` section until the devices have appeared and been verified in the UI.

## Update an existing installation

1. On **Home Assistant 2026.11+**, go to **Settings → Marketplace**. Choose **Add from link** and enter `https://github.com/anaschillin/continuously_casting_dashboards` (type **Integration** if prompted). The older HACS interface is used only on Home Assistant versions before 2026.11.
2. When a version containing the updated dependency is available, install/update it through Marketplace (or older HACS). For manual installs, replace only the integration files in `config/custom_components/continuously_casting_dashboards/`. The manifest instructs Home Assistant to install CATT; do **not** manually modify HAOS's managed Python environment.
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
| [#6](https://github.com/anaschillin/continuously_casting_dashboards/pull/6) | Yes | Cast control panel, timed pause/resume, Repairs, notification persistence fix and 3.0.0 version bump |

All five feature PRs were merged on 6 November 2026. **A merged feature is not automatically a published release or verified on every display.** See [the roadmap](../ROADMAP.md) for outstanding features and validation.

## CATT 0.13.3 upgrade checks and rollback

This upgrade changes the Python dependency from `catt==0.12.13` to `catt==0.13.3` without changing any dashboard settings or Home Assistant services.

1. **Before updating**, take a full Home Assistant backup, record the running integration version and check whether the receiver is currently displaying a dashboard.
2. **After updating**, restart Home Assistant so the new manifest requirement can be installed. Check the logs for dependency-resolution errors. CATT 0.13.3 requires Python 3.11+ and PyChromecast 14.x; Home Assistant's current Google Cast integration uses PyChromecast 14.1.1.
3. Test one noncritical receiver first: a normal dashboard, name discovery, direct IP, preserve-volume behaviour and the return of dashboard casting after unrelated media or Assistant use. A successful CI test does **not** establish receiver compatibility.
4. If repeated recasting, wrong-device selection or dependency errors occur, restore the previously working integration version from your backup (including its older CATT requirement), then restart Home Assistant. Avoid forcing a manual pip downgrade inside HAOS.
5. If an incompatible package remains after restoring files, collect logs and follow Home Assistant's supported recovery/backup process; do not delete config entries merely to clear an error.

See [the CATT compatibility matrix](CAST_BACKENDS.md) for the full device test plan and [the changelog](../CHANGELOG.md) for the 3.0.1 summary.

## Background initialisation warning in 3.0.2 and earlier

The warning `Background device initialization timed out, continuing anyway`
comes from a fixed 45-second deadline around the initial device setup. It can
fire even with one working display because initial setup previously waited the
full default 60-second inter-device delay after its last device.

Version **3.0.3** removes the blanket startup deadline, avoids a trailing
delay and tracks startup tasks for clean unload. Individual CATT operations
still have their normal timeouts. This startup warning is **not** evidence
of a custom-card JavaScript failure. If casting succeeds but the screen
shows `Configuration error`, use the receiver diagnostics below to
troubleshoot Lovelace loading separately.

## Diagnosing custom-card errors on Cast receivers

Enable **Recover custom-card configuration errors on Cast** for the affected
dashboard, make a fresh Cast attempt, and download the integration diagnostics
under **Settings → Devices & Services**. The device's `cast_frontend`
section records whether the receiver was able to report, the number of
Lovelace `hui-error-card` elements and redacted script/resource/registration
counters. No dashboard query values or raw JavaScript error messages are
collected.

- `no_report` after 90 seconds: either the frontend guard did not execute or
  the receiver could not reach the authenticated reporting service. It does
  **not** prove the resource was never requested.
- `error_cards`: the receiver reported an actual Lovelace error element.
  Confirm the same dashboard works in Kiosk Satellite/Chrome to compare the
  environments; the source could still be malformed card config.
- `script_or_resource_errors`: the receiver saw a browser script/link failure
  **after the guard started**. Old failures may have occurred before observation.
- `observed` but the screen is broken: capture the reported counts and HA
  frontend version. Successful card registration is not proof of rendering.
- `reload_requested`: a single page-reload attempt was observed. If the
  subsequent state remains `error_cards`, do not attempt repeated recasts.

Browser reports are **best-effort** and may also originate from another browser
opening the identical guarded URL. They are a targeted diagnostic, not a
security attestation of a specific physical receiver.

## Common checks

- **Device not found:** Try a valid explicit Cast IP. Name matching now supports exact case-insensitive names and a recognized Google suffix, but refuses ambiguous matches.
- **Frequent recasts:** Verify the target device's Home Assistant Cast entity, active third-party media, Google Assistant activity, and the DashCast app state. Check the current dashboard's priority, schedule and entity condition.
- **Dashboard not appearing:** Check the URL from the Cast device's network, authentication and certificates. A successful cast command does not prove the browser loaded custom cards.
- **JavaScript card error:** If `custom:ccd-readiness-card` is configured, confirm that `/ccd_cast/ccd-readiness-card.js` is registered as a JavaScript module resource and that `verify_readiness` is enabled. The reporter checks custom-element registration only and cannot fix frontend race conditions.
- **Volume changes unexpectedly:** Enable `preserve_volume` on the specific dashboard if you do not want CCD to issue volume commands.
- **Control panel not visible:** Add `/ccd_cast/ccd-control-panel.js` under dashboard Resources as a JavaScript module and use `type: custom:ccd-control-panel` with the device's exact configured name and real status sensor entity ID.
- **System Repairs:** v3 registers actionable Repairs if CATT is missing or ambiguous Cast names are configured without explicit IPs. Temporary network outages do not produce Repairs.
- **Unreachable/retry delay:** Download the integration diagnostics and inspect the per-device status sensor's `last_error` / `retry_in_seconds`. Repeated failures use bounded exponential backoff rather than permanent lockout.
- **`stop_casting` did not stay stopped:** It remains a one-time stop. In v3 code, use **Pause casting** / `pause_casting` for an indefinite (until resume/restart) or timed pause; `resume_casting` clears it.
- **Home Assistant import failure:** This fork's `main` includes the Home Assistant 2026.11 `EntityCategory` import fix. Confirm that the installed copy is current and restart Home Assistant.

If updating fails, collect the exact Home Assistant Core version, integration version, relevant log excerpt (with tokens and addresses redacted), and integration diagnostics before opening an [issue in this fork](https://github.com/anaschillin/continuously_casting_dashboards/issues). Avoid repeated deletion/reinstallation unless a specific migration or repair procedure requires it.

For installations still using the old YAML layout, refer to the [historical v1.3.0 formatting note](update-help-1.3.0.md); it is **not** a general modern upgrade procedure.
