"""Diagnostics for Continuously Casting Dashboards.

Only runtime facts are returned. Dashboard URLs, authentication tokens,
remote identifiers, and Home Assistant config entry secrets are excluded.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return non-sensitive runtime health data for troubleshooting."""
    integration = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    caster = integration.get("caster")
    if caster is None:
        return {"state": "not_loaded"}

    device_manager = caster.device_manager
    monitor = caster.monitoring_manager
    details = []
    for device_name, configs in monitor.devices.items():
        statuses = [
            value for value in device_manager.active_devices.values()
            if value.get("name") == device_name
        ]
        status = statuses[0] if statuses else {}
        key = f"{device_name}_{status.get('ip', '')}"
        details.append({
            "name": device_name,
            "dashboard_count": len(configs),
            "status": status.get("status", "unknown"),
            "last_checked": status.get("last_checked"),
            "reconnect_attempts": status.get("reconnect_attempts", 0),
            "retry_in_seconds": round(monitor.reconnect_backoff.remaining(key)),
            "last_error": status.get("last_error"),
            "frontend_readiness": caster.readiness_tracker.snapshot(device_name),
            "cast_frontend": caster.frontend_diagnostics.snapshot(device_name),
        })

    return {
        "state": "loaded",
        "device_count": len(monitor.devices),
        "configured_interval_seconds": caster.config.get("scan_interval"),
        "discovered_devices": len(device_manager._scan_devices),
        "last_discovery_at": device_manager.last_scan_at,
        "discovery_had_error": device_manager.last_discovery_error is not None,
        "devices": details,
    }
