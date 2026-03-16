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
    STATUS_ASSISTANT_ACTIVE,
    CONF_SWITCH_ENTITY
)

_LOGGER = logging.getLogger(__name__)

class MonitoringManager:
    """Class to handle device monitoring and reconnection.

    This manager handles:
    - Periodic device status checking
    - Dashboard casting based on time windows and entity states
    - State change listeners for switch entities
    - Reconnection logic when devices go offline
    """

    def __init__(self, hass: HomeAssistant, config: dict, device_manager, casting_manager,
                 time_window_checker, switch_checker):
        """Initialize the monitoring manager.

        Args:
            hass: The Home Assistant instance.
            config: The integration configuration dictionary.
            device_manager: The DeviceManager instance for status checks.
            casting_manager: The CastingManager instance for casting operations.
            time_window_checker: The TimeWindowChecker for time-based scheduling.
            switch_checker: The SwitchEntityChecker for entity-based gating.
        """
        _LOGGER.debug("MONITORING INIT CONFIG: %s", config)
        self.hass = hass
        self.config = config
        self.device_manager = device_manager
        self.casting_manager = casting_manager
        self.time_window_checker = time_window_checker
        self.switch_checker = switch_checker
        self.stats_manager = None  # Will be set later
        self.devices = config.get(CONF_DEVICES, {})
        self.device_identifiers = config.get("device_identifiers", {})
        self.cast_delay = config.get('cast_delay', 0)
        self.active_device_configs = {}  # Track which dashboard config is active for each device
        self.monitor_lock = asyncio.Lock()  # Lock to prevent monitoring cycle overlap
        self._device_locks: dict[str, asyncio.Lock] = {}  # Per-device locks for concurrent operations
        self._dummy_positions: dict = {}  # Reserved for future use
        self._unsubscribe_listeners: list = []  # Track listeners for cleanup
        self._unreachable_counts: dict[str, int] = {}  # Consecutive unreachable cycle count per device

        # Set up switch entity state change listener if configured
        self.switch_entity_id = config.get(CONF_SWITCH_ENTITY)
        if self.switch_entity_id:
            self.setup_switch_entity_listener()

    async def _async_resolve_device_ip(self, device_key: str) -> str | None:
        """Resolve the IP address for a device by its key.

        Uses device_identifiers (name + ip) if available, otherwise treats
        device_key as a legacy name-or-IP string.

        Args:
            device_key: The device display title or legacy name/IP string.

        Returns:
            The resolved IP address, or None if resolution fails.
        """
        identifier = self.device_identifiers.get(device_key)
        if identifier:
            return await self.device_manager.async_get_device_ip_from_config(identifier)
        # Legacy fallback: device_key is the device name or IP directly
        return await self.device_manager.async_get_device_ip(device_key)

    def _get_device_lock(self, device_name: str) -> asyncio.Lock:
        """Get or create a per-device asyncio lock.

        Args:
            device_name: The name identifying the device.

        Returns:
            An asyncio.Lock dedicated to the specified device.
        """
        if device_name not in self._device_locks:
            self._device_locks[device_name] = asyncio.Lock()
        return self._device_locks[device_name]

    async def cleanup(self) -> None:
        """Clean up all resources held by the monitoring manager."""
        _LOGGER.debug("Cleaning up monitoring manager resources")

        # Unsubscribe all state change listeners
        for unsub in self._unsubscribe_listeners:
            try:
                unsub()
            except Exception as e:
                _LOGGER.debug("Error unsubscribing listener: %s", e)
        self._unsubscribe_listeners.clear()
        _LOGGER.debug("Unsubscribed %s listeners", len(self._unsubscribe_listeners))

        # Clear device locks
        self._device_locks.clear()

        # Clear active device configs
        self.active_device_configs.clear()

        _LOGGER.debug("Monitoring manager cleanup complete")
    
    def setup_switch_entity_listener(self):
        """Set up state change listeners for the global and per-device switch entities."""
        @callback
        async def switch_state_listener(event):
            """Handle the state change event for global switch entity."""
            new_state = event.data.get('new_state')
            if new_state is None:
                return
            
            if new_state.state.lower() not in ('on', 'true', 'home', 'open'):
                _LOGGER.info("Global switch entity %s turned off, stopping dashboards for devices without specific switches", self.switch_entity_id)
                
                # Only stop dashboards for devices without their own switch
                for device_name, device_configs in self.devices.items():
                    current_config, _ = self.time_window_checker.get_current_device_config(device_name, device_configs)
                    if not current_config.get('switch_entity_id'):
                        # This device uses the global switch, stop its dashboard
                        ip = await self._async_resolve_device_ip(device_name)
                        if ip:
                            is_casting = await self.device_manager.async_check_device_status(ip)
                            if is_casting:
                                _LOGGER.info("Stopping dashboard for %s due to global switch off", device_name)
                                await self.async_stop_casting(ip)
                                
                                device_key = f"{device_name}_{ip}"
                                self.device_manager.update_active_device(
                                    device_key=device_key,
                                    status='stopped',
                                    last_checked=datetime.now().isoformat()
                                )
        
        # Register the listener for the global switch
        if self.switch_entity_id:
            unsub = async_track_state_change_event(
                self.hass, self.switch_entity_id, switch_state_listener
            )
            self._unsubscribe_listeners.append(unsub)
            _LOGGER.info("Registered state change listener for global switch entity: %s", self.switch_entity_id)
        
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
                                ip = await self._async_resolve_device_ip(device)
                                if ip:
                                    # Check if it's currently casting
                                    is_casting = await self.device_manager.async_check_device_status(ip)
                                    if is_casting:
                                        _LOGGER.info("Device switch entity %s turned off for %s, stopping dashboard", entity_id, device)
                                        await self.async_stop_casting(ip)
                                        
                                        # Update device status
                                        device_key = f"{device}_{ip}"
                                        self.device_manager.update_active_device(
                                            device_key=device_key,
                                            status='stopped',
                                            last_checked=datetime.now().isoformat()
                                        )
                            else:
                                # If switch turned on, trigger a re-check of ONLY this specific device
                                _LOGGER.info("Device switch entity %s turned on for %s, scheduling check for %s only", entity_id, device, device)
                                self.hass.async_create_task(self._async_check_single_device(device))
                        
                        # Register the listener for this device's switch
                        unsub = async_track_state_change_event(
                            self.hass, device_switch, device_switch_listener
                        )
                        self._unsubscribe_listeners.append(unsub)
                        _LOGGER.info("Registered state change listener for device %s switch entity: %s", device_name, device_switch)

    async def _async_check_single_device(self, target_device_name):
        """Check and process a single device, skipping the full monitoring cycle.

        Args:
            target_device_name: The display name of the device to check.
        """
        if self.monitor_lock.locked():
            _LOGGER.debug("Previous monitoring cycle still running, skipping single device check for %s", target_device_name)
            return

        async with self.monitor_lock:
            _LOGGER.debug("Running single device check for %s", target_device_name)

            # Get device IP
            ip = await self._get_device_ip_with_timeout(target_device_name)
            if not ip:
                _LOGGER.warning("Could not get IP for %s, skipping check", target_device_name)
                return

            # Get the current device config
            if target_device_name not in self.active_device_configs:
                _LOGGER.warning("No active configuration for %s, skipping", target_device_name)
                return
                
            active_config_info = self.active_device_configs[target_device_name]
            current_config = active_config_info['config']
            
            # Process this single device using the same logic as the main monitoring
            await self._process_single_device(target_device_name, ip, current_config, force_check=True)

    async def _process_single_device(self, device_name, ip, current_config, force_check=False):
            """Evaluate device state and cast, stop, or skip as appropriate.

            This is the core per-device logic, shared by the full monitoring cycle
            and switch-triggered single-device checks.

            Args:
                device_name: The display name of the device.
                ip: The resolved IP address of the device.
                current_config: The active dashboard configuration dict for this device.
                force_check: When True, bypass stabilization delays (e.g. switch-triggered).
            """
            device_key = f"{device_name}_{ip}"
            
            # SINGLE STATUS CHECK - do this once and reuse the result
            is_casting = await self.device_manager.async_check_device_status(ip)
            
            # Check if casting is enabled for this specific device
            if not await self.switch_checker.async_check_switch_entity(device_name, current_config):
                _LOGGER.info("Casting disabled for device %s, checking if dashboard is active to stop it", device_name)

                if is_casting:  # Reuse the single status check result
                    _LOGGER.info("Device %s is casting our dashboard while casting is disabled. Stopping cast.", device_name)
                    await self.async_stop_casting(ip)
                    
                    # Update device status
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status='stopped',
                        last_checked=datetime.now().isoformat()
                    )
                
                return  # Skip to the next device
            
            # Check if the current time is within any of the device's time windows
            _, is_in_window = self.time_window_checker.get_current_device_config(device_name, self.devices[device_name])
                
            # Handle device outside all time windows
            if not is_in_window:
                _LOGGER.debug("Outside all casting time windows for %s, checking if dashboard is active to stop it", device_name)

                if is_casting:  # Reuse the single status check result
                    _LOGGER.info("Device %s is casting our dashboard outside allowed time window. Stopping cast.", device_name)
                    await self.async_stop_casting(ip)
                    
                    # Update device status
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status='stopped',
                        last_checked=datetime.now().isoformat()
                    )
                
                return  # Skip to the next device
            
            # Check if casting is already in progress for this device
            if ip in self.casting_manager.active_casting_operations:
                _LOGGER.info("Casting operation in progress for %s (%s), skipping checks", device_name, ip)
                # Update status to indicate casting is in progress
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status=STATUS_CASTING_IN_PROGRESS,
                    last_checked=datetime.now().isoformat()
                )
                return
            
            # Handle device configuration changes (only for regular monitoring, not switch-triggered)
            if not force_check and device_name in self.active_device_configs:
                active_config_info = self.active_device_configs[device_name]
                instance_change = active_config_info['instance_change']
                
                # If the instance has changed, we need to force a reload
                if instance_change:
                    _LOGGER.info("Dashboard configuration changed for %s, forcing reload", device_name)

                    # If currently casting, stop it first
                    if is_casting:  # Reuse the single status check result
                        _LOGGER.info("Stopping current dashboard on %s before switching to new one", device_name)
                        await self.async_stop_casting(ip)
                        # Small delay to ensure the stop takes effect
                        await asyncio.sleep(2)
                    
                    # Cast the new dashboard
                    await self.async_start_device(device_name, current_config, ip)
                    
                    # Reset the instance_change flag
                    self.active_device_configs[device_name]['instance_change'] = False
                    return  # Skip normal checks since we've already handled this device
            
            # Handle device within its allowed time window
            _LOGGER.debug("Inside casting time window for %s, continuing with normal checks", device_name)
            
            # Check if the device is part of an active speaker group
            speaker_groups = current_config.get('speaker_groups')
            if speaker_groups:
                if await self.device_manager.async_check_speaker_group_state(ip, speaker_groups):
                    _LOGGER.info("Speaker Group playback is active for %s, skipping status check", device_name)
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
                    return
            
            # If the initial status check already timed out (returned None), skip further catt
            # calls on this device — it's unreachable, not "other content"
            _initial_status_timed_out = not is_casting and self.device_manager._get_cached_status_output(ip) is None

            # Check if media is playing before attempting to reconnect
            if _initial_status_timed_out:
                is_media_playing = False
            else:
                is_media_playing = await self.device_manager.async_is_media_playing(ip)

            # Check if Google Assistant (timer/alarm/reminder) is active
            if _initial_status_timed_out:
                assistant_active = False
            else:
                assistant_active = await self.device_manager.async_is_assistant_active(ip)
            if assistant_active:
                _LOGGER.info("Google Assistant activity detected on %s, pausing dashboard casting", device_name)

                if is_casting:
                    _LOGGER.info("Stopping dashboard on %s to allow Assistant UI", device_name)
                    await self.async_stop_casting(ip)

                active_device = self.device_manager.get_active_device(device_key)
                if active_device:
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status=STATUS_ASSISTANT_ACTIVE,
                        last_checked=datetime.now().isoformat()
                    )
                else:
                    self.device_manager.update_active_device(
                        device_key=device_key,
                        status=STATUS_ASSISTANT_ACTIVE,
                        name=device_name,
                        ip=ip,
                        first_seen=datetime.now().isoformat(),
                        last_checked=datetime.now().isoformat(),
                        reconnect_attempts=0
                    )
                return

            if is_media_playing:
                _LOGGER.info("Media is currently playing on %s, skipping status check", device_name)
                # Update device status to media_playing
                active_device = self.device_manager.get_active_device(device_key)
                if active_device:
                    # If device was previously connected to our dashboard, add a delay before marking as media_playing
                    # This prevents rapid switching when "Hey Google" commands are being processed
                    if active_device.get('status') == 'connected':
                        _LOGGER.info("Device %s was showing our dashboard but now has media - giving it time to stabilize", device_name)
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
                return
            
            # Check if device is idle with just volume info (manual status check for idle detection)
            # Skip entirely if we already know the device is unreachable
            is_unreachable = False
            if _initial_status_timed_out:
                is_idle = False
                is_unreachable = True
                status_output = ""
                _LOGGER.debug("Skipping idle check for %s (%s) — already unreachable", device_name, ip)
            else:
                # Use cache if available to avoid a redundant catt call
                cached = self.device_manager._get_cached_status_output(ip)
                if cached is not None:
                    status_output = cached
                    is_idle = len(status_output.splitlines()) <= 2 and all(line.startswith("Volume") for line in status_output.splitlines())
                else:
                    cmd = ['catt', '-d', ip, 'status']
                    status_process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    try:
                        status_stdout, status_stderr = await asyncio.wait_for(status_process.communicate(), timeout=10.0)
                        status_output = status_stdout.decode().strip()
                        is_idle = len(status_output.splitlines()) <= 2 and all(line.startswith("Volume") for line in status_output.splitlines())
                    except asyncio.TimeoutError:
                        _LOGGER.warning("Status check timed out for %s (%s)", device_name, ip)
                        status_process.terminate()
                        try:
                            await asyncio.wait_for(status_process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            status_process.kill()
                        is_idle = False
                        is_unreachable = True
                        status_output = ""
            
            # Handle switch-triggered immediate casting
            if force_check:
                _LOGGER.info("Switch-triggered check for %s", device_name)

                if is_casting:
                    _LOGGER.info("Device %s is already casting our dashboard", device_name)
                    # Update status and we're done
                    active_device = self.device_manager.get_active_device(device_key)
                    if active_device:
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='connected',
                            last_checked=datetime.now().isoformat(),
                            current_dashboard=current_config.get('dashboard_url')
                        )
                    else:
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='connected',
                            name=device_name,
                            ip=ip,
                            first_seen=datetime.now().isoformat(),
                            last_checked=datetime.now().isoformat(),
                            reconnect_attempts=0,
                            current_dashboard=current_config.get('dashboard_url')
                        )
                    return
                
                elif is_idle:
                    _LOGGER.info("Switch triggered and device %s is idle - starting immediate cast", device_name)
                    # Bypass stabilization period, cast immediately
                    await self.async_start_device(device_name, current_config, ip)
                    return
                
                else:
                    active_device = self.device_manager.get_active_device(device_key)
                    previous_status = active_device.get('status') if active_device else None

                    # If CCD itself stopped this device (e.g. switch was turned off), cast immediately
                    # rather than waiting for the next regular monitoring cycle.
                    if previous_status == 'stopped' and not is_unreachable:
                        _LOGGER.info("Switch triggered and device %s was previously stopped by CCD - starting immediate cast", device_name)
                        await self.async_start_device(device_name, current_config, ip)
                        return

                    _LOGGER.info("Switch triggered but device %s has other content - marking status", device_name)
                    if active_device:
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='other_content',
                            last_checked=datetime.now().isoformat()
                        )
                    else:
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='other_content',
                            name=device_name,
                            ip=ip,
                            first_seen=datetime.now().isoformat(),
                            last_checked=datetime.now().isoformat(),
                            reconnect_attempts=0
                        )
                    return
            
            # Regular monitoring with stabilization period
            # Update device status based on consolidated check results
            active_device = self.device_manager.get_active_device(device_key)
            if active_device:
                previous_status = active_device.get('status', 'unknown')
                last_status_change = active_device.get('last_status_change', 0)
                current_time = time.time()
                
                # Determine current state and take appropriate action
                if is_casting:  # Use the single status check result

                    # Device is showing our dashboard
                    if previous_status != 'connected':
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='connected',
                            last_status_change=current_time,
                            current_dashboard=current_config.get('dashboard_url')
                        )
                        _LOGGER.info("Device %s (%s) is now connected", device_name, ip)
                        self.device_manager.update_active_device(device_key, 'connected', reconnect_attempts=0)
                        if self.stats_manager:
                            await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_SUCCESS)
                        # Dismiss any unreachable notification and reset the counter
                        self._unreachable_counts.pop(device_key, None)
                        if self.config.get("enable_notifications", True):
                            notification_id = f"ccd_unreachable_{device_key.replace(' ', '_')}"
                            self.hass.async_create_task(
                                self.hass.services.async_call(
                                    "persistent_notification", "dismiss",
                                    {"notification_id": notification_id}
                                )
                            )
                    else:
                        self.device_manager.update_active_device(device_key, 'connected', last_checked=datetime.now().isoformat())
                elif is_idle:
                    self._unreachable_counts.pop(device_key, None)
                    # Device is idle, should show our dashboard
                    # Add a delay after any status change to prevent rapid reconnects
                    # This gives voice commands time to be processed
                    min_time_between_reconnects = 30  # seconds
                    time_since_last_change = current_time - last_status_change
                    
                    if previous_status != 'disconnected':
                        _LOGGER.info("Device %s (%s) is idle and not casting our dashboard", device_name, ip)
                        self._dummy_positions.pop(device_key, None)
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='disconnected',
                            last_status_change=current_time,
                            last_checked=datetime.now().isoformat()
                        )
                    else:
                        # Only attempt to reconnect if enough time has passed since last status change
                        if time_since_last_change > min_time_between_reconnects:
                            _LOGGER.info("Device %s (%s) is still idle after waiting period, attempting reconnect", device_name, ip)
                            await self.async_reconnect_device(device_name, ip, current_config)
                        else:
                            _LOGGER.debug("Device %s (%s) is idle but waiting %ss before reconnecting", device_name, ip, int(min_time_between_reconnects - time_since_last_change))
                            self.device_manager.update_active_device(device_key, 'disconnected', last_checked=datetime.now().isoformat())
                elif is_unreachable:
                    # Device didn't respond at all — treat as disconnected, not other_content
                    unreachable_count = self._unreachable_counts.get(device_key, 0) + 1
                    self._unreachable_counts[device_key] = unreachable_count

                    if previous_status != 'disconnected':
                        _LOGGER.warning("Device %s (%s) is unreachable (all status checks timed out)", device_name, ip)
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='disconnected',
                            last_status_change=current_time,
                            last_checked=datetime.now().isoformat()
                        )
                    else:
                        _LOGGER.debug("Device %s (%s) still unreachable (consecutive count: %d)", device_name, ip, unreachable_count)
                        self.device_manager.update_active_device(device_key, 'disconnected', last_checked=datetime.now().isoformat())

                    if unreachable_count == 5 and self.config.get("enable_notifications", True):
                        notification_id = f"ccd_unreachable_{device_key.replace(' ', '_')}"
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "persistent_notification", "create",
                                {
                                    "title": f"CCD: {device_name} unreachable",
                                    "message": (
                                        f"**{device_name}** ({ip}) has not responded to the last 5 status checks.\n\n"
                                        f"Try rebooting the device if it doesn't recover on its own. "
                                        f"The dashboard will resume automatically once it comes back online."
                                    ),
                                    "notification_id": notification_id,
                                }
                            )
                        )
                else:
                    # Device has other content
                    self._unreachable_counts.pop(device_key, None)
                    if previous_status != 'other_content':
                        self.device_manager.update_active_device(
                            device_key=device_key,
                            status='other_content',
                            last_status_change=current_time,
                            last_checked=datetime.now().isoformat()
                        )
                    else:
                        self.device_manager.update_active_device(device_key, 'other_content', last_checked=datetime.now().isoformat())
                    _LOGGER.info("Device %s (%s) has other content (not our dashboard and not idle)", device_name, ip)
            else:
                # First time seeing this device
                if is_casting:  # Use the single status check result
                    status = 'connected'
                    _LOGGER.info("Device %s (%s) is casting our dashboard", device_name, ip)
                elif is_idle:
                    status = 'disconnected'
                    _LOGGER.info("Device %s (%s) is idle, will attempt to connect after stabilization period", device_name, ip)
                elif is_unreachable:
                    status = 'disconnected'
                    _LOGGER.warning("Device %s (%s) is unreachable, will retry next cycle", device_name, ip)
                else:
                    status = 'other_content'
                    _LOGGER.info("Device %s (%s) has other content, will not connect", device_name, ip)
                
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
        
        _LOGGER.info("Found %s active dashboard casts to stop", len(connected_devices))
        
        # Stop each connected device
        for device_key, device_info in connected_devices.items():
            ip = device_info.get('ip')
            name = device_info.get('name', 'Unknown device')
            
            if not ip:
                _LOGGER.warning("No IP found for device %s, skipping stop command", name)
                continue

            _LOGGER.info("Stopping dashboard cast on %s (%s)", name, ip)
            success = await self.async_stop_casting(ip)

            if success:
                _LOGGER.info("Successfully stopped dashboard cast on %s (%s)", name, ip)
                self.device_manager.update_active_device(
                    device_key=device_key,
                    status='stopped',
                    last_checked=datetime.now().isoformat()
                )
            else:
                _LOGGER.error("Failed to stop dashboard cast on %s (%s)", name, ip)
        
        _LOGGER.info("Finished stopping all active dashboard casts")
    
    def set_stats_manager(self, stats_manager):
        """Set the stats manager reference and share the device manager with it.

        Args:
            stats_manager: The StatsManager instance to use.
        """
        self.stats_manager = stats_manager
        # Share the device manager with stats manager
        self.stats_manager.set_device_manager(self.device_manager)
    
    async def initialize_devices(self):
        """Discover IPs and perform the initial cast for all configured devices.

        Returns:
            True when initialization is complete (even if some devices failed).
        """
        # Perform a single scan to find all devices
        device_ip_map = {}
        for device_name in self.devices.keys():
            ip = await self._async_resolve_device_ip(device_name)
            if ip:
                device_ip_map[device_name] = ip
            else:
                _LOGGER.error("Could not get IP for %s, skipping initial setup for this device", device_name)
                
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
                _LOGGER.info("Casting disabled for device %s, skipping initial cast", device_name)
                continue

            # Skip devices outside their time window
            if not is_in_window:
                _LOGGER.info("Outside all casting time windows for %s, skipping initial cast", device_name)
                continue
            
            # Check if device is within casting time window
            is_in_time_window = await self.time_window_checker.async_is_within_time_window(device_name, current_config)
            
            # Skip devices outside their time window
            if not is_in_time_window:
                _LOGGER.info("Outside casting time window for %s, skipping initial cast", device_name)
                continue
            
            # Check if media is playing
            if await self.device_manager.async_is_media_playing(ip):
                _LOGGER.info("Media is currently playing on %s, skipping initial cast", device_name)
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
                    _LOGGER.info("Speaker Group playback is active for %s, skipping initial cast", device_name)
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
        """Cast the configured dashboard to a device, updating its tracked status.

        Args:
            device_name: The display name of the device.
            device_config: The dashboard configuration dict (must contain 'dashboard_url').
            ip: Pre-resolved IP address. If None, it will be resolved automatically.
        """
        _LOGGER.info("Starting casting to %s", device_name)
        
        # Get device IP if not provided
        if not ip:
            ip = await self._async_resolve_device_ip(device_name)
            if not ip:
                _LOGGER.error("Could not get IP for %s, skipping", device_name)
                return
        
        # Check if media is playing before casting
        if await self.device_manager.async_is_media_playing(ip):
            _LOGGER.info("Media is currently playing on %s, skipping cast", device_name)
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
            _LOGGER.info("Casting already in progress for %s (%s), skipping", device_name, ip)
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
            _LOGGER.info("Successfully connected to %s (%s)", device_name, ip)
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
            _LOGGER.error("Failed to connect to %s (%s)", device_name, ip)
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
        """Refresh active device configs from time windows and flag changed dashboards.

        Returns:
            List of device names whose dashboard URL changed since the last update.
        """
        updated_devices = []
        
        for device_name, device_configs in self.devices.items():
            # Get the current device config based on the time window
            current_config, is_in_window = self.time_window_checker.get_current_device_config(device_name, device_configs)
            
            # Check if this device already has an active config
            if device_name in self.active_device_configs:
                previous_config = self.active_device_configs[device_name]['config']
                
                # Check if the dashboard URL has changed
                if (previous_config.get('dashboard_url') != current_config.get('dashboard_url')):
                    _LOGGER.info("Dashboard configuration changed for %s: new dashboard URL: %s", device_name, current_config.get('dashboard_url'))
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
        """Run one full monitoring cycle across all configured devices.

        Skips the cycle if a previous one is still running. Called periodically
        by async_track_time_interval and also triggered on demand.
        """
        # Use a lock to prevent monitoring cycles from overlapping
        if self.monitor_lock.locked():
            _LOGGER.debug("Previous monitoring cycle still running, skipping this cycle")
            return
            
        async with self.monitor_lock:
            _LOGGER.debug("Running device status check")
            
            # Update device configurations based on time windows
            updated_devices = await self.async_update_device_configs()
            if updated_devices:
                _LOGGER.info("Devices with updated dashboard configurations: %s", updated_devices)
                
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
                        _LOGGER.warning("Could not get IP for %s, skipping check", device_name)
                except Exception as e:
                    _LOGGER.error("Error getting IP for %s: %s, skipping check", device_name, e)
            
            # Process all devices concurrently - one slow/unresponsive device won't block others
            async def _process_device_safe(device_name):
                """Process a single device, swallowing exceptions so others are not blocked."""
                if device_name not in device_ip_map:
                    return
                ip = device_ip_map[device_name]
                if device_name not in self.active_device_configs:
                    _LOGGER.warning("No active configuration for %s, skipping", device_name)
                    return
                current_config = self.active_device_configs[device_name]['config']
                try:
                    await self._process_single_device(device_name, ip, current_config)
                except Exception as e:
                    _LOGGER.error("Unexpected error processing %s: %s", device_name, e)

            await asyncio.gather(*[_process_device_safe(name) for name in self.devices.keys()])

    async def async_stop_casting(self, ip):
        """Send a catt stop command to a device.

        Waits for any in-progress casting operation to finish before stopping.

        Args:
            ip: The IP address of the device to stop.

        Returns:
            True if the stop command succeeded, False otherwise.
        """
        try:
            # Check if a cast operation is in progress
            if ip in self.casting_manager.active_casting_operations:
                _LOGGER.info("Casting operation in progress for %s, waiting for it to complete before stopping", ip)
                # Wait up to 30 seconds for the operation to complete
                for _ in range(30):
                    if ip not in self.casting_manager.active_casting_operations:
                        break
                    await asyncio.sleep(1)

                if ip in self.casting_manager.active_casting_operations:
                    _LOGGER.warning("Casting operation still in progress after 30s wait, proceeding with stop")

            cmd = ['catt', '-d', ip, 'stop']
            _LOGGER.debug("Executing stop command: %s", ' '.join(cmd))
            
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
                _LOGGER.debug("Stop command stdout: %s", stdout_str)
                _LOGGER.debug("Stop command stderr: %s", stderr_str)

                if process.returncode == 0:
                    _LOGGER.info("Successfully stopped casting on device at %s", ip)
                    return True
                else:
                    _LOGGER.error("Failed to stop casting on device at %s: %s", ip, stderr_str)
                    return False
            except asyncio.TimeoutError:
                _LOGGER.error("Stop command timed out for %s", ip)
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                return False
                
        except Exception as e:
            _LOGGER.error("Error stopping casting on device at %s: %s", ip, e)
            return False

    async def async_reconnect_device(self, device_name, ip, device_config):
        """Attempt to reconnect a device that is no longer casting the dashboard.

        Skips reconnection if media is playing, a speaker group is active, the
        time window has passed, too many retries have occurred, or the device
        reports non-idle content.

        Args:
            device_name: The display name of the device.
            ip: The IP address of the device.
            device_config: The dashboard configuration dict for this device.

        Returns:
            True if reconnection succeeded, False otherwise.
        """
        device_key = f"{device_name}_{ip}"
        
        # Check if a cast is already in progress
        if ip in self.casting_manager.active_casting_operations:
            _LOGGER.info("Casting already in progress for %s (%s), skipping reconnect", device_name, ip)
            self.device_manager.update_active_device(
                device_key=device_key,
                status=STATUS_CASTING_IN_PROGRESS,
                last_checked=datetime.now().isoformat()
            )
            return False
        
        # Skip if outside time window
        if not await self.time_window_checker.async_is_within_time_window(device_name, device_config):
            _LOGGER.info("Outside casting time window for %s, skipping reconnect", device_name)
            return False
        
        # Check if the device is part of an active speaker group
        speaker_groups = device_config.get('speaker_groups')
        if speaker_groups:
            if await self.device_manager.async_check_speaker_group_state(ip, speaker_groups):
                _LOGGER.info("Speaker Group playback is active for %s, skipping reconnect", device_name)
                active_device = self.device_manager.get_active_device(device_key)
                if active_device:
                    self.device_manager.update_active_device(device_key, 'speaker_group_active')
                return False
        
        # Check if media is playing before attempting to reconnect
        if await self.device_manager.async_is_media_playing(ip):
            _LOGGER.info("Media is currently playing on %s, skipping reconnect", device_name)
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
                _LOGGER.warning("Device %s (%s) has had %s reconnect attempts, backing off", device_name, ip, attempts)
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
                    _LOGGER.info("Device %s (%s) shows non-idle status, skipping reconnect", device_name, ip)
                    if active_device:
                        self.device_manager.update_active_device(device_key, 'other_content')
                    return False
        except asyncio.TimeoutError:
            _LOGGER.warning("Status check timed out for %s (%s)", device_name, ip)
            status_process.terminate()
            try:
                await asyncio.wait_for(status_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                status_process.kill()
            # Skip reconnect if we can't determine status
            return False
        except Exception as e:
            _LOGGER.error("Error checking status before reconnect: %s", e)
            return False
        
        # Update status to indicate casting is in progress
        self.device_manager.update_active_device(
            device_key=device_key,
            status=STATUS_CASTING_IN_PROGRESS,
            last_checked=datetime.now().isoformat()
        )
        
        _LOGGER.info("Attempting to reconnect to %s (%s)", device_name, ip)
        if self.stats_manager:
            await self.stats_manager.async_update_health_stats(device_key, EVENT_RECONNECT_ATTEMPT)
        dashboard_url = device_config.get('dashboard_url')
        _LOGGER.debug("Casting URL %s to device %s (%s)", dashboard_url, device_name, ip)
        success = await self.casting_manager.async_cast_dashboard(ip, dashboard_url, device_config)
        
        if success:
            _LOGGER.info("Successfully reconnected to %s (%s)", device_name, ip)
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
            _LOGGER.error("Failed to reconnect to %s (%s)", device_name, ip)
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
        """Resolve a device IP address with a hard timeout.

        Args:
            device_name: The display name of the device.
            timeout: Maximum seconds to wait for IP resolution.

        Returns:
            The IP address string, or None on timeout or error.
        """
        try:
            return await asyncio.wait_for(
                self._async_resolve_device_ip(device_name),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            _LOGGER.error("Timed out getting IP for %s after %s seconds", device_name, timeout)
            return None
        except Exception as e:
            _LOGGER.error("Error getting IP for %s: %s", device_name, e)
            return None
