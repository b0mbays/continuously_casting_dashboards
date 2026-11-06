# Cast backend and CATT compatibility review

Checked **6 November 2026** against [CATT on PyPI](https://pypi.org/project/catt/), [upstream release notes](https://github.com/skorokithakis/catt/releases), the [CATT CLI source](https://github.com/skorokithakis/catt/blob/master/catt/cli.py), and [Home Assistant's Google Cast manifest](https://github.com/home-assistant/core/blob/dev/homeassistant/components/cast/manifest.json).

## CATT 0.13.3 upgrade — candidate for version 3.0.1

The integration now proposes **`catt==0.13.3`** in `custom_components/continuously_casting_dashboards/manifest.json`, upgrading from `0.12.13`. Upstream published 0.13.3 on **24 September 2026**; it was the latest stable published version when checked on **6 November 2026**.

CATT 0.13.3 declares **Python >=3.11** and **PyChromecast >=14.0.1,<15**. Home Assistant Core's current Google Cast integration requires **PyChromecast 14.1.1**, which is inside CATT's supported version range. A successful package resolver check does not establish that Cast receiver firmware, discovery or application IDs behave identically.

### CLI and parsing compatibility

CCD currently uses these CATT subprocess commands, all of which remain in 0.13.3:

| Integration operation | CATT command | Compatibility concern |
| --- | --- | --- |
| Device discovery | `catt scan` | Output must retain `IP - device name - manufacturer model`, with safe handling of ambiguous names |
| Cast dashboard URL | `catt -d IP cast_site URL` | DashCast receiver readiness, app ID, and network access can change |
| Current state / volume | `catt -d IP status` | CCD parses `Title:`, `State:` and `Volume:` text; DashCast may have no media session |
| Change/restore volume | `catt -d IP volume LEVEL` | Use integer levels 0–100; `preserve_volume` skips these commands |
| Stop cast | `catt -d IP stop` | Must not interrupt external media or Assistant activity |

The new CI checks the pinned version, resolves it with `PyChromecast==14.1.1`, runs `pip check`, verifies the CLI command help and checks the scan/status output format using mocks. Tests run on Python 3.13 and 3.14. They do **not** discover real Cast devices or issue destructive Cast commands.

Relevant upstream changes since 0.12.13 include updated DashCast application handling, PyChromecast dependencies, discovery and timeout fixes. The integration continues to monitor real device identity and respect user-media protection; never assume an app is healthy solely because CATT exited successfully.

### Live upgrade test matrix (still required)

1. Back up Home Assistant; record current integration version, CATT version and device configurations.
2. Install the candidate on a test HA instance or noncritical device and restart Home Assistant; verify the Python requirement resolves.
3. Test direct-IP casting and name discovery on Nest Hub/Chromecast, including Google's name/model suffixes and ambiguous names.
4. Verify `cast_site` displays a normal Lovelace view and a custom-card view. Look for repeated recasts and compare the DashCast app ID against Home Assistant's Cast media-player entity.
5. Test `status`, volume preservation and volume restore, initial cast, sleep/idle, user media playing/paused, Assistant use and group playback without unwanted interruptions.
6. Test timeout recovery, an unreachable/offline receiver, multiple dashboards, manual pause/resume and HA reload/restart.
7. Only after hardware and integration validation should this be treated as an operationally verified dependency upgrade.

**Rollback:** restore the previously working integration version (which pins `catt==0.12.13`) from a backup or a known-good source, then restart HA. For HAOS, do not manually edit packages in Home Assistant's managed environment. See [upgrade help](update_help.md).

**Status:** CATT 0.13.3 is a source-code dependency update pending live receiver validation, not a replacement casting backend.

## Alternative backend: native Home Assistant Cast

Home Assistant exposes `cast.show_lovelace_view` to display a Lovelace view
through its own Cast receiver. This can be promising for Home Assistant views
but it is **not** a drop-in replacement for CATT's arbitrary-webpage
`cast_site` backend.

Constraints:
- Requires a reachable **HTTPS** Home Assistant external URL or Home Assistant Cloud.
- Shows Home Assistant dashboard views, not arbitrary external URLs.
- Custom cards might depend on browser APIs unavailable in the Cast frontend.
- Native receiver status, page readiness and playback detection differ from
  DashCast, so blindly reusing CATT logic could interrupt user media.

See:
- https://www.home-assistant.io/integrations/cast
- https://cast.home-assistant.io/faq.html

### Proposed backend interface

A future experimental adapter can expose:

- `async_cast(target, dashboard)`
- `async_stop(target)` (only for this integration's own active session)
- `async_status(target)` yielding `dashboard`, `user_media`,
  `assistant`, `idle`, or `unknown`
- `async_discover(target)`
- `supported_dashboard_types` and `readiness_capabilities`

CATT/DashCast should remain the default. Only an explicitly opted-in
per-dashboard backend switch should use HA Cast, and only for a supported
Home Assistant dashboard/view identifier. The HA Cast adapter must have
its own status and non-interruption tests before it is offered to users.

## Remaining validation

The CATT 0.13.3 candidate includes pinned-package resolver and CLI compatibility tests, plus existing integration-logic regression tests. Physical Chromecast and HAOS runtime checks are still outstanding; mocked scan/status output is not evidence that all real receiver models behave the same. Verify these before marking the upgrade complete in the roadmap.
