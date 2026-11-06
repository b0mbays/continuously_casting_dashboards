# Cast backend and CATT compatibility review

Last checked: **2026-11-06**. This is a design and compatibility review, not a production dependency change.

## Current supported path

The integration uses subprocess commands from **CATT 0.12.13**, pinned in
`manifest.json`. The monitoring engine assumes that `catt scan` provides
discoverable device names, `catt -d DEVICE status` returns parseable playback
state, and `catt -d DEVICE cast_site URL` uses DashCast to display a webpage.

As of 2026-11-06, **CATT 0.13.3** is the latest version published on PyPI
(2026-09-24). It requires Python 3.11 or newer. Home Assistant 2026.11
uses a modern Python runtime, but the Python version alone does **not**
establish CLI output or pychromecast dependency compatibility.

Upstream sources:
- https://pypi.org/project/catt/
- https://github.com/skorokithakis/catt/releases
- https://github.com/skorokithakis/catt
- https://www.home-assistant.io/integrations/cast

### Why this PR does not unpin CATT

CATT's 0.13.x changelog includes discovery, timeout and pychromecast changes,
and a DashCast application ID change. CCD also uses a DashCast app ID and
interprets `catt status` text. Changing CATT without testing those assumptions
could make a healthy display appear disconnected or cause unwanted recasts.

Upgrade checklist:

1. Reproduce CATT 0.12.13 baseline on Home Assistant 2026.11 using a Nest
   Hub / Chromecast, with two configured devices and custom cards.
2. On an isolated feature branch, pin 0.13.3, test resolution of its
   dependencies with Home Assistant, and confirm `catt --help`,
   `catt scan`, `catt status`, `cast_site`, `volume` and `stop`.
3. Confirm the DashCast app ID actually reported by HA's Google Cast entity.
4. Test normal cast, media playing/paused, Google Assistant, unreachable,
   device rename, timeouts, reconnect and Home Assistant restart.
5. Test API/CLI changes without changing user settings or service contracts.
6. Roll back to 0.12.13 if any display loops or media gets interrupted.

**Decision:** retain CATT 0.12.13 until at least one physical Cast device
passes the upgrade test matrix. This avoids hiding an untested dependency
upgrade among unrelated UI and Repairs changes.

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

No physical Chromecast or HAOS deployment test was run as part of this
review. The existing automated tests exercise local logic and mocked
subprocesses, not receiver firmware, display rendering, or live network
behavior.
