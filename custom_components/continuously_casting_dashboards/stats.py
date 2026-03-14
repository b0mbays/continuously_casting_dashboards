"""Statistics handling for Continuously Casting Dashboards."""
import json
import logging
from datetime import datetime
from pathlib import Path
from homeassistant.core import HomeAssistant
from .const import (
    DOMAIN,
    HEALTH_STATS_FILE,
    STATUS_FILE,
    EVENT_CONNECTION_ATTEMPT,
    EVENT_CONNECTION_SUCCESS,
    EVENT_DISCONNECTED,
    EVENT_RECONNECT_ATTEMPT,
    EVENT_RECONNECT_SUCCESS,
    EVENT_RECONNECT_FAILED,
    STATUS_ASSISTANT_ACTIVE,
)

_LOGGER = logging.getLogger(__name__)

EVENT_STATUS_UPDATED = f"{DOMAIN}_status_updated"


class StatsManager:
    """Class to handle statistics for the integration."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the statistics manager.

        Args:
            hass: The Home Assistant instance.
            config: The integration configuration dictionary.
        """
        self.hass = hass
        self.config = config
        self.health_stats = {}
        self.device_manager = None  # Will be set later

        # Ensure directory exists
        Path('/config/continuously_casting_dashboards').mkdir(parents=True, exist_ok=True)

    def set_device_manager(self, device_manager):
        """Set the device manager reference.

        Args:
            device_manager: The DeviceManager instance to use for status queries.
        """
        self.device_manager = device_manager
    
    async def async_update_health_stats(self, device_key, event_type):
        """Increment health counters for a device event and persist to disk.

        Args:
            device_key: The device identifier string used as the stats key.
            event_type: One of the EVENT_* constants (e.g. EVENT_CONNECTION_ATTEMPT).
        """
        if device_key not in self.health_stats:
            self.health_stats[device_key] = {
                'first_seen': datetime.now().isoformat(),
                'connection_attempts': 0,
                'successful_connections': 0,
                'disconnections': 0,
                'reconnect_attempts': 0,
                'successful_reconnects': 0,
                'failed_reconnects': 0,
                'uptime_seconds': 0,
                'last_connection': None,
                'last_disconnection': None
            }
        
        now = datetime.now().isoformat()
        
        if event_type == EVENT_CONNECTION_ATTEMPT:
            self.health_stats[device_key]['connection_attempts'] += 1
        elif event_type == EVENT_CONNECTION_SUCCESS:
            self.health_stats[device_key]['successful_connections'] += 1
            self.health_stats[device_key]['last_connection'] = now
        elif event_type == EVENT_DISCONNECTED:
            self.health_stats[device_key]['disconnections'] += 1
            self.health_stats[device_key]['last_disconnection'] = now
        elif event_type == EVENT_RECONNECT_ATTEMPT:
            self.health_stats[device_key]['reconnect_attempts'] += 1
        elif event_type == EVENT_RECONNECT_SUCCESS:
            self.health_stats[device_key]['successful_reconnects'] += 1
            self.health_stats[device_key]['last_connection'] = now
        elif event_type == EVENT_RECONNECT_FAILED:
            self.health_stats[device_key]['failed_reconnects'] += 1
        
        # Save health stats to file
        try:
            def write_health_stats():
                """Write the current health_stats dict to the JSON file."""
                Path('/config/continuously_casting_dashboards').mkdir(parents=True, exist_ok=True)
                with open(HEALTH_STATS_FILE, 'w') as f:
                    json.dump(self.health_stats, f, indent=2)
                    
            await self.hass.async_add_executor_job(write_health_stats)
        except Exception as e:
            _LOGGER.error("Failed to save health stats: %s", e)

    async def async_generate_status_data(self, *args):
        """Build a status snapshot, write it to disk, and fire a sensor-refresh event.

        Returns:
            A dict with aggregate counts and per-device status details,
            or an empty dict if the device manager is not yet set.
        """
        if not self.device_manager:
            _LOGGER.warning("Device manager not set in StatsManager")
            return {}
            
        active_devices = self.device_manager.get_all_active_devices()
        
        connected_count = sum(1 for d in active_devices.values() if d.get('status') == 'connected')
        disconnected_count = sum(1 for d in active_devices.values() if d.get('status') == 'disconnected')
        media_playing_count = sum(1 for d in active_devices.values() if d.get('status') == 'media_playing')
        other_content_count = sum(1 for d in active_devices.values() if d.get('status') == 'other_content')
        assistant_active_count = sum(1 for d in active_devices.values() if d.get('status') == STATUS_ASSISTANT_ACTIVE)
        
        # Format for Home Assistant sensors
        status_data = {
            'total_devices': len(active_devices),
            'connected_devices': connected_count,
            'disconnected_devices': disconnected_count,
            'media_playing_devices': media_playing_count,
            'other_content_devices': other_content_count,
            'assistant_active_devices': assistant_active_count,
            'last_updated': datetime.now().isoformat(),
            'devices': {}
        }
        
        for device_key, device in active_devices.items():
            device_name = device.get('name', 'Unknown')
            ip = device.get('ip', 'Unknown')

            device_data = {
                'ip': ip,
                'status': device.get('status', 'unknown'),
                'last_checked': device.get('last_checked', ''),
                'reconnect_attempts': device.get('reconnect_attempts', 0)
            }

            # Include current dashboard URL if available
            current_dashboard = device.get('current_dashboard')
            if current_dashboard:
                device_data['current_dashboard'] = current_dashboard

            status_data['devices'][device_name] = device_data
        
        # Save status data to file for Home Assistant
        try:
            def write_status_file():
                """Write the current status_data dict to the JSON file."""
                Path('/config/continuously_casting_dashboards').mkdir(parents=True, exist_ok=True)
                with open(STATUS_FILE, 'w') as f:
                    json.dump(status_data, f, indent=2)

            await self.hass.async_add_executor_job(write_status_file)

            # Fire event to refresh sensors
            self.hass.bus.async_fire(EVENT_STATUS_UPDATED, {"status_data": status_data})
            _LOGGER.debug("Fired status update event for sensor refresh")
        except Exception as e:
            _LOGGER.error("Failed to save status data: %s", e)

        return status_data
