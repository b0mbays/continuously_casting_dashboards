"""Actionable Home Assistant Repairs for casting configuration errors.

Only problems needing user intervention create Repairs. Temporary receiver
outages and media playback are diagnostic states, *not* persistent Repairs.
"""

from __future__ import annotations

import shutil
from collections import Counter

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


def ambiguous_device_names(device_identifiers: dict) -> list[str]:
    """Return duplicate names without usable explicit IP addresses.

    Duplicate names are safe when configured with individual valid explicit
    IPs. Ambiguity matters only for name-based CATT discovery.
    """
    names = []
    for identifier in device_identifiers.values():
        name = (identifier.get("device_name") or "").strip().casefold()
        ip = (identifier.get("device_ip") or "").strip()
        if name and not ip:
            names.append(name)
    counts = Counter(names)
    return sorted(name for name, count in counts.items() if count > 1)


async def async_check_configuration_repairs(
    hass: HomeAssistant, entry: ConfigEntry, device_identifiers: dict
) -> None:
    """Create or remove actionable issues for this integration entry."""
    duplicate_issue = f"ambiguous_cast_name_{entry.entry_id}"
    conflicts = ambiguous_device_names(device_identifiers)
    if conflicts:
        ir.async_create_issue(
            hass,
            DOMAIN,
            duplicate_issue,
            config_entry_id=entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="ambiguous_cast_name",
            translation_placeholders={"count": str(len(conflicts))},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, duplicate_issue)

    catt_issue = f"catt_executable_missing_{entry.entry_id}"
    executable = await hass.async_add_executor_job(shutil.which, "catt")
    if executable is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            catt_issue,
            config_entry_id=entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="catt_executable_missing",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, catt_issue)
