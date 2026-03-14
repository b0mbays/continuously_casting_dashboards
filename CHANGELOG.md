## UI-based configuration with device subentries
- Replaced YAML-only setup with a full UI config flow. Global settings (logging, cast delay, time windows, switch entity) are configured once; each Chromecast device is added as an independent subentry with its own dashboards, volume, time window, and entity controls.
- Automatic migration imports existing `configuration.yaml` devices into subentries on first boot, with no data loss.

## Concurrent device monitoring
- Replaced serial device processing (one device blocking all others) with `asyncio.gather()` so all devices are checked in parallel each cycle. A single unresponsive device no longer delays the entire monitoring loop.

## Unreachable device handling
- Devices that time out on `catt status` are now correctly marked as `disconnected` rather than `other_content`, avoiding false "other content playing" states that required manual restarts.
- Optional HA persistent notification fires when a device first becomes unreachable and auto-dismisses when it recovers. Can be disabled in global settings for flaky networks.

## Volume scale fix
- Config UI uses 0-100 for volume. The legacy 1-10 YAML multiplier (x 10) has been removed — volume values are now passed directly to `catt`, so a slider value of 5 sets 5%, not 50%.

## Subprocess lifecycle management
- All `catt` subprocesses are tracked by key and explicitly terminated/killed on timeout or unload, preventing zombie processes accumulating over time.
- Subprocess timeout values extracted to named constants (`TIMEOUT_STATUS_CHECK`, `TIMEOUT_PROCESS_TERMINATE`, etc.) in `const.py`.

## Config flow validation
- Dashboard URLs, device names, and IP addresses are validated before saving, with specific error messages per failure type (bad scheme, invalid IP format, name too long, etc.).

## Minimum HA version enforced
- `manifest.json` now declares `homeassistant: 2025.2.0`, matching the actual minimum required for `ConfigSubentryFlow` and `SubentryFlowResult`.

## UI copy and helper text
- Time fields labelled as "Start casting at / Stop casting at" with "24-hour format" helper text throughout all device and global forms.
- Logging level dropdown includes guidance ("Use Warning normally, switch to Debug when troubleshooting").
- `reconfigure_successful` abort message no longer shows as a raw translation key.

## Code quality
- All `_LOGGER.debug(f"...")` f-string calls converted to `_LOGGER.debug("...", arg)` — strings are no longer evaluated when the log level is disabled.
- `os.makedirs` replaced with `pathlib.Path.mkdir` in `stats.py`.
- Docstrings with Args/Returns added to all public and non-trivial private functions across all modules.
- Service call examples in README corrected to use actual field names (`delay:`, `time:`, `level:`) rather than the generic `value:`.
