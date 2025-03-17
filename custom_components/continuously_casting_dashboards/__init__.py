"""Continuously Cast Dashboards"""
import logging
import asyncio
import os
from datetime import timedelta
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv

from .casting import CastingManager
from .device import DeviceManager
from .monitoring import MonitoringManager
from .stats import StatsManager
from .utils import TimeWindowChecker, SwitchEntityChecker
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

class ContinuouslyCastingDashboards:
    """Class to handle casting dashboards to Chromecast devices."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the dashboard caster."""
        self.hass = hass
        self.config = config
        self.running = True
        self.unsubscribe_listeners = []
        
        # Ensure directory exists
        os.makedirs('/config/continuously_casting_dashboards', exist_ok=True)
        
        # Set up logging based on config
        log_level = config.get('logging_level', 'INFO').upper()
        logging.getLogger(__name__).setLevel(getattr(logging, log_level))
        
        # Initialize managers
        self.device_manager = DeviceManager(hass, config)
        self.time_window_checker = TimeWindowChecker(config)
        self.switch_checker = SwitchEntityChecker(hass, config)
        self.casting_manager = CastingManager(hass, config, self.device_manager)
        self.monitoring_manager = MonitoringManager(
            hass, 
            config, 
            self.device_manager,
            self.casting_manager,
            self.time_window_checker,
            self.switch_checker
        )
        self.stats_manager = StatsManager(hass, config)
        
        # Share components between managers
        self.monitoring_manager.set_stats_manager(self.stats_manager)
    
    async def start(self):
        """Start the casting process."""
        _LOGGER.info("Starting Continuously Casting Dashboards integration")
        
        # Initial setup of devices
        await self.monitoring_manager.initialize_devices()
        
        # Set up recurring monitoring
        scan_interval = self.config.get(CONF_SCAN_INTERVAL, 30)
        self.unsubscribe_listeners.append(
            async_track_time_interval(
                self.hass, 
                self.monitoring_manager.async_monitor_devices, 
                timedelta(seconds=scan_interval)
            )
        )
        
        # Generate initial status
        await self.stats_manager.async_generate_status_data()
        
        # Schedule regular status updates
        self.unsubscribe_listeners.append(
            async_track_time_interval(
                self.hass,
                self.stats_manager.async_generate_status_data,
                timedelta(minutes=5)
            )
        )
        
        return True

    async def stop(self):
        """Stop the casting process."""
        _LOGGER.info("Stopping Continuously Casting Dashboards integration")
        self.running = False
        
        # Unsubscribe from all listeners
        for unsubscribe in self.unsubscribe_listeners:
            unsubscribe()
        
        return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Continuously Cast Dashboards integration."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True
    
    hass.data.setdefault(DOMAIN, {})
    
    # Start the ContinuouslyCastingDashboards
    caster = ContinuouslyCastingDashboards(hass, conf)
    hass.data[DOMAIN]['caster'] = caster
    
    hass.loop.create_task(caster.start())
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # This function would handle setup from the UI config flow
    # For now it's a placeholder for future development
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This function would handle teardown from the UI config flow
    # For now it's a placeholder for future development
    return True