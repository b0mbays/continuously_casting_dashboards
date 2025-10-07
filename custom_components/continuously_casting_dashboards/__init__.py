"""Continuously Cast Dashboards"""

import logging
import asyncio
import os
from datetime import timedelta
import voluptuous as vol
import json

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.helpers.storage import Store
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
    DEFAULT_END_TIME,
)

_LOGGER = logging.getLogger(__name__)

# Global lock to prevent concurrent setup of the same entry
_SETUP_LOCKS = {}

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Continuously Cast Dashboards component."""
    hass.data.setdefault(DOMAIN, {})

    # Simple file-based approach to track notification state
    storage_file = hass.config.path(f".{DOMAIN}_notification_state.json")
    _LOGGER.debug(f"Using storage file at: {storage_file}")
    
    notification_shown = False
    
    try:
        if os.path.exists(storage_file):
            with open(storage_file, 'r') as f:
                data = json.load(f)
                notification_shown = data.get('acknowledged', False)
    except Exception as ex:
        _LOGGER.debug(f"Error loading notification state: {ex}")

    if DOMAIN in config:
        _LOGGER.debug("Found YAML configuration for Continuously Cast Dashboards")
        
        # Check if we already have config entries for this domain to avoid conflicts
        existing_entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)]
        if existing_entries:
            _LOGGER.warning("Config entries already exist for %s, skipping YAML import to avoid conflicts", DOMAIN)
            return True

        # If notification hasn't been shown yet
        if not notification_shown:
            # Create persistent notification
            notification_id = f"{DOMAIN}_config_imported"
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Continuously Cast Dashboards Configuration Imported",
                    "message": (
                        "Your YAML configuration for Continuously Cast Dashboards has been imported into the UI configuration.\n\n"
                        "Please remove the configuration from your configuration.yaml file to avoid conflicts.\n\n"
                        "You can now manage your configuration through the UI. "
                        "Click DISMISS to prevent this message from appearing again."
                    ),
                    "notification_id": notification_id,
                },
            )
            
            # Log all events to see what's happening
            async def log_all_events(event):
                """Log all events to see what's happening."""
                # Any event that looks related to notifications
                if "notification" in event.event_type.lower():
                    # See if our notification_id appears anywhere in the event data
                    event_data_str = str(event.data)
                    if notification_id in event_data_str:
                        try:
                            # Save the acknowledged state regardless of the exact event type
                            with open(storage_file, 'w') as f:
                                json.dump({"acknowledged": True}, f)
                        except Exception as ex:
                            _LOGGER.debug(f"Failed to save acknowledged state: {ex}")
            
            # Listen for ALL events for diagnostic purposes
            remove_listener = hass.bus.async_listen("*", log_all_events)
            
            # Store the listener so it doesn't get garbage collected
            hass.data[DOMAIN]["remove_listener"] = remove_listener
            
            # Also create a one-time task to auto-acknowledge after 5 minutes
            # as a fallback in case the event system isn't working
            async def auto_acknowledge():
                """Automatically acknowledge after a timeout."""
                import asyncio
                await asyncio.sleep(300)  # 5 minutes
                
                # Check if we've already acknowledged
                try:
                    if os.path.exists(storage_file):
                        with open(storage_file, 'r') as f:
                            data = json.load(f)
                            if data.get('acknowledged', False):
                                return  # Already acknowledged, nothing to do
                    
                    # Not acknowledged yet, do it now
                    _LOGGER.debug("Auto-acknowledging notification after timeout")
                    with open(storage_file, 'w') as f:
                        json.dump({"acknowledged": True}, f)
                except Exception as ex:
                    _LOGGER.debug(f"Error in auto-acknowledge: {ex}")
            
            # Start the auto-acknowledge task
            hass.async_create_task(auto_acknowledge())
        else:
            _LOGGER.debug("Notification was previously acknowledged, skipping")

        # Forward the YAML config to the config flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Continuously Casting Dashboards from a config entry."""
    # Get or create a lock for this specific entry
    if entry.entry_id not in _SETUP_LOCKS:
        _SETUP_LOCKS[entry.entry_id] = asyncio.Lock()
    
    async with _SETUP_LOCKS[entry.entry_id]:
        _LOGGER.debug("=== SETUP ENTRY START (LOCKED): %s (ID: %s) ===", entry.title, entry.entry_id)
        
        try:
            # Check if this entry is already set up
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                existing_data = hass.data[DOMAIN][entry.entry_id]
                _LOGGER.debug("Entry %s already exists in hass.data: %s", entry.entry_id, existing_data)
                # If platforms are already set up, we really shouldn't continue
                if existing_data.get("platforms_setup", False):
                    _LOGGER.debug("Platforms already set up for entry %s, aborting setup", entry.entry_id)
                    return True
                else:
                    _LOGGER.debug("Entry exists but platforms not set up, cleaning up first")
                    # Clean up the incomplete setup
                    if "caster" in existing_data:
                        await existing_data["caster"].stop()
                    del hass.data[DOMAIN][entry.entry_id]

            # Register update listener
            entry.async_on_unload(entry.add_update_listener(async_reload_entry))
            entry.async_on_unload(entry.add_update_listener(async_migrate_entry))
            
            # Merge data from config entry with options
            config = dict(entry.data)
            config.update(entry.options)
            _LOGGER.debug("Merged config: %s", config)

            # Extract configuration with fallback to defaults
            logging_level = config.get("logging_level", DEFAULT_LOGGING_LEVEL)
            cast_delay = config.get("cast_delay", DEFAULT_CAST_DELAY)
            start_time = config.get("start_time", DEFAULT_START_TIME)
            end_time = config.get("end_time", DEFAULT_END_TIME)
            devices = config.get("devices", {})

            # Ensure directory exists
            os.makedirs("/config/continuously_casting_dashboards", exist_ok=True)

            # Set up logging based on config
            log_level = logging_level.upper()
            logging.getLogger(__name__).setLevel(getattr(logging, log_level))

            # Set the scan interval from cast_delay
            config[CONF_SCAN_INTERVAL] = cast_delay

            # Initialize the Continuously Casting Dashboards instance
            _LOGGER.debug("Creating ContinuouslyCastingDashboards instance")
            caster = ContinuouslyCastingDashboards(hass, config)

            # Store the caster in domain data with entry_id to support multiple entries
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][entry.entry_id] = {"caster": caster, "config": config, "platforms_setup": False}

            # 🚀 FAST CORE STARTUP - only essential services, no device discovery
            _LOGGER.debug("Starting core services...")
            try:
                # Start core services only (no device initialization)
                await asyncio.wait_for(caster.start_core(), timeout=10)  # Quick 10-second timeout
                _LOGGER.debug("Core services started successfully")
                
                # Set up platforms (including sensor platform)
                _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
                await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                _LOGGER.debug("Successfully set up all platforms")
                
                hass.data[DOMAIN][entry.entry_id]["platforms_setup"] = True
                _LOGGER.debug("Platforms setup completed")
                
                # 🚀 START BACKGROUND DEVICE INITIALIZATION - doesn't block integration loading
                _LOGGER.info("Integration loaded successfully, starting device initialization in background...")
                hass.async_create_task(caster.start_background_initialization())
                
                _LOGGER.info("Entry %s setup completed successfully", entry.entry_id)
                return True
                
            except asyncio.TimeoutError:
                _LOGGER.error("Core initialization timed out for entry %s", entry.entry_id)
                # Clean up on timeout
                if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                    del hass.data[DOMAIN][entry.entry_id]
                return False
                
            except Exception as e:
                _LOGGER.error("Error in async_setup_entry: %s", str(e), exc_info=True)
                # Clean up on error
                if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                    del hass.data[DOMAIN][entry.entry_id]
                raise
                
        finally:
            _LOGGER.debug("=== SETUP ENTRY END: %s ===", entry.entry_id)

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Comprehensive entry reload mechanism."""
    _LOGGER.info(f"Reloading entry {entry.entry_id}")
    
    try:
        # 1. Merge current data and options
        config = dict(entry.data)
        config.update(entry.options)
        _LOGGER.debug(f"Reloading with config: {config}")
        _LOGGER.debug(f"Options before reload: {entry.options}")

        # 2. Stop existing integration instance and unload platforms
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            current_instance = hass.data[DOMAIN][entry.entry_id].get("caster")
            if current_instance:
                await current_instance.stop()
            
            # Unload all platforms first
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            _LOGGER.debug("Unloaded all platforms")

            # Remove the current entry data
            del hass.data[DOMAIN][entry.entry_id]

        # 3. Create and start new instance
        new_instance = ContinuouslyCastingDashboards(hass, config)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "caster": new_instance, 
            "config": config,
            "platforms_setup": False  # Reset platform setup flag
        }

        # Start the new instance (core services only)
        try:
            await asyncio.wait_for(new_instance.start_core(), timeout=10)  # Fast core startup
            
            # 4. Set up platforms fresh
            _LOGGER.debug("Setting up platforms after reload")
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            _LOGGER.debug("Successfully set up all platforms")
            
            hass.data[DOMAIN][entry.entry_id]["platforms_setup"] = True
            _LOGGER.info(f"Successfully reloaded integration for entry {entry.entry_id}")
            _LOGGER.debug(f"Options after reload: {entry.options}")
            
            # Start background initialization after reload
            hass.async_create_task(new_instance.start_background_initialization())
            
        except asyncio.TimeoutError:
            _LOGGER.error(f"Reload timed out for entry {entry.entry_id}")
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                del hass.data[DOMAIN][entry.entry_id]
            raise
        except Exception as e:
            _LOGGER.error(f"Error during reload: {str(e)}", exc_info=True)
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                del hass.data[DOMAIN][entry.entry_id]
            raise
    except Exception as ex:
        _LOGGER.error(f"Reload failed: {ex}")
        _LOGGER.exception("Detailed reload failure traceback:")
        raise

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading entry %s", entry.entry_id)

    try:
        # Unload all platforms first
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.debug("Unloaded all platforms")

        # Stop the existing caster if it exists
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            caster = hass.data[DOMAIN][entry.entry_id]["caster"]
            await caster.stop()

            # Remove the entry from domain data
            del hass.data[DOMAIN][entry.entry_id]

        # Clean up the setup lock for this entry
        if entry.entry_id in _SETUP_LOCKS:
            del _SETUP_LOCKS[entry.entry_id]

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
        self.started = False  # Add flag to prevent multiple starts
        self.core_started = False  # Add flag for core services
        self.background_started = False  # Add flag for background initialization
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
            self.switch_checker,
        )
        self.stats_manager = StatsManager(hass, config)

        # Share components between managers
        self.monitoring_manager.set_stats_manager(self.stats_manager)

    async def start_core(self):
        """Start core services only - fast startup for integration loading."""
        if self.core_started:
            _LOGGER.warning("Core services already started, skipping duplicate start")
            return True
            
        _LOGGER.info("Starting core services - Instance ID: %s", id(self))
        self.core_started = True

        try:
            # Set up recurring monitoring (but don't initialize devices yet)
            _LOGGER.debug("Setting up recurring monitoring - Scan interval: %s seconds", self.config.get(CONF_SCAN_INTERVAL, 30))
            scan_interval = self.config.get(CONF_SCAN_INTERVAL, 30)
            recurring_listener = async_track_time_interval(
                self.hass,
                self.monitoring_manager.async_monitor_devices,
                timedelta(seconds=scan_interval),
            )
            self.unsubscribe_listeners.append(recurring_listener)
            _LOGGER.debug("Recurring monitoring listener created: %s", id(recurring_listener))

            # Schedule regular status updates
            _LOGGER.debug("Setting up regular status updates")
            status_listener = async_track_time_interval(
                self.hass,
                self.stats_manager.async_generate_status_data,
                timedelta(minutes=5),
            )
            self.unsubscribe_listeners.append(status_listener)
            _LOGGER.debug("Status update listener created: %s", id(status_listener))

            # Mark core services as complete
            _LOGGER.info("Core services started successfully - Total listeners: %s", len(self.unsubscribe_listeners))
            return True
        except Exception as e:
            _LOGGER.error("Error in start_core(): %s", str(e), exc_info=True)
            raise

    async def start_background_initialization(self):
        """Start background device initialization - doesn't block integration loading."""
        if self.background_started:
            _LOGGER.warning("Background initialization already started, skipping duplicate start")
            return True
            
        _LOGGER.info("Starting background device initialization")
        self.background_started = True

        try:
            # Initial setup of devices - this can take time but doesn't block integration
            _LOGGER.debug("Starting device initialization in background")
            try:
                await asyncio.wait_for(
                    self.monitoring_manager.initialize_devices(),
                    timeout=45,  # 45 second timeout for initial device setup
                )
                _LOGGER.info("Background device initialization completed successfully")
            except asyncio.TimeoutError:
                _LOGGER.warning("Background device initialization timed out, continuing anyway")
            except Exception as e:
                _LOGGER.error("Error during background device initialization: %s", str(e), exc_info=True)
                # Don't raise - let the integration continue working

            # Generate initial status
            _LOGGER.debug("Generating initial status in background")
            try:
                await self.stats_manager.async_generate_status_data()
                _LOGGER.debug("Initial status generation completed")
            except Exception as e:
                _LOGGER.error("Error generating initial status: %s", str(e), exc_info=True)
                # Don't raise - let the integration continue working

            # Trigger an immediate monitoring run
            _LOGGER.debug("Triggering immediate monitoring run in background")
            monitoring_task = self.hass.async_create_task(self.monitoring_manager.async_monitor_devices(None))
            _LOGGER.debug("Immediate monitoring task created: %s", id(monitoring_task))

            # Mark background initialization as complete
            _LOGGER.info("Background initialization complete - integration fully operational")
            return True
        except Exception as e:
            _LOGGER.error("Error in background initialization: %s", str(e), exc_info=True)
            # Don't raise - let the integration continue working even if background init fails

    async def start(self):
        """Legacy start method for backward compatibility - now calls start_core."""
        return await self.start_core()

    async def stop(self):
        """Stop the casting process."""
        _LOGGER.info("Stopping Continuously Casting Dashboards integration")
        self.running = False
        self.started = False
        self.core_started = False
        self.background_started = False

        # Unsubscribe from all listeners
        for unsubscribe in self.unsubscribe_listeners:
            unsubscribe()
        
        # Clear the listeners list
        self.unsubscribe_listeners.clear()

        return True