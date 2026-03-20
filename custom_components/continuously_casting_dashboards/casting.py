"""Casting functionality for Continuously Casting Dashboards.

This module handles:
- Dashboard casting via catt commands
- Retry logic with exponential backoff
- Volume management before/after casting
- Subprocess lifecycle management
"""
import asyncio
import logging
import time
from datetime import datetime
from homeassistant.core import HomeAssistant
from .const import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, DEFAULT_VERIFICATION_WAIT_TIME, DEFAULT_CASTING_TIMEOUT, TIMEOUT_PROCESS_TERMINATE, TIMEOUT_PROCESS_KILL, TIMEOUT_VOLUME_COMMAND

_LOGGER = logging.getLogger(__name__)


class CastingManager:
    """Class to handle casting to devices.

    Manages the casting lifecycle including:
    - Pre-cast checks (media playing detection)
    - Volume management (save/restore)
    - Subprocess tracking and cleanup
    - Retry logic with exponential backoff
    """

    def __init__(self, hass: HomeAssistant, config: dict, device_manager):
        """Initialize the casting manager.

        Args:
            hass: The Home Assistant instance.
            config: The integration configuration dictionary.
            device_manager: The DeviceManager instance for pre-cast status checks.
        """
        self.hass = hass
        self.config = config
        self.device_manager = device_manager
        self.cast_delay = config.get('cast_delay', 0)
        # Track active casting operations by IP address
        self.active_casting_operations: dict[str, dict] = {}
        # Track subprocess objects to ensure proper cleanup
        self.active_subprocesses: dict[str, asyncio.subprocess.Process] = {}

    async def cleanup(self) -> None:
        """Clean up all resources held by the casting manager.

        Terminates all active subprocesses and clears tracking dicts.
        Call this when unloading the integration.
        """
        _LOGGER.debug("Cleaning up casting manager resources")

        # Terminate all active subprocesses
        for key, process in list(self.active_subprocesses.items()):
            if process.returncode is None:  # Process is still running
                _LOGGER.debug("Terminating subprocess: %s", key)
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Force killing subprocess: %s", key)
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_KILL)
                    except asyncio.TimeoutError:
                        pass  # Process may be unkillable, continue cleanup

        self.active_subprocesses.clear()
        self.active_casting_operations.clear()
        _LOGGER.debug("Casting manager cleanup complete")

    async def async_cast_dashboard(self, ip, dashboard_url, device_config):
        """Cast a dashboard URL to a device using catt, with exponential-backoff retry.

        Skips the cast if another operation for the same IP is already in progress.
        Stops any current cast, sets volume to 0, casts the site, verifies success,
        then restores volume.

        Args:
            ip: The device IP address.
            dashboard_url: The URL to cast.
            device_config: Per-device configuration dict (e.g. contains 'volume').

        Returns:
            True if the dashboard was successfully cast, False otherwise.
        """
        # Check if an active casting operation is already in progress for this IP
        if ip in self.active_casting_operations:
            last_start = self.active_casting_operations[ip]['start_time']
            current_time = time.time()
            elapsed = current_time - last_start
            
            # If a cast has been running too long, it might be stuck - force cleanup
            timeout = self.config.get('casting_timeout', DEFAULT_CASTING_TIMEOUT)
            if elapsed > timeout:
                _LOGGER.warning("Casting to %s has been running for %.1fs which exceeds timeout of %ss. Force cleaning up.", ip, elapsed, timeout)
                await self.cleanup_casting_operation(ip)
            else:
                _LOGGER.info("Casting operation already in progress for %s (started %.1fs ago). Skipping new cast request.", ip, elapsed)
                return False
        
        # Mark this IP as having an active casting operation
        self.active_casting_operations[ip] = {
            'start_time': time.time(),
            'dashboard_url': dashboard_url
        }
        
        try:
            # Enhanced debug logging for troubleshooting
            _LOGGER.debug("Device config received for %s: %s", ip, device_config)

            # Get config volume (use None if not specified)
            config_volume = device_config.get('volume', None)
            _LOGGER.debug("Config volume for %s: %s", ip, config_volume)
            
            max_retries = self.config.get('max_retries', DEFAULT_MAX_RETRIES)
            retry_delay = self.config.get('retry_delay', DEFAULT_RETRY_DELAY)
            verification_wait_time = self.config.get('verification_wait_time', DEFAULT_VERIFICATION_WAIT_TIME)
            
            for attempt in range(max_retries):
                try:
                    # Check if media is playing before casting
                    if await self.device_manager.async_is_media_playing(ip):
                        _LOGGER.info("Media is currently playing on device at %s, skipping cast attempt", ip)
                        return False
                    
                    # Before casting, check the current volume
                    current_volume = await self.async_get_current_volume(ip)
                    _LOGGER.debug("Current volume before casting for %s: %s", ip, current_volume)

                    # Use catt to cast the dashboard
                    _LOGGER.debug("Casting %s to %s (attempt %s/%s)", dashboard_url, ip, attempt + 1, max_retries)
                    
                    # First stop any current casting
                    stop_cmd = ['catt', '-d', ip, 'stop']
                    _LOGGER.debug("Executing stop command: %s", ' '.join(stop_cmd))
                    stop_process = await asyncio.create_subprocess_exec(
                        *stop_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    self.active_subprocesses[f"{ip}_stop"] = stop_process
                    try:
                        await asyncio.wait_for(stop_process.communicate(), timeout=TIMEOUT_VOLUME_COMMAND)
                    except asyncio.TimeoutError:
                        _LOGGER.warning("Stop command timed out for %s", ip)
                        stop_process.terminate()
                    finally:
                        self.active_subprocesses.pop(f"{ip}_stop", None)

                    # Set volume to 0 initially
                    vol_cmd = ['catt', '-d', ip, 'volume', '0']
                    _LOGGER.debug("Setting initial volume to 0: %s", ' '.join(vol_cmd))
                    vol_process = await asyncio.create_subprocess_exec(
                        *vol_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    self.active_subprocesses[f"{ip}_vol_initial"] = vol_process
                    try:
                        await asyncio.wait_for(vol_process.communicate(), timeout=TIMEOUT_VOLUME_COMMAND)
                    except asyncio.TimeoutError:
                        _LOGGER.warning("Initial volume command timed out for %s", ip)
                        vol_process.terminate()
                    finally:
                        self.active_subprocesses.pop(f"{ip}_vol_initial", None)
                    
                    # Cast the dashboard
                    cmd = ['catt', '-d', ip, 'cast_site', dashboard_url]
                    _LOGGER.debug("Executing cast command: %s", ' '.join(cmd))
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    self.active_subprocesses[f"{ip}_cast"] = process
                    
                    # Use a timeout to prevent hanging processes
                    timeout = self.config.get('casting_timeout', DEFAULT_CASTING_TIMEOUT)
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                        self.active_subprocesses.pop(f"{ip}_cast", None)
                    except asyncio.TimeoutError:
                        _LOGGER.error("Cast command timed out after %ss", timeout)
                        if f"{ip}_cast" in self.active_subprocesses:
                            process = self.active_subprocesses.pop(f"{ip}_cast")
                            process.terminate()
                            try:
                                await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                            except asyncio.TimeoutError:
                                _LOGGER.error("Force killing cast process for %s", ip)
                                process.kill()
                        raise Exception(f"Cast command timed out after {timeout}s")
                    
                    # Log the full output
                    stdout_str = stdout.decode().strip()
                    stderr_str = stderr.decode().strip()
                    _LOGGER.debug("Cast command stdout: %s", stdout_str)
                    _LOGGER.debug("Cast command stderr: %s", stderr_str)
                    _LOGGER.debug("Cast command return code: %s", process.returncode)
                    
                    # Check if the cast command itself failed
                    if process.returncode != 0:
                        error_msg = stderr_str or "Unknown error"
                        _LOGGER.error("Catt command failed: %s", error_msg)
                        raise Exception(f"Catt command failed: {error_msg}")
                    
                    # If stdout contains success message like "Casting ... on device", consider it likely successful
                    cast_likely_succeeded = "Casting" in stdout_str and "on" in stdout_str
                    
                    # Verify the device is actually casting
                    _LOGGER.debug("Waiting %s seconds to verify casting...", verification_wait_time)
                    await asyncio.sleep(verification_wait_time)  # Give it more time to start casting

                    status_check = await self.device_manager.async_check_device_status(ip)
                    _LOGGER.debug("Status check result: %s", status_check)
                    
                    # Only set the volume after the status check confirms casting is successful
                    if status_check or cast_likely_succeeded:
                        # Determine the volume to set after casting:
                        # 1. If config_volume is specified and not None, use it (multiplied by 10 to get percentage)
                        # 2. If no config_volume or it's None/unspecified, use the current_volume we detected
                        if config_volume is not None:
                            # Volume is stored as 0-100 from the UI slider
                            final_volume = int(config_volume)
                            _LOGGER.debug("Using config volume: %s%%", final_volume)
                        else:
                            # Current volume from device is already in percentage
                            final_volume = current_volume
                            _LOGGER.debug("Using current volume from device: %s%%", final_volume)
                        
                        # Ensure we have a reasonable volume value
                        if final_volume is None or not isinstance(final_volume, (int, float)):
                            final_volume = 50  # Default fallback (50%)
                        
                        # Make sure volume is within 0-100 range
                        final_volume = max(0, min(100, final_volume))
                        
                        _LOGGER.debug("Setting final volume to %s%% for device at %s", final_volume, ip)
                        final_vol_cmd = ['catt', '-d', ip, 'volume', str(final_volume)]
                        _LOGGER.debug("Executing final volume command: %s", ' '.join(final_vol_cmd))
                        
                        final_vol_process = await asyncio.create_subprocess_exec(
                            *final_vol_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        self.active_subprocesses[f"{ip}_vol_final"] = final_vol_process
                        
                        try:
                            vol_stdout, vol_stderr = await asyncio.wait_for(final_vol_process.communicate(), timeout=TIMEOUT_VOLUME_COMMAND)
                            self.active_subprocesses.pop(f"{ip}_vol_final", None)
                        except asyncio.TimeoutError:
                            _LOGGER.error("Volume command timed out")
                            if f"{ip}_vol_final" in self.active_subprocesses:
                                process = self.active_subprocesses.pop(f"{ip}_vol_final")
                                process.terminate()
                                try:
                                    await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                                except asyncio.TimeoutError:
                                    process.kill()
                        
                        # Log volume command output
                        vol_stdout_str = vol_stdout.decode().strip() if 'vol_stdout' in locals() else ""
                        vol_stderr_str = vol_stderr.decode().strip() if 'vol_stderr' in locals() else ""
                        _LOGGER.debug("Volume command stdout: %s", vol_stdout_str)
                        _LOGGER.debug("Volume command stderr: %s", vol_stderr_str)
                        if 'final_vol_process' in locals():
                            _LOGGER.debug("Volume command return code: %s", final_vol_process.returncode)
                    
                    # Return success/failure based on status check
                    if status_check:
                        _LOGGER.info("Successfully cast to device at %s", ip)
                        return True
                    elif cast_likely_succeeded:
                        _LOGGER.info("Cast command succeeded but status check didn't detect dashboard yet. Assuming success.")
                        return True
                    else:
                        _LOGGER.warning("Cast command appeared to succeed but device status check failed")
                        raise Exception("Device not casting after command")
                    
                except Exception as e:
                    _LOGGER.error("Cast error on attempt %s/%s: %s", attempt + 1, max_retries, e)

                    if attempt < max_retries - 1:
                        _LOGGER.info("Retrying in %s seconds...", retry_delay)
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                    else:
                        _LOGGER.error("Failed to cast to device at %s after %s attempts", ip, max_retries)
                        return False
            
            return False
        
        finally:
            # Always clean up, regardless of success or failure
            await self.cleanup_casting_operation(ip)
    
    async def cleanup_casting_operation(self, ip):
        """Terminate lingering subprocesses and remove the active operation marker for an IP.

        Args:
            ip: The device IP address whose operations should be cleaned up.
        """
        # Clear the active casting operation marker
        self.active_casting_operations.pop(ip, None)
        
        # Clean up any remaining subprocesses for this IP
        for key in list(self.active_subprocesses.keys()):
            if key.startswith(f"{ip}_"):
                process = self.active_subprocesses.pop(key)
                if process.returncode is None:  # Process is still running
                    _LOGGER.warning("Terminating lingering process: %s", key)
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                    except asyncio.TimeoutError:
                        _LOGGER.error("Force killing process: %s", key)
                        process.kill()
        
    async def async_get_current_volume(self, ip):
        """Query and return the current volume percentage of a device.

        Args:
            ip: The device IP address.

        Returns:
            Volume as an integer (0-100). Defaults to 50 on failure or missing data.
        """
        try:
            cmd = ['catt', '-d', ip, 'status']
            _LOGGER.debug("Getting current volume for %s: %s", ip, ' '.join(cmd))
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.active_subprocesses[f"{ip}_status_vol"] = process
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_VOLUME_COMMAND)
                self.active_subprocesses.pop(f"{ip}_status_vol", None)
            except asyncio.TimeoutError:
                _LOGGER.error("Volume status command timed out")
                if f"{ip}_status_vol" in self.active_subprocesses:
                    process = self.active_subprocesses.pop(f"{ip}_status_vol")
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                    except asyncio.TimeoutError:
                        process.kill()
                return 50  # Default fallback
            
            if process.returncode != 0:
                _LOGGER.warning("Failed to get current volume for %s: %s", ip, stderr.decode().strip())
                return 50  # Default fallback (50%)
                
            status_output = stdout.decode().strip()
            _LOGGER.debug("Current status output: %s", status_output)
            
            # Try to extract volume information
            for line in status_output.splitlines():
                if line.startswith("Volume:"):
                    try:
                        volume_str = line.split(":", 1)[1].strip()
                        volume = int(volume_str)
                        _LOGGER.debug("Extracted current volume: %s%%", volume)
                        return volume
                    except (ValueError, IndexError) as e:
                        _LOGGER.warning("Failed to parse volume from status: %s", e)
                        return 50  # Default fallback (50%)
            
            # If we didn't find volume info
            _LOGGER.warning("No volume information found in status output")
            return 50  # Default fallback (50%)
            
        except Exception as e:
            _LOGGER.error("Error getting current volume for %s: %s", ip, e)
            return 50  # Default fallback (50%)
        finally:
            # Clean up any lingering subprocess
            if f"{ip}_status_vol" in self.active_subprocesses:
                process = self.active_subprocesses.pop(f"{ip}_status_vol")
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                    except asyncio.TimeoutError:
                        process.kill()
