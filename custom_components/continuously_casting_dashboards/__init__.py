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
from .config_flow import async_migrate_entry
from .const import (
    DOMAIN, 
    PLATFORMS, 
    CONF_CAST_DELAY, 
    CONF_LOGGING_LEVEL,
    DEFAULT_CAST_DELAY,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_START_TIME,
    DEFAULT_END_TIME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Continuously Cast Dashboards component."""
    _LOGGER.debug("Setting up Continuously Cast Dashboards integration")
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Continuously Cast Dashboards from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    # Register migration handler in async_setup_entry, not async_setup
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    entry.async_on_unload(entry.add_update_listener(async_migrate_entry))
    # Merge data from config entry with options
    config = dict(entry.data)
    config.update(entry.options)
    
    # Extract configuration with fallback to defaults
    logging_level = config.get('logging_level', DEFAULT_LOGGING_LEVEL)
    cast_delay = config.get('cast_delay', DEFAULT_CAST_DELAY)
    start_time = config.get('start_time', DEFAULT_START_TIME)
    end_time = config.get('end_time', DEFAULT_END_TIME)
    devices = config.get('devices', {})
    
    # Ensure directory exists
    os.makedirs('/config/continuously_casting_dashboards', exist_ok=True)
    
    # Set up logging based on config
    log_level = logging_level.upper()
    logging.getLogger(__name__).setLevel(getattr(logging, log_level))
    
    # Set the scan interval from cast_delay
    config[CONF_SCAN_INTERVAL] = cast_delay
    
    # Initialize the Continuously Casting Dashboards instance
    caster = ContinuouslyCastingDashboards(hass, config)
    
    # Store the caster in domain data with entry_id to support multiple entries
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        'caster': caster,
        'config': config
    }
    
    # Start the caster
    start_task = asyncio.create_task(caster.start())
    
    # Register update listener to handle option updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    try:
        # Wait for initialization with a timeout
        result = await asyncio.wait_for(start_task, timeout=60)  # 60 seconds timeout
        _LOGGER.info("Entry %s setup completed with result: %s", entry.entry_id, result)
        return result
    except asyncio.TimeoutError:
        _LOGGER.warning("Initialization timed out for entry %s, but continuing anyway", entry.entry_id)
        return True  # Continue even if initialization times out

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Comprehensive entry reload mechanism."""
    _LOGGER.debug(f"Reloading entry {entry.entry_id}")
    _LOGGER.debug(f"Reloading with config: {config}")
    _LOGGER.debug(f"Options before reload: {entry.options}")
    try:
        # 1. Merge current data and options
        config = dict(entry.data)
        config.update(entry.options)
        
        # 2. Stop existing integration instance
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            current_instance = hass.data[DOMAIN][entry.entry_id].get('caster')
            if current_instance:
                await current_instance.stop()
            
            # Remove the current entry data
            del hass.data[DOMAIN][entry.entry_id]
        
        # 3. Create and start new instance
        new_instance = ContinuouslyCastingDashboards(hass, config)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            'caster': new_instance,
            'config': config
        }
        
        # Start the new instance
        await new_instance.start()
        
        _LOGGER.info(f"Successfully reloaded integration for entry {entry.entry_id}")
        _LOGGER.debug(f"Options after reload: {entry.options}")
    except Exception as ex:
        _LOGGER.error(f"Reload failed: {ex}")
        # Consider adding this line to help with debugging:
        _LOGGER.exception("Detailed reload failure traceback:")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading entry %s", entry.entry_id)
    
    try:
        # Stop the existing caster if it exists
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            caster = hass.data[DOMAIN][entry.entry_id]['caster']
            await caster.stop()
            
            # Remove the entry from domain data
            del hass.data[DOMAIN][entry.entry_id]
        
        return True
    except Exception as ex:
        _LOGGER.error(f"Error unloading entry: {ex}")
        return False

class ContinuouslyCastingDashboards:
    """Class to handle casting dashboards to Chromecast devices."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the dashboard caster."""
        _LOGGER.debug(f"Initializing with config: {config}")
        _LOGGER.debug(f"Devices from config: {config.get('devices', {})}")
        self.hass = hass
        self.config = config
        self.running = True
        self.unsubscribe_listeners = []
        
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
        
        # Initial setup of devices - each device may take a while to discover
        try:
            await asyncio.wait_for(
                self.monitoring_manager.initialize_devices(),
                timeout=45  # 45 second timeout for initial device setup
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Device initialization timed out, continuing with setup")
        
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
        
        # Trigger an immediate monitoring run in a separate task
        self.hass.async_create_task(self.monitoring_manager.async_monitor_devices(None))
        
        # Mark initialization as complete
        _LOGGER.info("Continuously Casting Dashboards initialization complete")
        return True

    async def stop(self):
        """Stop the casting process."""
        _LOGGER.info("Stopping Continuously Casting Dashboards integration")
        self.running = False
        
        # Unsubscribe from all listeners
        for unsubscribe in self.unsubscribe_listeners:
            unsubscribe()
        
        return True