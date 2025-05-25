"""Sensor platform for Continuously Casting Dashboards."""
from __future__ import annotations

import logging
from typing import Any, Optional
from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_CAST_DELAY,
    CONF_LOGGING_LEVEL,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_SWITCH_ENTITY_ID,
    CONF_SWITCH_ENTITY_STATE,
    DEFAULT_CAST_DELAY,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_START_TIME,
    DEFAULT_END_TIME,
    LOGGING_LEVELS,
)

_LOGGER = logging.getLogger(__name__)

def validate_time_format(value: str) -> str:
    """Validate time format (HH:MM)."""
    try:
        datetime.strptime(value, "%H:%M")
        return value
    except ValueError:
        raise vol.Invalid("Time must be in format HH:MM")

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    # Add all sensors
    sensors = [
        CastDelaySensor(hass, entry),
        LoggingLevelSensor(hass, entry),
        StartTimeSensor(hass, entry),
        EndTimeSensor(hass, entry),
    ]
    
    # Only add switch entity sensors if a switch is configured
    if entry.options.get(CONF_SWITCH_ENTITY_ID):
        sensors.extend([
            SwitchEntitySensor(hass, entry),
            SwitchStateSensor(hass, entry),
        ])
    
    async_add_entities(sensors)

    # Register services for all sensors
    platform = entity_platform.async_get_current_platform()
    
    # Cast delay service
    platform.async_register_entity_service(
        "set_cast_delay",
        {
            vol.Required("value"): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=300)
            ),
        },
        "async_set_cast_delay",
    )
    
    # Logging level service
    platform.async_register_entity_service(
        "set_logging_level",
        {
            vol.Required("value"): vol.In(LOGGING_LEVELS),
        },
        "async_set_logging_level",
    )
    
    # Start time service
    platform.async_register_entity_service(
        "set_start_time",
        {
            vol.Required("value"): vol.All(cv.string, validate_time_format),
        },
        "async_set_start_time",
    )
    
    # End time service
    platform.async_register_entity_service(
        "set_end_time",
        {
            vol.Required("value"): vol.All(cv.string, validate_time_format),
        },
        "async_set_end_time",
    )
    
    # Switch entity service
    platform.async_register_entity_service(
        "set_switch_entity",
        {
            vol.Required("value"): cv.entity_id,
        },
        "async_set_switch_entity",
    )
    
    # Switch state service
    platform.async_register_entity_service(
        "set_switch_state",
        {
            vol.Required("value"): cv.string,
        },
        "async_set_switch_state",
    )

class BaseConfigSensor(SensorEntity):
    """Base class for configuration sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the base sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Continuously Casting Dashboards",
            "manufacturer": "Custom Integration",
        }

    @callback
    def async_update_config_entry(self, entry: ConfigEntry) -> None:
        """Update the sensor when the config entry is updated."""
        self._update_from_config(entry)
        self.async_write_ha_state()

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        raise NotImplementedError

    async def _async_update_config(self, key: str, value: Any) -> None:
        """Update a configuration value."""
        new_options = dict(self._entry.options)
        new_options[key] = value
        
        # Update the entry
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options,
        )
        
        # Update the local value
        self._attr_native_value = value
        self.async_write_ha_state()
        
        # Reload the entry to apply the new value
        await self.hass.config_entries.async_reload(self._entry.entry_id)

class CastDelaySensor(BaseConfigSensor):
    """Sensor for the cast delay configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "Cast Delay"
        self._attr_unique_id = f"{entry.entry_id}_cast_delay"
        self._attr_native_unit_of_measurement = "s"
        self._attr_icon = "mdi:timer"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_CAST_DELAY, DEFAULT_CAST_DELAY)

    async def async_set_cast_delay(self, value: int) -> None:
        """Update the cast delay value."""
        await self._async_update_config(CONF_CAST_DELAY, value)

class LoggingLevelSensor(BaseConfigSensor):
    """Sensor for the logging level configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "Logging Level"
        self._attr_unique_id = f"{entry.entry_id}_logging_level"
        self._attr_icon = "mdi:file-document-edit"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_LOGGING_LEVEL, DEFAULT_LOGGING_LEVEL)

    async def async_set_logging_level(self, value: str) -> None:
        """Update the logging level value."""
        await self._async_update_config(CONF_LOGGING_LEVEL, value)

class StartTimeSensor(BaseConfigSensor):
    """Sensor for the start time configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "Start Time"
        self._attr_unique_id = f"{entry.entry_id}_start_time"
        self._attr_icon = "mdi:clock-start"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_START_TIME, DEFAULT_START_TIME)

    async def async_set_start_time(self, value: str) -> None:
        """Update the start time value."""
        await self._async_update_config(CONF_START_TIME, value)

class EndTimeSensor(BaseConfigSensor):
    """Sensor for the end time configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "End Time"
        self._attr_unique_id = f"{entry.entry_id}_end_time"
        self._attr_icon = "mdi:clock-end"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_END_TIME, DEFAULT_END_TIME)

    async def async_set_end_time(self, value: str) -> None:
        """Update the end time value."""
        await self._async_update_config(CONF_END_TIME, value)

class SwitchEntitySensor(BaseConfigSensor):
    """Sensor for the switch entity configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "Control Entity"
        self._attr_unique_id = f"{entry.entry_id}_switch_entity"
        self._attr_icon = "mdi:toggle-switch"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_SWITCH_ENTITY_ID, "")

    async def async_set_switch_entity(self, value: str) -> None:
        """Update the switch entity value."""
        # Validate that the entity exists
        if self.hass.states.get(value) is None:
            raise ValueError(f"Entity {value} not found")
        await self._async_update_config(CONF_SWITCH_ENTITY_ID, value)

class SwitchStateSensor(BaseConfigSensor):
    """Sensor for the switch state configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry)
        self._attr_name = "Required Entity State"
        self._attr_unique_id = f"{entry.entry_id}_switch_state"
        self._attr_icon = "mdi:state-machine"
        self._update_from_config(entry)

    def _update_from_config(self, entry: ConfigEntry) -> None:
        """Update the sensor value from config entry."""
        self._attr_native_value = entry.options.get(CONF_SWITCH_ENTITY_STATE, "")

    async def async_set_switch_state(self, value: str) -> None:
        """Update the switch state value."""
        await self._async_update_config(CONF_SWITCH_ENTITY_STATE, value) 