# Continuously Casting Dashboards for Home Assistant

Keep selected Home Assistant dashboards visible on compatible Chromecast / Cast displays, with monitoring that can restore the dashboard when the display is idle and eligible to cast.

This fork includes the v3.0.0 functionality merged into [`main`](https://github.com/anaschillin/continuously_casting_dashboards) on **6 November 2026**. The **3.0.1 update candidate** pins **CATT 0.13.3**, the latest published upstream version checked on that date. Integration and Marketplace metadata are kept in sync; a GitHub release/tag is still a separate publishing step.

## Current capabilities

- Global and per-dashboard schedules, entity-state rules, and opt-in continuous casting.
- Independent dashboard eligibility with per-dashboard priority, optional rotation, and a time-limited manual selection service.
- Volume preservation, speaker-group and user-media protection, and opt-in Google TV remote keepalive.
- Improved Cast discovery, bounded reconnection backoff, timeout/subprocess safeguards, and Home Assistant diagnostics.
- An **optional, diagnostic-only** Lovelace readiness reporter for custom-element registration. It does not confirm actual rendering or automatically recast on missing heartbeats.
- Home Assistant status sensors and documented runtime services.

## Installation and details

On Home Assistant **2026.11 or newer**, open **Settings → Marketplace → Add from link** and enter `https://github.com/anaschillin/continuously_casting_dashboards` (type **Integration** if prompted). Before 2026.11, add it through HACS **Custom repositories**. Manual installation is also possible. Do not install both this fork and the original upstream integration simultaneously; they share the same Home Assistant integration domain.

See [README.md](README.md) for setup, configuration, dashboard selection and examples, and [CHANGELOG.md](CHANGELOG.md) for release history, including the v3.0.1 dependency change. Use [the upgrade/troubleshooting guide](docs/update_help.md) when updating an existing installation, and [ROADMAP.md](ROADMAP.md) for outstanding work.

This fork builds on the [original b0mbays project](https://github.com/b0mbays/continuously_casting_dashboards). Development and testing contributions are welcome through [this fork's issue tracker](https://github.com/anaschillin/continuously_casting_dashboards/issues).
