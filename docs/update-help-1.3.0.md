# Historical migration note — version 1.3.0

> **Archived for legacy YAML installations only.** This note explains the v1.3.0 change from one `dashboard_url` mapping per device to a **list** of dashboard entries. It is not an instruction to reinstall the integration or remove your current UI settings. For present-day upgrades, including PRs #2–#6 and the CATT 0.13.3 candidate, use [the current upgrade guide](update_help.md), [README](../README.md), and [roadmap](../ROADMAP.md).

In old YAML configurations the device had one dashboard mapping:

```yaml
continuously_casting_dashboards:
  devices:
    "Living Room Display":
      dashboard_url: "http://192.168.1.100:8123/lovelace/home"
      volume: 5
      start_time: "07:00"
      end_time: "01:00"
```

Starting with the v1.3.0 YAML list layout, a device's dashboards use a leading `-`:

```yaml
continuously_casting_dashboards:
  devices:
    "Living Room Display":
      - dashboard_url: "http://192.168.1.100:8123/lovelace/home"
        volume: 5
        start_time: "07:00"
        end_time: "01:00"
      - dashboard_url: "http://192.168.1.100:8123/lovelace/alternate"
        cast_continuously: true
        preserve_volume: true
```

The current integration also supports an options/config-entry UI, independent dashboard rules, priorities, optional rotation and other post-v1.3.0 functionality. **Do not assume that omitting `volume` preserves the receiver volume.** Use `preserve_volume: true` explicitly when you want CCD to avoid changing volume.

Before editing any legacy YAML, create a Home Assistant backup and confirm which repository and version are installed.
