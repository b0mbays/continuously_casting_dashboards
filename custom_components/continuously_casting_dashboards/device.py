"""Device discovery and management for Continuously Casting Dashboards."""
import asyncio
import logging
import time
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class DeviceManager:
    """Class to manage device discovery and status checks."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the device manager."""
        self.hass = hass
        self.config = config
        self.device_ip_cache = {}  # Cache for device IPs
        self.active_devices = {}   # Track active devices
    
    async def async_get_device_ip(self, device_name):
        """Get IP address for a device name using catt scan without relying on cached mappings."""
        try:
            _LOGGER.info(f"Scanning for device: {device_name}")
            # Check if we've already cached the device to speed up lookups
            if device_name in self.device_ip_cache and self.device_ip_cache[device_name]['timestamp'] > (time.time() - 300):
                _LOGGER.debug(f"Using cached IP for {device_name}: {self.device_ip_cache[device_name]['ip']}")
                return self.device_ip_cache[device_name]['ip']
                
            # Do a fresh scan
            process = await asyncio.create_subprocess_exec(
                'catt', 'scan',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            scan_output = stdout.decode()
            _LOGGER.debug(f"Full scan output: {scan_output}")
            
            if process.returncode != 0:
                _LOGGER.warning(f"Catt scan failed: {stderr.decode().strip()}")
                return None
            
            # Parse scan results and find exact matching device
            found_devices = []
            for line in scan_output.splitlines():
                # Skip the header line or empty lines
                if "Scanning Chromecasts..." in line or not line.strip():
                    continue
                
                # Parse format: IP - Name
                parts = line.split(' - ')
                if len(parts) < 2:
                    continue
                    
                ip = parts[0].strip()
                found_name = parts[1].strip() if len(parts) > 1 else ""
                
                # Collect all found devices for logging
                found_devices.append((found_name, ip))
                
                # Update the cache for all found devices to speed up future lookups
                self.device_ip_cache[found_name] = {
                    'ip': ip,
                    'timestamp': time.time()
                }
                
                # Exact match check (case-insensitive)
                if found_name.lower() == device_name.lower():
                    _LOGGER.info(f"Matched device '{device_name}' with IP {ip}")
                    return ip
            
            # If we get here, no exact match was found
            found_names = [name for name, _ in found_devices]
            _LOGGER.warning(f"Device '{device_name}' not found in scan results. Found devices: {found_names}")
            _LOGGER.warning(f"Make sure the name matches exactly what appears in the scan output.")
            return None
        except Exception as e:
            _LOGGER.warning(f"Error scanning for devices: {str(e)}")
            return None

    async def async_is_media_playing(self, ip):
        """Check if media (like Spotify or YouTube) is playing or paused on the device."""
        try:
            _LOGGER.debug(f"Checking if media is playing on device at {ip}")
            cmd = ['catt', '-d', ip, 'status']
            _LOGGER.debug(f"Executing command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            # Log full output
            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()
            _LOGGER.debug(f"Status command stdout: {stdout_str}")
            _LOGGER.debug(f"Status command stderr: {stderr_str}")
            
            if process.returncode != 0:
                _LOGGER.warning(f"Status check failed with return code {process.returncode}: {stderr_str}")
                return False
                
            # Check for "idle" state that only shows volume info
            if len(stdout_str.splitlines()) <= 2 and all(line.startswith("Volume") for line in stdout_str.splitlines()):
                _LOGGER.debug(f"Device at {ip} is idle (only volume info returned)")
                return False
            
            # Check for a status line that contains "Casting: Starting" which indicates media is about to play
            if "Casting: Starting" in stdout_str:
                _LOGGER.info(f"Device at {ip} is starting to cast media")
                return True
                
            # Check for references to Google Assistant, which means a voice command is being handled
            if "assistant" in stdout_str.lower():
                _LOGGER.info(f"Device at {ip} is processing a Google Assistant command")
                return True
                
            # If we get "Idle" or "Nothing is currently playing", no media is playing
            if "Idle" in stdout_str or "Nothing is currently playing" in stdout_str:
                _LOGGER.debug(f"Device at {ip} is idle or not playing anything")
                return False
                
            # Check if we have a "State: PLAYING" or "State: PAUSED" or "State: BUFFERING" line
            for line in stdout_str.splitlines():
                if "State:" in line and ("PLAYING" in line or "PAUSED" in line or "BUFFERING" in line):
                    _LOGGER.info(f"Found {line} - media is active on device at {ip}")
                    return True
                    
            # Check for a "Title:" line that is not "Dummy" (dashboard)
            for line in stdout_str.splitlines():
                if "Title:" in line and "Dummy" not in line:
                    _LOGGER.info(f"Found '{line}' - media content is active on device at {ip}")
                    return True
                    
            # Check if any known media app name is in the output
            status_lower = stdout_str.lower()
            media_apps = ["spotify", "youtube", "netflix", "plex", "disney+", "hulu", "amazon prime", "music", "audio", "video", "cast"]
            for app in media_apps:
                if app in status_lower:
                    _LOGGER.info(f"Found '{app}' in status - media app is active on device at {ip}")
                    return True
                    
            # At this point, check if anything is playing at all (that's not our dashboard)
            if "Dummy" not in stdout_str and ("playing" in status_lower or "paused" in status_lower or "buffering" in status_lower):
                _LOGGER.info(f"Found playing/paused/buffering state but not our dashboard - media is active on device at {ip}")
                return True
                
            _LOGGER.debug(f"No media playing on device at {ip}")
            return False
        except Exception as e:
            _LOGGER.warning(f"Error checking media status on device at {ip}: {str(e)}")
            return False

    async def async_check_device_status(self, ip):
        """Check if a device is still casting our dashboard specifically."""
        try:
            _LOGGER.debug(f"Checking status for device at {ip}")
            cmd = ['catt', '-d', ip, 'status']
            _LOGGER.debug(f"Executing command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            # Log full output
            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()
            _LOGGER.debug(f"Status command stdout: {stdout_str}")
            _LOGGER.debug(f"Status command stderr: {stderr_str}")
            _LOGGER.debug(f"Status command return code: {process.returncode}")
            
            # Parse output to check if it's actually casting our dashboard
            if process.returncode == 0:
                output = stdout_str
                
                # Check for "idle" state that only shows volume info
                if len(stdout_str.splitlines()) <= 2 and all(line.startswith("Volume") for line in stdout_str.splitlines()):
                    _LOGGER.debug(f"Device at {ip} is idle (only volume info returned)")
                    return False
                    
                # If device explicitly says idle or nothing playing, return False
                if "Idle" in output or "Nothing is currently playing" in output:
                    _LOGGER.debug(f"Device at {ip} is idle or not casting")
                    return False
                    
                # Look for "Dummy" or our dashboard URL, which indicates our dashboard is casting
                if "Dummy" in output:
                    dummy_line = next((line for line in output.splitlines() if "Dummy" in line), "")
                    _LOGGER.debug(f"Dashboard found: {dummy_line}")
                    return True
                
                # Check for dashboard-specific indicators in the output
                dashboard_indicators = ["8123", "dashboard", "kiosk", "homeassistant"]
                if any(indicator in output.lower() for indicator in dashboard_indicators):
                    _LOGGER.debug(f"Dashboard indicators found in status")
                    return True
                
                # If we get here, device is playing something but not our dashboard
                _LOGGER.debug(f"Device at {ip} is playing something, but not our dashboard")
                return False
            else:
                _LOGGER.warning(f"Status check failed with return code {process.returncode}: {stderr_str}")
                return False
        except Exception as e:
            _LOGGER.warning(f"Error checking device status at {ip}: {str(e)}")
            return False
            
    def get_active_device(self, device_key):
        """Get active device info by key."""
        return self.active_devices.get(device_key)
        
    def update_active_device(self, device_key, status, **kwargs):
        """Update or create an active device entry."""
        if device_key in self.active_devices:
            self.active_devices[device_key].update(status=status, **kwargs)
        else:
            # First time seeing this device
            device_data = {'status': status}
            device_data.update(kwargs)
            self.active_devices[device_key] = device_data
            
    def get_all_active_devices(self):
        """Get all active devices."""
        return self.active_devices
        
    def get_device_current_dashboard(self, device_key):
        """Get the current dashboard URL for a device if it exists."""
        if device_key in self.active_devices:
            return self.active_devices[device_key].get('current_dashboard')
        return None
