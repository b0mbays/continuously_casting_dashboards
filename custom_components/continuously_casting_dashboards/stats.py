"""Statistics handling for Continuously Casting Dashboards."""
import json
import logging
import os
from datetime import datetime
from homeassistant.core import HomeAssistant
from .const import (
    HEALTH_STATS_FILE, 
    STATUS_FILE,
    EVENT_CONNECTION_ATTEMPT, 
    EVENT_CONNECTION_SUCCESS,
    EVENT_DISCONNECTED, 
    EVENT_RECONNECT_ATTEMPT,
    EVENT_RECONNECT_SUCCESS, 
    EVENT_RECONNECT_FAILED
)

_LOGGER = logging.getLogger(__name__)

class StatsManager:
    """Class to handle statistics for the integration."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the statistics manager."""
        self.hass = hass
        self.config = config
        self.health_stats = {}
        self.device_manager = None  # Will be set later
        
        # Ensure directory exists
        os.makedirs('/config/continuously_casting_dashboards', exist_ok=True)
    
    def set_device_manager(self, device_manager):
        """Set the device manager reference."""
        self.device_manager = device_manager
    
    async def async_update_health_stats(self, device_key, event_type):
        """Update health statistics for a device."""
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
                os.makedirs('/config/continuously_casting_dashboards', exist_ok=True)
                with open(HEALTH_STATS_FILE, 'w') as f:
                    json.dump(self.health_stats, f, indent=2)
                    
            await self.hass.async_add_executor_job(write_health_stats)
        except Exception as e:
            _LOGGER.error(f"Failed to save health stats: {str(e)}")

    async def async_generate_status_data(self, *args):
        """Generate status data for Home Assistant sensors."""
        if not self.device_manager:
            _LOGGER.warning("Device manager not set in StatsManager")
            return {}
            
        active_devices = self.device_manager.get_all_active_devices()
        
        connected_count = sum(1 for d in active_devices.values() if d.get('status') == 'connected')
        disconnected_count = sum(1 for d in active_devices.values() if d.get('status') == 'disconnected')
        media_playing_count = sum(1 for d in active_devices.values() if d.get('status') == 'media_playing')
        other_content_count = sum(1 for d in active_devices.values() if d.get('status') == 'other_content')
        
        # Format for Home Assistant sensors
        status_data = {
            'total_devices': len(active_devices),
            'connected_devices': connected_count,
            'disconnected_devices': disconnected_count,
            'media_playing_devices': media_playing_count,
            'other_content_devices': other_content_count,
            'last_updated': datetime.now().isoformat(),
            'devices': {}
        }
        
        for device_key, device in active_devices.items():
            device_name = device.get('name', 'Unknown')
            ip = device.get('ip', 'Unknown')
            
            status_data['devices'][device_name] = {
                'ip': ip,
                'status': device.get('status', 'unknown'),
                'last_checked': device.get('last_checked', ''),
                'reconnect_attempts': device.get('reconnect_attempts', 0)
            }
        
        # Save status data to file for Home Assistant
        try:
            def write_status_file():
                os.makedirs('/config/continuously_casting_dashboards', exist_ok=True)
                with open(STATUS_FILE, 'w') as f:
                    json.dump(status_data, f, indent=2)
                    
            await self.hass.async_add_executor_job(write_status_file)
        except Exception as e:
            _LOGGER.error(f"Failed to save status data: {str(e)}")
            
        return status_data