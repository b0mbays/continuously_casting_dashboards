# Continuously Casting Dashboards for Home Assistant

Keep selected Home Assistant dashboards visible on compatible Chromecast / Cast displays, with monitoring that can restore the dashboard when the display is idle and eligible to cast.

This fork includes the features merged into [`main`](https://github.com/anaschillin/continuously_casting_dashboards) through **6 November 2026**. The repository manifest currently declares integration version `2.1.0`; a merged pull request does not automatically publish a HACS release.

## Current capabilities

- Global and per-dashboard schedules, entity-state rules, and opt-in continuous casting.
- Independent dashboard eligibility with per-dashboard priority, optional rotation, and a time-limited manual selection service.
- Volume preservation, speaker-group and user-media protection, and opt-in Google TV remote keepalive.
- Improved Cast discovery, bounded reconnection backoff, timeout/subprocess safeguards, and Home Assistant diagnostics.
- An **optional, diagnostic-only** Lovelace readiness reporter for custom-element registration. It does not confirm actual rendering or automatically recast on missing heartbeats.
- Home Assistant status sensors and documented runtime services.

## Installation and details

For this fork, add `https://github.com/anaschillin/continuously_casting_dashboards` as a HACS **Integration** custom repository, or install manually from this repository. Do not install both this fork and the original upstream integration simultaneously; they use the same Home Assistant integration domain.

See [README.md](README.md) for setup, configuration, dashboard selection and examples. Use [the upgrade/troubleshooting guide](docs/update_help.md) when updating an existing installation, and [ROADMAP.md](ROADMAP.md) for outstanding work.

This fork builds on the [original b0mbays project](https://github.com/b0mbays/continuously_casting_dashboards). Development and testing contributions are welcome through [this fork's issue tracker](https://github.com/anaschillin/continuously_casting_dashboards/issues).
