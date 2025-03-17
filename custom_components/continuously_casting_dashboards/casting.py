"""Casting functionality for Continuously Casting Dashboards."""
import asyncio
import logging
from datetime import datetime
from homeassistant.core import HomeAssistant
from .const import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, DEFAULT_VERIFICATION_WAIT_TIME

_LOGGER = logging.getLogger(__name__)

class CastingManager:
    """Class to handle casting to devices."""

    def __init__(self, hass: HomeAssistant, config: dict, device_manager):
        """Initialize the casting manager."""
        self.hass = hass
        self.config = config
        self.device_manager = device_manager
        self.cast_delay = config.get('cast_delay', 0)

    async def async_cast_dashboard(self, ip, dashboard_url, device_config):
        """Cast a dashboard to a device with retry logic."""
        # Enhanced debug logging for troubleshooting
        _LOGGER.debug(f"Device config received for {ip}: {device_config}")
        
        # Get config volume (use None if not specified)
        config_volume = device_config.get('volume', None)
        _LOGGER.debug(f"Config volume for {ip}: {config_volume}")
        
        max_retries = self.config.get('max_retries', DEFAULT_MAX_RETRIES)
        retry_delay = self.config.get('retry_delay', DEFAULT_RETRY_DELAY)
        verification_wait_time = self.config.get('verification_wait_time', DEFAULT_VERIFICATION_WAIT_TIME)
        
        for attempt in range(max_retries):
            try:
                # Check if media is playing before casting
                if await self.device_manager.async_is_media_playing(ip):
                    _LOGGER.info(f"Media is currently playing on device at {ip}, skipping cast attempt")
                    return False
                
                # Before casting, check the current volume
                current_volume = await self.async_get_current_volume(ip)
                _LOGGER.debug(f"Current volume before casting for {ip}: {current_volume}")
                
                # Use catt to cast the dashboard
                _LOGGER.debug(f"Casting {dashboard_url} to {ip} (attempt {attempt+1}/{max_retries})")
                
                # First stop any current casting
                stop_cmd = ['catt', '-d', ip, 'stop']
                _LOGGER.debug(f"Executing stop command: {' '.join(stop_cmd)}")
                stop_process = await asyncio.create_subprocess_exec(
                    *stop_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await stop_process.communicate()
                
                # Set volume to 0 initially
                vol_cmd = ['catt', '-d', ip, 'volume', '0']
                _LOGGER.debug(f"Setting initial volume to 0: {' '.join(vol_cmd)}")
                vol_process = await asyncio.create_subprocess_exec(
                    *vol_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await vol_process.communicate()
                
                # Cast the dashboard
                cmd = ['catt', '-d', ip, 'cast_site', dashboard_url]
                _LOGGER.debug(f"Executing cast command: {' '.join(cmd)}")
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                # Log the full output
                stdout_str = stdout.decode().strip()
                stderr_str = stderr.decode().strip()
                _LOGGER.debug(f"Cast command stdout: {stdout_str}")
                _LOGGER.debug(f"Cast command stderr: {stderr_str}")
                _LOGGER.debug(f"Cast command return code: {process.returncode}")
                
                # Check if the cast command itself failed
                if process.returncode != 0:
                    error_msg = stderr_str or "Unknown error"
                    _LOGGER.error(f"Catt command failed: {error_msg}")
                    raise Exception(f"Catt command failed: {error_msg}")
                
                # If stdout contains success message like "Casting ... on device", consider it likely successful
                cast_likely_succeeded = "Casting" in stdout_str and "on" in stdout_str
                
                # Verify the device is actually casting
                _LOGGER.debug(f"Waiting {verification_wait_time} seconds to verify casting...")
                await asyncio.sleep(verification_wait_time)  # Give it more time to start casting
                
                status_check = await self.device_manager.async_check_device_status(ip)
                _LOGGER.debug(f"Status check result: {status_check}")
                
                # Only set the volume after the status check confirms casting is successful
                if status_check or cast_likely_succeeded:
                    # Determine the volume to set after casting:
                    # 1. If config_volume is specified and not None, use it (multiplied by 10 to get percentage)
                    # 2. If no config_volume or it's None/unspecified, use the current_volume we detected
                    if config_volume is not None:
                        # Convert from scale of 1-10 to percentage (0-100)
                        final_volume = int(config_volume * 10)
                        _LOGGER.debug(f"Using config volume: {config_volume} (converted to {final_volume}%)")
                    else:
                        # Current volume from device is already in percentage
                        final_volume = current_volume
                        _LOGGER.debug(f"Using current volume from device: {final_volume}%")
                    
                    # Ensure we have a reasonable volume value
                    if final_volume is None or not isinstance(final_volume, (int, float)):
                        final_volume = 50  # Default fallback (50%)
                    
                    # Make sure volume is within 0-100 range
                    final_volume = max(0, min(100, final_volume))
                    
                    _LOGGER.debug(f"Setting final volume to {final_volume}% for device at {ip}")
                    final_vol_cmd = ['catt', '-d', ip, 'volume', str(final_volume)]
                    _LOGGER.debug(f"Executing final volume command: {' '.join(final_vol_cmd)}")
                    
                    final_vol_process = await asyncio.create_subprocess_exec(
                        *final_vol_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    vol_stdout, vol_stderr = await final_vol_process.communicate()
                    
                    # Log volume command output
                    vol_stdout_str = vol_stdout.decode().strip()
                    vol_stderr_str = vol_stderr.decode().strip()
                    _LOGGER.debug(f"Volume command stdout: {vol_stdout_str}")
                    _LOGGER.debug(f"Volume command stderr: {vol_stderr_str}")
                    _LOGGER.debug(f"Volume command return code: {final_vol_process.returncode}")
                
                # Return success/failure based on status check
                if status_check:
                    _LOGGER.info(f"Successfully cast to device at {ip}")
                    return True
                elif cast_likely_succeeded:
                    _LOGGER.info(f"Cast command succeeded but status check didn't detect dashboard yet. Assuming success.")
                    return True
                else:
                    _LOGGER.warning(f"Cast command appeared to succeed but device status check failed")
                    raise Exception("Device not casting after command")
                
            except Exception as e:
                _LOGGER.error(f"Cast error on attempt {attempt+1}/{max_retries}: {str(e)}")
                
                if attempt < max_retries - 1:
                    _LOGGER.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    _LOGGER.error(f"Failed to cast to device at {ip} after {max_retries} attempts")
                    return False
        
        return False
        
    async def async_get_current_volume(self, ip):
        """Get the current volume of a device."""
        try:
            cmd = ['catt', '-d', ip, 'status']
            _LOGGER.debug(f"Getting current volume for {ip}: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                _LOGGER.warning(f"Failed to get current volume for {ip}: {stderr.decode().strip()}")
                return 50  # Default fallback (50%)
                
            status_output = stdout.decode().strip()
            _LOGGER.debug(f"Current status output: {status_output}")
            
            # Try to extract volume information
            for line in status_output.splitlines():
                if line.startswith("Volume:"):
                    try:
                        volume_str = line.split(":", 1)[1].strip()
                        volume = int(volume_str)
                        _LOGGER.debug(f"Extracted current volume: {volume}%")
                        return volume
                    except (ValueError, IndexError) as e:
                        _LOGGER.warning(f"Failed to parse volume from status: {e}")
                        return 50  # Default fallback (50%)
            
            # If we didn't find volume info
            _LOGGER.warning(f"No volume information found in status output")
            return 50  # Default fallback (50%)
            
        except Exception as e:
            _LOGGER.error(f"Error getting current volume for {ip}: {str(e)}")
            return 50  # Default fallback (50%)