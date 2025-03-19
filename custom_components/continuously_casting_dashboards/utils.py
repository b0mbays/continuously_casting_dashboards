"""Utility functions for Continuously Casting Dashboards."""
import logging
from datetime import time as dt_time, datetime
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from .const import DEFAULT_START_TIME, DEFAULT_END_TIME, CONF_SWITCH_ENTITY

_LOGGER = logging.getLogger(__name__)

class TimeWindowChecker:
    """Class to handle time window checking."""
    
    def __init__(self, config: dict):
        """Initialize the time window checker."""
        self.config = config
        self.default_start_time = config.get('start_time', DEFAULT_START_TIME)
        self.default_end_time = config.get('end_time', DEFAULT_END_TIME)
    
    async def async_is_within_time_window(self, device_name, device_config):
        """Check if current time is within the casting window for a device."""
        now = dt_util.now().time()
        
        # First check device-specific time window
        device_start = device_config.get('start_time', self.default_start_time)
        device_end = device_config.get('end_time', self.default_end_time)
        
        # Parse times to time objects
        try:
            start_time = dt_time(*map(int, device_start.split(':')))
            end_time = dt_time(*map(int, device_end.split(':')))
        except Exception as e:
            _LOGGER.error(f"Error parsing time window for {device_name}: {str(e)}")
            return True  # Default to casting if time parsing fails
        
        # Check if casting should be active now
        if start_time <= end_time:
            # Simple case: start_time is before end_time in the same day
            return start_time <= now <= end_time
        else:
            # Complex case: time window spans midnight
            return now >= start_time or now <= end_time
            
    def get_current_device_config(self, device_name, device_configs):
        """Get the current device configuration based on the current time window."""
        now = dt_util.now().time()
        
        # Try to find a config whose time window includes the current time
        for config in device_configs:
            device_start = config.get('start_time', self.default_start_time)
            device_end = config.get('end_time', self.default_end_time)
            
            # Parse times to time objects
            try:
                start_time = dt_time(*map(int, device_start.split(':')))
                end_time = dt_time(*map(int, device_end.split(':')))
            except Exception as e:
                _LOGGER.error(f"Error parsing time window for {device_name}: {str(e)}")
                continue
            
            # Check if the current time is within this window
            is_in_window = False
            if start_time <= end_time:
                # Simple case: start_time is before end_time in the same day
                is_in_window = start_time <= now <= end_time
            else:
                # Complex case: time window spans midnight
                is_in_window = now >= start_time or now <= end_time
                
            if is_in_window:
                _LOGGER.debug(f"Found matching time window for {device_name}: {start_time}-{end_time}")
                # Add the parsed time objects to the config for convenience
                config['parsed_start_time'] = start_time
                config['parsed_end_time'] = end_time
                return config, True
        
        # If no matching time window is found, return the first config as default (with an indicator that no match was found)
        if device_configs:
            _LOGGER.debug(f"No matching time window for {device_name}, using first config as default")
            return device_configs[0], False
        
        # If no configs at all, return None
        return None, False


class SwitchEntityChecker:
    """Class to handle switch entity checking."""
    
    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the switch entity checker."""
        self.hass = hass
        self.switch_entity_id = config.get(CONF_SWITCH_ENTITY)
        
        # Immediately log the switch entity config for diagnostics
        if self.switch_entity_id:
            _LOGGER.debug(f"SWITCH ENTITY CONFIGURED: {self.switch_entity_id}")
            
            # Check if the entity exists in Home Assistant
            state = self.hass.states.get(self.switch_entity_id)
            if state is None:
                _LOGGER.error(f"CRITICAL: Switch entity {self.switch_entity_id} NOT FOUND in Home Assistant!")
            else:
                _LOGGER.debug(f"SWITCH ENTITY CURRENT STATE: {state.state}")
        else:
            _LOGGER.debug("NO SWITCH ENTITY CONFIGURED - Casting will always be enabled")
            
        # Also log the raw config for debugging
        if 'switch_entity_id' in config:
            _LOGGER.debug(f"Found 'switch_entity_id' in config with value: {config['switch_entity_id']}")
        else:
            _LOGGER.debug("'switch_entity_id' not found in raw config. Check your configuration.yaml syntax.")
    
    async def async_check_switch_entity(self):
        """Check if the switch entity is enabled (if configured)."""
        if not self.switch_entity_id:
            return True  # No switch configured, always enabled
        
        state = self.hass.states.get(self.switch_entity_id)
        if state is None:
            _LOGGER.debug(f"Switch entity {self.switch_entity_id} not found in Home Assistant states")
            return True  # If entity doesn't exist, default to enabled
        
        is_enabled = state.state == 'on'
        _LOGGER.debug(f"Continuously Casting Dashbords - Switch Entity: {self.switch_entity_id} state = {state.state}, casting enabled: {is_enabled}")
        return is_enabled