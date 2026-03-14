"""Sensor platform for Continuously Casting Dashboards integration."""

import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATUS_FILE

_LOGGER = logging.getLogger(__name__)

EVENT_STATUS_UPDATED = f"{DOMAIN}_status_updated"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up global summary sensors and per-device status sensors for the entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback used to register new sensor entities.
    """
    _LOGGER.debug("Setting up sensor platform for entry %s", entry.entry_id)

    # Get the integration instance from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Integration data not found for entry %s", entry.entry_id)
        return

    integration_data = hass.data[DOMAIN][entry.entry_id]
    caster = integration_data.get("caster")
    config = integration_data.get("config", {})

    if not caster:
        _LOGGER.error("Caster instance not found for entry %s", entry.entry_id)
        return

    devices = config.get("devices", {})
    _LOGGER.debug("Found %d devices to create sensors for", len(devices))

    entities = []

    # Create global summary sensors
    entities.extend([
        ContinuouslyCastingSummarySensor(
            hass, entry, "total_devices", "Total Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "connected_devices", "Connected Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "disconnected_devices", "Disconnected Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "media_playing_devices", "Media Playing"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "other_content_devices", "Other Content"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "assistant_active_devices", "Assistant Active"
        ),
    ])

    # Create a sensor for each device
    for device_name in devices.keys():
        entity = ContinuouslyCastingDeviceSensor(hass, entry, device_name)
        entities.append(entity)
        _LOGGER.debug("Created sensor for device: %s", device_name)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d sensor entities", len(entities))

        # Listen for status updates to refresh sensors
        @callback
        def on_status_update(event):
            """Refresh all sensors when status is updated."""
            _LOGGER.debug("Received status update event, refreshing sensors")
            for entity in entities:
                hass.async_create_task(entity._async_refresh_and_write())

        # Register the event listener
        entry.async_on_unload(
            hass.bus.async_listen(EVENT_STATUS_UPDATED, on_status_update)
        )
        _LOGGER.debug("Registered status update event listener")
    else:
        _LOGGER.warning("No sensor entities to add")


def _read_status_data() -> dict:
    """Read status data from file (synchronous, run in executor)."""
    try:
        if not os.path.exists(STATUS_FILE):
            return {}

        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        _LOGGER.debug("Error reading status file: %s", e)
        return {}


class ContinuouslyCastingSensorBase(SensorEntity):
    """Base class for Continuously Casting Dashboards sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the sensor base.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this sensor belongs to.
        """
        self.hass = hass
        self.entry = entry
        self._status_data = {}

    def _refresh_data(self):
        """Schedule a non-blocking refresh of status data in the background."""
        async def _do_refresh():
            """Read status data in an executor and update internal state."""
            try:
                self._status_data = await self.hass.async_add_executor_job(_read_status_data)
            except Exception as e:
                _LOGGER.debug("Error refreshing status data: %s", e)

        self.hass.async_create_task(_do_refresh())

    async def async_added_to_hass(self) -> None:
        """Fetch initial data when entity is added."""
        await self._async_refresh_and_write()

    async def _async_refresh_and_write(self) -> None:
        """Refresh data in executor and write state."""
        try:
            self._status_data = await self.hass.async_add_executor_job(_read_status_data)
        except Exception as e:
            _LOGGER.debug("Error refreshing status data: %s", e)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the sensor state."""
        await self._async_refresh_and_write()

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Continuously Casting Dashboards",
            "manufacturer": "Continuously Casting Dashboards",
            "model": "Integration",
        }

    @property
    def should_poll(self) -> bool:
        """Return False as we push updates."""
        return False


class ContinuouslyCastingSummarySensor(ContinuouslyCastingSensorBase):
    """Sensor for global summary statistics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, sensor_type: str, friendly_name: str):
        """Initialize the summary sensor.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this sensor belongs to.
            sensor_type: Key in the status data dict (e.g. 'connected_devices').
            friendly_name: Human-readable sensor name shown in the UI.
        """
        super().__init__(hass, entry)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sensor_type}"
        self._attr_has_entity_name = True
        self._attr_name = friendly_name
        self._refresh_data()

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._status_data.get(self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self._status_data:
            return None

        return {
            "last_updated": self._status_data.get("last_updated"),
        }


class ContinuouslyCastingDeviceSensor(ContinuouslyCastingSensorBase):
    """Sensor for individual device status.

    Provides detailed status information for each Chromecast device including:
    - Current casting status (connected, disconnected, media_playing, etc.)
    - Device IP address
    - Current dashboard URL (if casting)
    - Reconnection attempt count
    - Last check timestamp
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_name: str):
        """Initialize the device status sensor.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this sensor belongs to.
            device_name: The Chromecast device name as it appears in status data.
        """
        super().__init__(hass, entry)
        self._device_name = device_name
        # Create a sanitized version of device name for unique_id
        sanitized_name = device_name.replace(' ', '_').replace('-', '_').lower()
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sanitized_name}_status"
        self._attr_has_entity_name = True
        self._attr_name = f"{device_name} Status"
        self._refresh_data()

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        devices = self._status_data.get("devices", {})
        device_info = devices.get(self._device_name)
        if device_info:
            return device_info.get("status", "unknown")
        return "unknown"

    @property
    def icon(self) -> str:
        """Return the icon based on device status."""
        status = self.native_value
        if status == "connected":
            return "mdi:cast-connected"
        elif status == "disconnected":
            return "mdi:cast-off"
        elif status == "media_playing":
            return "mdi:cast-audio"
        elif status == "assistant_active":
            return "mdi:google-assistant"
        elif status == "speaker_group_active":
            return "mdi:speaker-multiple"
        elif status == "casting_in_progress":
            return "mdi:cast"
        else:
            return "mdi:cast"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        devices = self._status_data.get("devices", {})
        device_info = devices.get(self._device_name)
        if device_info:
            attrs = {
                "ip": device_info.get("ip", "Unknown"),
                "last_checked": device_info.get("last_checked", ""),
                "reconnect_attempts": device_info.get("reconnect_attempts", 0),
                "device_name": self._device_name,
            }
            # Add current dashboard if available
            current_dashboard = device_info.get("current_dashboard")
            if current_dashboard:
                attrs["current_dashboard"] = current_dashboard
            return attrs
        return None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category."""
        return EntityCategory.DIAGNOSTIC
