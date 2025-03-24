"""Monitoring functionality for Continuously Casting Dashboards."""
import asyncio
import logging
import time
from datetime import datetime
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_DEVICES
from homeassistant.helpers.event import async_track_state_change_event
from .const import (
    EVENT_CONNECTION_ATTEMPT, 
    EVENT_CONNECTION_SUCCESS, 
    EVENT_RECONNECT_ATTEMPT, 
    EVENT_RECONNECT_SUCCESS, 
    EVENT_RECONNECT_FAILED,
    STATUS_CASTING_IN_PROGRESS,
    CONF_SWITCH_ENTITY
)

_LOGGER = logging.getLogger(__name__)

class MonitoringManager:
    """Class to handle device monitoring and reconnection."""

    def __init__(self, hass: HomeAssistant, config: dict, device_manager, casting_manager, 
                 time_window_checker, switch_checker):
        """Initialize the monitoring manager."""
        self.hass = hass
        self.config = config
        self.device_manager = device_manager
        self.casting_manager = casting_manager
        self.time_window_checker = time_window_checker
        self.switch_checker = switch_checker
        self.stats_manager = None  # Will be set later
        self.devices = config.get(CONF_DEVICES, {})
        self.cast_delay = config.get('cast_delay', 0)
        self.active_device_configs = {}  # Track which dashboard config is active for each device
        self.monitor_lock = asyncio.Lock()  # Lock to prevent monitoring cycle overlap
        
        # Set up switch entity state change listener if configured
        self.switch_entity_id = config.get(CONF_SWITCH_ENTITY)
        if self.switch_entity_id:
            self.setup_switch_entity_listener()
    
    def setup_switch_entity_listener(self):
        """Set up a listener for the global switch entity state changes."""
        @callback
        async def switch_state_listener(event):
            """Handle the state change event for global switch entity."""
            new_state = event.data.get('new_state')
            if new_state is None:
                return
            
            if new_state.state.lower() not in ('on', 'true', 'home', 'open'):
                _LOGGER.info(f"Global switch entity {self.switch_entity_id} turned off, stopping dashboards for devices without specific switches")
                
                # Only stop dashboards for devices without their own switch
                for device_name, device_configs in self.devices.items():
                    current_config, _ = self.time_window_checker.get_current_device_config(device_name, device_configs)
                    if not current_config.get('switch_entity_id'):
                        # This device uses the global switch, stop its dashboard
                        ip = await self.device_manager.async_get_device_ip(device_name)
                        if ip:
                            is_casting = await self.device_manager.async_check_device_status(ip)
                            if is_casting:
                                _LOGGER.info(f"Stopping dashboard for {device_name} due to global switch off")
                                await self.async_stop_casting(ip)
                                
                                device_key = f"{device_name}_{ip}"
                                self.device_manager.update_active_device(
                                    device_key=device_key,
                                    status='stopped',
                                    last_checked=datetime.now().isoformat()
                                )
        
        # Register the listener for the global switch
        if self.switch_entity_id:
            self.hass.helpers.event.async_track_state_change_event(
                self.switch_entity_id, switch_state_listener
            )
            _LOGGER.info(f"Registered state change listener for global switch entity: {self.switch_entity_id}")
        
        # Set up listeners for device-specific switches
        for device_name, device_configs in self.devices.items():
            for config in device_configs:
                if 'switch_entity_id' in config:
                    device_switch = config.get('switch_entity_id')
                    if device_switch:
                        # Use a closure to capture the current device_name and config
                        @callback
                        async def device_switch_listener(event, device=device_name, conf=config):
                            """Handle the state change event for device-specific switch entity."""
                            new_state = event.data.get('new_state')
                            if new_state is None:
                                return
                            
                            entity_id = event.data.get('entity_id')
                            
                            # Check if the device is active and should be stopped
                            if new_state.state.lower() not in ('on', 'true', 'home', 'open'):
                                # Find the device IP
                                ip = await self.device_manager.async_get_device_ip(device)
                                if ip:
                                    # Check if it's currently casting
                                    is_casting = await self.device_manager.async_check_device_status(ip)
                                    if is_casting:
                                        _LOGGER.info(f"Device switch entity {entity_id} turned off for {device}, stopping dashboard")
                                        await self.async_stop_casting(ip)
                                        
                                        # Update device status
                                        device_key = f"{device}_{ip}"
                                        self.device_manager.update_active_device(
                                            device_key=device_key,
                                            status='stopped',
                                            last_checked=datetime.now().isoformat()
                                        )
                            else:
                                # If switch turned on, trigger a re-check of the device
                                _LOGGER.info(f"Device switch entity {entity_id} turned on for {device}, scheduling check")
                                self.hass.async_create_task(self.async_monitor_devices())
                        
                        # Register the listener for this device's switch
                        self.hass.helpers.event.async_track_state_change_event(
                            device_switch, device_switch_listener
                        )
                        _LOGGER.info(f"Registered state change listener for device {device_name} switch entity: {device_switch}")
    async def async_stop_all_dashboards(self):
        """Stop casting dashboards on all active devices."""
        _LOGGER.info("Stopping all active dashboard casts")
        
        # Get all active devices
        active_devices = self.device_manager.get_all_active_devices()
        
        # Find all devices that are currently connected (showing dashboard)
        connected_devices = {key: device for key, device in active_devices.items() 
                            if device.get('status') == 'connected'}
        
        if not connected_devices:
            _LOGGER.info("No active dashboard casts found to stop")
            return
        
        _LOGGER.info(f"Found {len(connected_devices)} active dashboard casts to stop")
        
        # Stop each connected device
        for device_key, device_info in connected_devices.items():
            ip = device_info.get('ip')
            name = device_info.get('name', 'Unknown device')
            
            if not ip:
                _LOGGER.warning(f"No IP found for device {name}, skipping stop command")
                continue
                
            _LOGGER.info(f"Stopping dashboard cast on {name} ({ip})")
            success = await self.async_stop_casting(ip)
            
            if success:
                _LOGGER.info(f"Successfully stopped dashboard cast on {name} ({ip})")
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status='stopped',
                    last_checked=datetime.now().isoformat()
                )
            else:
                _LOGGER.error(f"Failed to stop dashboard cast on {name} ({ip})")
        
        _LOGGER.info("Finished stopping all active dashboard casts")
    
    def set_stats_manager(self, stats_manager):
        """Set the stats manager reference."""
        self.stats_manager = stats_manager
        # Share the device manager with stats manager
        self.stats_manager.set_device_manager(self.device_manager)
    
    async def initialize_devices(self):
        """Initialize all configured devices."""
        # Perform a single scan to find all devices
        device_ip_map = {}
        for device_name in self.devices.keys():
            ip = await self.device_manager.async_get_device_ip(device_name)
            if ip:
                device_ip_map[device_name] = ip
            else:
                _LOGGER.error(f"Could not get IP for {device_name}, skipping initial setup for this device")
                
        # Add delay between scanning and casting to avoid overwhelming the network
        await asyncio.sleep(2)
        
        # Start each device with appropriate delay
        for device_name, device_configs in self.devices.items():
            if device_name not in device_ip_map:
                continue
                
            ip = device_ip_map[device_name]
            
            # Get the current device config based on the time window
            current_config, is_in_window = self.time_window_checker.get_current_device_config(device_name, device_configs)
            
            # Store the active config for this device
            self.active_device_configs[device_name] = {
                'config': current_config,
                'instance_change': False,  # No change on first run
                'last_updated': datetime.now()
            }
            
            # Check if casting is enabled for this specific device
            if not await self.switch_checker.async_check_switch_entity(device_name, current_config):
                _LOGGER.info(f"Casting disabled for device {device_name}, skipping initial cast")
                continue
            
            # Skip devices outside their time window
            if not is_in_window:
                _LOGGER.info(f"Outside all casting time windows for {device_name}, skipping initial cast")
                continue
            
            # Check if device is within casting time window
            is_in_time_window = await self.time_window_checker.async_is_within_time_window(device_name, current_config)
            
            # Skip devices outside their time window
            if not is_in_time_window:
                _LOGGER.info(f"Outside casting time window for {device_name}, skipping initial cast")
                continue
            
            # Check if media is playing
            if await self.device_manager.async_is_media_playing(ip):
                _LOGGER.info(f"Media is currently playing on {device_name}, skipping initial cast")
                device_key = f"{device_name}_{ip}"
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status='media_playing',
                    name=device_name,
                    ip=ip,
                    first_seen=datetime.now().isoformat(),
                    last_checked=datetime.now().isoformat(),
                    reconnect_attempts=0
                )
                continue
                
            # Check if the device is part of an active speaker group
            speaker_groups = current_config.get('speaker_groups')
            if speaker_groups:
                if await self.device_manager.async_check_speaker_group_state(ip, speaker_groups):
                    _LOGGER.info(f"Speaker Group playback is active for {device_name}, skipping initial cast")
                    device_key = f"{device_name}_{ip}"
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status='speaker_group_active',
                        name=device_name,
                        ip=ip,
                        first_seen=datetime.now().isoformat(),
                        last_checked=datetime.now().isoformat(),
                        reconnect_attempts=0
                    )
                    continue
            
            # Create task for each device
            await self.async_start_device(device_name, current_config, ip)
            
            # Apply cast delay between devices
            if self.cast_delay > 0:
                await asyncio.sleep(self.cast_delay)
        
        return True
    
    async def async_start_device(self, device_name, device_config, ip=None):
        """Start casting to a specific device."""
        _LOGGER.info(f"Starting casting to {device_name}")
        
        # Get device IP if not provided
        if not ip:
            ip = await self.device_manager.async_get_device_ip(device_name)
            if not ip:
                _LOGGER.error(f"Could not get IP for {device_name}, skipping")
                return
        
        # Check if media is playing before casting
        if await self.device_manager.async_is_media_playing(ip):
            _LOGGER.info(f"Media is currently playing on {device_name}, skipping cast")
            device_key = f"{device_name}_{ip}"
            self.device_manager.update_active_device(
                device_key=device_key,
                status='media_playing',
                name=device_name,
                ip=ip,
                first_seen=datetime.now().isoformat(),
                last_checked=datetime.now().isoformat(),
                reconnect_attempts=0
            )
            return
        
        # Check if a cast is already in progress
        if ip in self.casting_manager.active_casting_operations:
            _LOGGER.info(f"Casting already in progress for {device_name} ({ip}), skipping")
            device_key = f"{device_name}_{ip}"
            self.device_manager.update_active_device(
                device_key=device_key,
                status=STATUS_CASTING_IN_PROGRESS,
                name=device_name,
                ip=ip,
                last_checked=datetime.now().isoformat()
            )
            return
        
        device_key = f"{device_name}_{ip}"
        # Update device status to indicate casting is in progress
        self.device_manager.update_active_device(
            device_key=device_key,
            status=STATUS_CASTING_IN_PROGRESS,
            name=device_name,
            ip=ip,
            last_checked=datetime.now().isoformat()
        )
        
        if self.stats_manager:
            await self.stats_manager.async_update_health_stats(device_key, EVENT_CONNECTION_ATTEMPT)
        
        # Cast dashboard to device
        dashboard_url = device_config.get('dashboard_url')
        success = await self.casting_manager.async_cast_dashboard(ip, dashboard_url, device_config)
        
        if success:
            _LOGGER.info(f"Successfully connected to {device_name} ({ip})")
            self.device_manager.update_active_device(
                device_key=device_key,
                status='connected',
                name=device_name,
                ip=ip,
                first_seen=datetime.now().isoformat(),
                last_checked=datetime.now().isoformat(),
                reconnect_attempts=0,
                current_dashboard=dashboard_url
            )
            if self.stats_manager:
                await self.stats_manager.async_update_health_stats(device_key, EVENT_CONNECTION_SUCCESS)
        else:
            _LOGGER.error(f"Failed to connect to {device_name} ({ip})")
            self.device_manager.update_active_device(
                device_key=device_key,
                status='disconnected',
                name=device_name,
                ip=ip,
                first_seen=datetime.now().isoformat(),
                last_checked=datetime.now().isoformat(),
                reconnect_attempts=0
            )
    
    async def async_update_device_configs(self):
        """Update the active device configurations based on the current time."""
        updated_devices = []
        
        for device_name, device_configs in self.devices.items():
            # Get the current device config based on the time window
            current_config, is_in_window = self.time_window_checker.get_current_device_config(device_name, device_configs)
            
            # Check if this device already has an active config
            if device_name in self.active_device_configs:
                previous_config = self.active_device_configs[device_name]['config']
                
                # Check if the dashboard URL has changed
                if (previous_config.get('dashboard_url') != current_config.get('dashboard_url')):
                    _LOGGER.info(f"Dashboard configuration changed for {device_name}: new dashboard URL: {current_config.get('dashboard_url')}")
                    self.active_device_configs[device_name] = {
                        'config': current_config,
                        'instance_change': True,
                        'last_updated': datetime.now()
                    }
                    updated_devices.append(device_name)
                else:
                    # No change, just update the timestamp
                    self.active_device_configs[device_name]['last_updated'] = datetime.now()
                    self.active_device_configs[device_name]['instance_change'] = False
            else:
                # First time seeing this device
                self.active_device_configs[device_name] = {
                    'config': current_config,
                    'instance_change': False,  # No change on first run
                    'last_updated': datetime.now()
                }
        
        return updated_devices

    async def async_monitor_devices(self, *args):
        """Monitor all devices and reconnect if needed."""
        # Use a lock to prevent monitoring cycles from overlapping
        if self.monitor_lock.locked():
            _LOGGER.debug("Previous monitoring cycle still running, skipping this cycle")
            return
            
        async with self.monitor_lock:
            _LOGGER.debug("Running device status check")
            
            # Update device configurations based on time windows
            updated_devices = await self.async_update_device_configs()
            if updated_devices:
                _LOGGER.info(f"Devices with updated dashboard configurations: {updated_devices}")
                
            # Scan for all devices at once and store IPs - with better error handling
            device_ip_map = {}
            scan_futures = []
            
            # Start all IP lookups concurrently with timeouts
            for device_name in self.devices.keys():
                future = asyncio.ensure_future(self._get_device_ip_with_timeout(device_name))
                scan_futures.append((device_name, future))
            
            # Wait for all lookups to complete
            for device_name, future in scan_futures:
                try:
                    ip = await future
                    if ip:
                        device_ip_map[device_name] = ip
                    else:
                        _LOGGER.warning(f"Could not get IP for {device_name}, skipping check")
                except Exception as e:
                    _LOGGER.error(f"Error getting IP for {device_name}: {str(e)}, skipping check")
            
            # Process each device with its known IP
            for device_name in list(self.devices.keys()):
                # Skip if we couldn't get the IP
                if device_name not in device_ip_map:
                    continue
                    
                ip = device_ip_map[device_name]
                device_key = f"{device_name}_{ip}"
                
                # Get the current device config
                if device_name not in self.active_device_configs:
                    _LOGGER.warning(f"No active configuration for {device_name}, skipping")
                    continue
                    
                active_config_info = self.active_device_configs[device_name]
                current_config = active_config_info['config']
                instance_change = active_config_info['instance_change']
                
                # Check if casting is enabled for this specific device
                if not await self.switch_checker.async_check_switch_entity(device_name, current_config):
                    _LOGGER.info(f"Casting disabled for device {device_name}, checking if dashboard is active to stop it")
                    
                    # Check if our dashboard is currently active
                    is_casting = await self.device_manager.async_check_device_status(ip)
                    
                    if is_casting:
                        _LOGGER.info(f"Device {device_name} is casting our dashboard while casting is disabled. Stopping cast.")
                        await self.async_stop_casting(ip)
                        
                        # Update device status
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='stopped',
                            last_checked=datetime.now().isoformat()
                        )
                    
                    continue  # Skip to the next device
                
                # Check if the current time is within any of the device's time windows
                _, is_in_window = self.time_window_checker.get_current_device_config(device_name, self.devices[device_name])
                    
                # Handle device outside all time windows
                if not is_in_window:
                    _LOGGER.debug(f"Outside all casting time windows for {device_name}, checking if dashboard is active to stop it")
                    
                    # Check if our dashboard is currently active
                    is_casting = await self.device_manager.async_check_device_status(ip)
                    
                    if is_casting:
                        _LOGGER.info(f"Device {device_name} is casting our dashboard outside allowed time window. Stopping cast.")
                        await self.async_stop_casting(ip)
                        
                        # Update device status
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='stopped',
                            last_checked=datetime.now().isoformat()
                        )
                    
                    continue  # Skip to the next device
                
                # Check if casting is already in progress for this device
                if ip in self.casting_manager.active_casting_operations:
                    _LOGGER.info(f"Casting operation in progress for {device_name} ({ip}), skipping checks")
                    # Update status to indicate casting is in progress
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status=STATUS_CASTING_IN_PROGRESS,
                        last_checked=datetime.now().isoformat()
                    )
                    continue
                
                # If the instance has changed, we need to force a reload
                if instance_change:
                    _LOGGER.info(f"Dashboard configuration changed for {device_name}, forcing reload")
                    
                    # If currently casting, stop it first
                    is_casting = await self.device_manager.async_check_device_status(ip)
                    if is_casting:
                        _LOGGER.info(f"Stopping current dashboard on {device_name} before switching to new one")
                        await self.async_stop_casting(ip)
                        # Small delay to ensure the stop takes effect
                        await asyncio.sleep(2)
                    
                    # Cast the new dashboard
                    await self.async_start_device(device_name, current_config, ip)
                    
                    # Reset the instance_change flag
                    self.active_device_configs[device_name]['instance_change'] = False
                    continue  # Skip normal checks since we've already handled this device
                
                # Handle device within its allowed time window
                _LOGGER.debug(f"Inside casting time window for {device_name}, continuing with normal checks")
                
                # Check if the device is part of an active speaker group
                speaker_groups = current_config.get('speaker_groups')
                if speaker_groups:
                    if await self.device_manager.async_check_speaker_group_state(ip, speaker_groups):
                        _LOGGER.info(f"Speaker Group playback is active for {device_name}, skipping status check")
                        active_device = self.device_manager.get_active_device(device_key)
                        if active_device:
                            if active_device.get('status') != 'speaker_group_active':
                                self.device_manager.update_active_device(
                                    device_key=device_key,
                                    status='speaker_group_active',
                                    last_checked=datetime.now().isoformat()
                                )
                        else:
                            self.device_manager.update_active_device(
                                device_key=device_key,
                                status='speaker_group_active',
                                name=device_name,
                                ip=ip,
                                first_seen=datetime.now().isoformat(),
                                last_checked=datetime.now().isoformat(),
                                reconnect_attempts=0
                            )
                        continue
                
                # Check if media is playing before attempting to reconnect
                is_media_playing = await self.device_manager.async_is_media_playing(ip)
                if is_media_playing:
                    _LOGGER.info(f"Media is currently playing on {device_name}, skipping status check")
                    # Update device status to media_playing
                    active_device = self.device_manager.get_active_device(device_key)
                    if active_device:
                        # If device was previously connected to our dashboard, add a delay before marking as media_playing
                        # This prevents rapid switching when "Hey Google" commands are being processed
                        if active_device.get('status') == 'connected':
                            _LOGGER.info(f"Device {device_name} was showing our dashboard but now has media - giving it time to stabilize")
                            # Don't update the status yet, let it remain as 'connected' for this cycle
                        else:
                            self.device_manager.update_active_device(device_key, 'media_playing', last_checked=datetime.now().isoformat())
                    else:
                        # First time seeing this device
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='media_playing',
                            name=device_name,
                            ip=ip,
                            first_seen=datetime.now().isoformat(),
                            last_checked=datetime.now().isoformat(),
                            reconnect_attempts=0
                        )
                    continue
                
                # Check if device is still casting our dashboard
                is_casting = await self.device_manager.async_check_device_status(ip)
                
                # Check if device is idle with just volume info
                cmd = ['catt', '-d', ip, 'status']
                status_process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    # Add timeout to prevent hanging
                    status_stdout, status_stderr = await asyncio.wait_for(status_process.communicate(), timeout=10.0)
                    status_output = status_stdout.decode().strip()
                    
                    # If only volume info is returned, device is truly idle
                    is_idle = len(status_output.splitlines()) <= 2 and all(line.startswith("Volume") for line in status_output.splitlines())
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"Status check timed out for {device_name} ({ip})")
                    status_process.terminate()
                    try:
                        await asyncio.wait_for(status_process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        status_process.kill()
                    # Assume device is not idle to avoid reconnect attempts that might fail
                    is_idle = False
                    status_output = ""
                
                # Update device status
                active_device = self.device_manager.get_active_device(device_key)
                if active_device:
                    previous_status = active_device.get('status', 'unknown')
                    last_status_change = active_device.get('last_status_change', 0)
                    current_time = time.time()
                    
                    # Determine current state and take appropriate action
                    if is_casting:
                        # Device is showing our dashboard
                        if previous_status != 'connected':
                            self.device_manager.update_active_device(
                                device_key=device_key, 
                                status='connected', 
                                last_status_change=current_time,
                                current_dashboard=current_config.get('dashboard_url')
                            )
                            _LOGGER.info(f"Device {device_name} ({ip}) is now connected")
                            self.device_manager.update_active_device(device_key, 'connected', reconnect_attempts=0)
                            if self.stats_manager:
                                await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_SUCCESS)
                        else:
                            self.device_manager.update_active_device(device_key, 'connected', last_checked=datetime.now().isoformat())
                    elif is_idle:
                        # Device is idle, should show our dashboard
                        # Add a delay after any status change to prevent rapid reconnects
                        # This gives voice commands time to be processed
                        min_time_between_reconnects = 30  # seconds
                        time_since_last_change = current_time - last_status_change
                        
                        if previous_status != 'disconnected':
                            _LOGGER.info(f"Device {device_name} ({ip}) is idle and not casting our dashboard")
                            self.device_manager.update_active_device(
                                device_key=device_key, 
                                status='disconnected', 
                                last_status_change=current_time,
                                last_checked=datetime.now().isoformat()
                            )
                        else:
                            # Only attempt to reconnect if enough time has passed since last status change
                            if time_since_last_change > min_time_between_reconnects:
                                _LOGGER.info(f"Device {device_name} ({ip}) is still idle after waiting period, attempting reconnect")
                                await self.async_reconnect_device(device_name, ip, current_config)
                            else:
                                _LOGGER.debug(f"Device {device_name} ({ip}) is idle but waiting {int(min_time_between_reconnects - time_since_last_change)}s before reconnecting")
                                self.device_manager.update_active_device(device_key, 'disconnected', last_checked=datetime.now().isoformat())
                    else:
                        # Device has other content
                        if previous_status != 'other_content':
                            self.device_manager.update_active_device(
                                device_key=device_key, 
                                status='other_content', 
                                last_status_change=current_time,
                                last_checked=datetime.now().isoformat()
                            )
                        else:
                            self.device_manager.update_active_device(device_key, 'other_content', last_checked=datetime.now().isoformat())
                        _LOGGER.info(f"Device {device_name} ({ip}) has other content (not our dashboard and not idle)")
                else:
                    # First time seeing this device
                    if is_casting:
                        status = 'connected'
                        _LOGGER.info(f"Device {device_name} ({ip}) is casting our dashboard")
                    elif is_idle:
                        status = 'disconnected'
                        _LOGGER.info(f"Device {device_name} ({ip}) is idle, will attempt to connect after stabilization period")
                    else:
                        status = 'other_content'
                        _LOGGER.info(f"Device {device_name} ({ip}) has other content, will not connect")
                    
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status=status,
                        name=device_name,
                        ip=ip,
                        first_seen=datetime.now().isoformat(),
                        last_checked=datetime.now().isoformat(),
                        last_status_change=time.time(),
                        reconnect_attempts=0,
                        current_dashboard=current_config.get('dashboard_url') if status == 'connected' else None
                    )

    async def async_stop_casting(self, ip):
        """Stop casting on a device."""
        try:
            # Check if a cast operation is in progress
            if ip in self.casting_manager.active_casting_operations:
                _LOGGER.info(f"Casting operation in progress for {ip}, waiting for it to complete before stopping")
                # Wait up to 30 seconds for the operation to complete
                for _ in range(30):
                    if ip not in self.casting_manager.active_casting_operations:
                        break
                    await asyncio.sleep(1)
                
                if ip in self.casting_manager.active_casting_operations:
                    _LOGGER.warning(f"Casting operation still in progress after 30s wait, proceeding with stop")
            
            cmd = ['catt', '-d', ip, 'stop']
            _LOGGER.debug(f"Executing stop command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
                
                # Log the results
                stdout_str = stdout.decode().strip()
                stderr_str = stderr.decode().strip()
                _LOGGER.debug(f"Stop command stdout: {stdout_str}")
                _LOGGER.debug(f"Stop command stderr: {stderr_str}")
                
                if process.returncode == 0:
                    _LOGGER.info(f"Successfully stopped casting on device at {ip}")
                    return True
                else:
                    _LOGGER.error(f"Failed to stop casting on device at {ip}: {stderr_str}")
                    return False
            except asyncio.TimeoutError:
                _LOGGER.error(f"Stop command timed out for {ip}")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error stopping casting on device at {ip}: {str(e)}")
            return False

    async def async_reconnect_device(self, device_name, ip, device_config):
        """Attempt to reconnect a disconnected device."""
        device_key = f"{device_name}_{ip}"
        
        # Check if a cast is already in progress
        if ip in self.casting_manager.active_casting_operations:
            _LOGGER.info(f"Casting already in progress for {device_name} ({ip}), skipping reconnect")
            self.device_manager.update_active_device(
                device_key=device_key,
                status=STATUS_CASTING_IN_PROGRESS,
                last_checked=datetime.now().isoformat()
            )
            return False
        
        # Skip if outside time window
        if not await self.time_window_checker.async_is_within_time_window(device_name, device_config):
            _LOGGER.info(f"Outside casting time window for {device_name}, skipping reconnect")
            return False
        
        # Check if the device is part of an active speaker group
        speaker_groups = device_config.get('speaker_groups')
        if speaker_groups:
            if await self.device_manager.async_check_speaker_group_state(ip, speaker_groups):
                _LOGGER.info(f"Speaker Group playback is active for {device_name}, skipping reconnect")
                active_device = self.device_manager.get_active_device(device_key)
                if active_device:
                    self.device_manager.update_active_device(device_key, 'speaker_group_active')
                return False
        
        # Check if media is playing before attempting to reconnect
        if await self.device_manager.async_is_media_playing(ip):
            _LOGGER.info(f"Media is currently playing on {device_name}, skipping reconnect")
            active_device = self.device_manager.get_active_device(device_key)
            if active_device:
                self.device_manager.update_active_device(device_key, 'media_playing')
            return False
        
        # Increment reconnect attempts
        active_device = self.device_manager.get_active_device(device_key)
        if active_device:
            attempts = active_device.get('reconnect_attempts', 0) + 1
            self.device_manager.update_active_device(device_key, active_device.get('status'), reconnect_attempts=attempts)
            
            # If too many reconnect attempts, back off
            if attempts > 10:
                _LOGGER.warning(f"Device {device_name} ({ip}) has had {attempts} reconnect attempts, backing off")
                if self.stats_manager:
                    await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_FAILED)
                return False
        
        # Check status one more time to see if it's truly idle
        cmd = ['catt', '-d', ip, 'status']
        try:
            status_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            status_stdout, status_stderr = await asyncio.wait_for(status_process.communicate(), timeout=10.0)
            status_output = status_stdout.decode().strip()
            
            # If device isn't idle (has more than just volume info), don't attempt to cast
            if len(status_output.splitlines()) > 2 or not all(line.startswith("Volume") for line in status_output.splitlines()):
                if "Dummy" not in status_output and "8123" not in status_output:
                    _LOGGER.info(f"Device {device_name} ({ip}) shows non-idle status, skipping reconnect")
                    if active_device:
                        self.device_manager.update_active_device(device_key, 'other_content')
                    return False
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Status check timed out for {device_name} ({ip})")
            status_process.terminate()
            try:
                await asyncio.wait_for(status_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                status_process.kill()
            # Skip reconnect if we can't determine status
            return False
        except Exception as e:
            _LOGGER.error(f"Error checking status before reconnect: {str(e)}")
            return False
        
        # Update status to indicate casting is in progress
        self.device_manager.update_active_device(
            device_key=device_key,
            status=STATUS_CASTING_IN_PROGRESS,
            last_checked=datetime.now().isoformat()
        )
        
        _LOGGER.info(f"Attempting to reconnect to {device_name} ({ip})")
        if self.stats_manager:
            await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_ATTEMPT)
        dashboard_url = device_config.get('dashboard_url')
        _LOGGER.debug(f"Casting URL {dashboard_url} to device {device_name} ({ip})")
        success = await self.casting_manager.async_cast_dashboard(ip, dashboard_url, device_config)
        
        if success:
            _LOGGER.info(f"Successfully reconnected to {device_name} ({ip})")
            if active_device:
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status='connected',
                    reconnect_attempts=0,
                    last_reconnect=datetime.now().isoformat(),
                    current_dashboard=dashboard_url
                )
            if self.stats_manager:
                await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_SUCCESS)
            return True
        else:
            _LOGGER.error(f"Failed to reconnect to {device_name} ({ip})")
            if active_device:
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status='disconnected',
                    last_checked=datetime.now().isoformat()
                )
            if self.stats_manager:
                await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_FAILED)
            return False

    async def _get_device_ip_with_timeout(self, device_name, timeout=15):
        """Get device IP with timeout to prevent hanging."""
        try:
            return await asyncio.wait_for(
                self.device_manager.async_get_device_ip(device_name),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            _LOGGER.error(f"Timed out getting IP for {device_name} after {timeout} seconds")
            return None
        except Exception as e:
            _LOGGER.error(f"Error getting IP for {device_name}: {str(e)}")
            return None
