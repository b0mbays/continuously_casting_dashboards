"""Device discovery and management for Continuously Casting Dashboards.

This module handles:
- Device IP discovery via catt scan
- Device status checking (casting state, media playing, assistant active)
- IP address caching to reduce network scans
- Speaker group state detection
"""
import asyncio
import logging
import time
import re
from datetime import datetime
from homeassistant.core import HomeAssistant
from .const import (
    TIMEOUT_STATUS_CHECK,
    TIMEOUT_PROCESS_TERMINATE,
    TIMEOUT_SCAN,
    TIMEOUT_SCAN_TERMINATE,
    TIMEOUT_SPEAKER_GROUP,
)

_LOGGER = logging.getLogger(__name__)


def is_valid_ipv4(ip_string: str) -> bool:
    """Validate an IPv4 address string.

    Args:
        ip_string: The string to validate as an IPv4 address.

    Returns:
        True if valid IPv4 address (each octet 0-255), False otherwise.
    """
    if not ip_string:
        return False

    parts = ip_string.split('.')
    if len(parts) != 4:
        return False

    for part in parts:
        # Must be numeric
        if not part.isdigit():
            return False
        # Check range 0-255
        num = int(part)
        if num < 0 or num > 255:
            return False
        # Reject leading zeros (e.g., "01" or "001") except for "0" itself
        if len(part) > 1 and part[0] == '0':
            return False

    return True


# Legacy pattern kept for backward compatibility, but use is_valid_ipv4() instead
IP_PATTERN = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

# Pattern to extract playback position from Dummy cast title
# e.g. "Dummy 00:26:17 GMT+0000 (Greenwich Mean Time)"
_DUMMY_POSITION_RE = re.compile(r'^Dummy\s+(\d{2}:\d{2}:\d{2})\s+GMT', re.IGNORECASE)


def extract_dummy_position(status_output: str) -> str | None:
    """Extract the playback position string from a Dummy cast status output.

    Args:
        status_output: The raw text output from a catt status command.

    Returns:
        The position string (e.g. '00:26:17') if found, else None.
    """
    for line in status_output.splitlines():
        if line.startswith("Title:"):
            title = line.split(":", 1)[1].strip()
            match = _DUMMY_POSITION_RE.match(title)
            if match:
                return match.group(1)
    return None

class DeviceManager:
    """Class to manage device discovery and status checks."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the device manager.

        Args:
            hass: The Home Assistant instance.
            config: The integration configuration dictionary.
        """
        self.hass = hass
        self.config = config
        self.device_ip_cache = {}  # Cache for device IPs
        self.active_devices = {}   # Track active devices
        self.active_checks = {}    # Track active status checks
        self.status_cache = {}     # Short-lived cache for catt status output

    def _cache_status_output(self, ip, output):
        """Cache catt status output briefly to avoid duplicate network calls.

        Args:
            ip: The device IP address used as the cache key.
            output: The stdout string from the catt status command.
        """
        if not output:
            return
        self.status_cache[ip] = {
            "output": output,
            "timestamp": time.time(),
        }

    def _get_cached_status_output(self, ip, max_age=2.0):
        """Return cached catt status output if it is still within max_age seconds.

        Args:
            ip: The device IP address to look up.
            max_age: Maximum age in seconds before the cache entry is considered stale.

        Returns:
            The cached output string, or None if absent or stale.
        """
        cached = self.status_cache.get(ip)
        if not cached:
            return None
        if (time.time() - cached.get("timestamp", 0)) > max_age:
            return None
        return cached.get("output")

    def _status_indicates_assistant_activity(self, status_output):
        """Detect Google Assistant or timer/alarm/reminder activity in catt status output.

        Args:
            status_output: The raw stdout from a catt status command.

        Returns:
            True if Assistant or a related keyword is detected, False otherwise.
        """
        if not status_output:
            return False
        status_lower = status_output.lower()

        # Avoid matching "homeassistant" or "home assistant" as "assistant"
        sanitized = status_lower.replace("homeassistant", "").replace("home assistant", "")

        if "google assistant" in sanitized:
            return True

        # Match 'assistant' as a standalone word to reduce false positives
        if re.search(r"\bassistant\b", sanitized):
            return True

        assistant_keywords = [
            "timer",
            "alarm",
            "reminder",
            "stopwatch",
            "countdown",
        ]
        for keyword in assistant_keywords:
            if re.search(rf"\b{keyword}\b", sanitized):
                _LOGGER.debug("Assistant activity keyword matched: '%s' in status output", keyword)
                return True
        return False

    async def _async_run_status_command(self, ip, timeout=TIMEOUT_STATUS_CHECK, allow_cache=True):
        """Run catt status and return stdout, stderr, return code, and a cache-hit flag.

        Args:
            ip: The device IP address.
            timeout: Seconds to wait before timing out the subprocess.
            allow_cache: When True, return a cached result if one exists.

        Returns:
            A tuple of (stdout_str, stderr_str, returncode, from_cache).
            All values are None (except from_cache=False) on timeout.
        """
        if allow_cache:
            cached_output = self._get_cached_status_output(ip)
            if cached_output is not None:
                return cached_output, "", 0, True

        cmd = ['catt', '-d', ip, 'status']
        _LOGGER.debug("Executing command: %s", ' '.join(cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            _LOGGER.warning("Status check timed out for %s", ip)
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
            except asyncio.TimeoutError:
                process.kill()
            return None, None, None, False

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()
        _LOGGER.debug("Status command stdout: %s", stdout_str)
        _LOGGER.debug("Status command stderr: %s", stderr_str)

        if process.returncode == 0:
            self._cache_status_output(ip, stdout_str)

        return stdout_str, stderr_str, process.returncode, False
    
    async def async_get_device_ip(self, device_name_or_ip: str) -> str | None:
        """Get IP address for a device name or directly use IP if provided.

        Args:
            device_name_or_ip: Either a Chromecast device name or a direct IP address.

        Returns:
            The IP address of the device, or None if not found.
        """
        # Check if the provided value is already a valid IP address
        if is_valid_ipv4(device_name_or_ip):
            _LOGGER.info("Using direct IP address: %s", device_name_or_ip)
            return device_name_or_ip

        # If not an IP, treat as a device name and look it up
        return await self._async_get_ip_by_name(device_name_or_ip)

    async def async_get_device_ip_from_config(self, device_config: dict) -> str | None:
        """Resolve a device IP from a config dict that may have name and/or IP.

        Tries direct IP first (fastest), then falls back to name-based scan.
        If both are provided and the direct IP fails, tries the name lookup.

        Args:
            device_config: Dict with optional keys 'device_name', 'device_ip', 'device_alias'.
                           At least one of 'device_name' or 'device_ip' should be present.

        Returns:
            The IP address of the device, or None if not found.
        """
        device_ip = (device_config.get("device_ip") or "").strip()
        device_name = (device_config.get("device_name") or "").strip()

        # Try direct IP first if provided
        if device_ip:
            if is_valid_ipv4(device_ip):
                _LOGGER.debug("Using configured IP address: %s", device_ip)
                return device_ip
            else:
                _LOGGER.warning("Configured device_ip '%s' is not a valid IPv4 address, ignoring it", device_ip)

        # Fall back to name-based lookup
        if device_name:
            _LOGGER.debug("No valid IP configured, looking up by name: %s", device_name)
            ip = await self._async_get_ip_by_name(device_name)
            if ip:
                return ip
            # If name lookup failed but we also had an (invalid-format) ip, warn clearly
            if device_ip:
                _LOGGER.warning(
                    "Both IP ('%s') and name ('%s') lookups failed for device",
                    device_ip,
                    device_name,
                )

        if not device_ip and not device_name:
            _LOGGER.error("Device config has neither 'device_ip' nor 'device_name' — cannot resolve IP")

        return None

    async def _async_get_ip_by_name(self, device_name: str) -> str | None:
        """Scan for a Chromecast device by name and return its IP address.

        Args:
            device_name: The Chromecast display name to search for.

        Returns:
            The IP address if found, or None.
        """
        try:
            _LOGGER.info("Scanning for device by name: %s", device_name)
            # Check if we've already cached the device to speed up lookups
            if device_name in self.device_ip_cache and self.device_ip_cache[device_name]['timestamp'] > (time.time() - 300):
                _LOGGER.debug("Using cached IP for %s: %s", device_name, self.device_ip_cache[device_name]['ip'])
                return self.device_ip_cache[device_name]['ip']

            # Do a fresh scan
            process = await asyncio.create_subprocess_exec(
                'catt', 'scan',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout = stderr = None
            try:
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SCAN)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Scan for device %s timed out after %ss", device_name, TIMEOUT_SCAN)
                    return None
            finally:
                # Always terminate the subprocess — including when this coroutine is cancelled
                # by an outer asyncio.wait_for. Without this guard, orphaned `catt scan`
                # processes accumulate and cause a memory leak.
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_SCAN_TERMINATE)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        process.kill()
                        try:
                            await asyncio.shield(process.wait())
                        except Exception:
                            pass

            if stdout is None:
                return None

            scan_output = stdout.decode()
            _LOGGER.debug("Full scan output: %s", scan_output)

            if process.returncode != 0:
                _LOGGER.warning("Catt scan failed: %s", stderr.decode().strip())
                return None

            # Parse scan results and find exact matching device
            found_devices = []
            for line in scan_output.splitlines():
                # Skip the header line or empty lines
                if "Scanning Chromecasts..." in line or not line.strip():
                    continue

                # Parse format: IP - Name (name may itself contain " - ", so split on first only)
                parts = line.split(' - ', 1)
                if len(parts) < 2:
                    continue

                ip = parts[0].strip()
                found_name = parts[1].strip()

                # Collect all found devices for logging
                found_devices.append((found_name, ip))

                # Update the cache for all found devices to speed up future lookups
                self.device_ip_cache[found_name] = {
                    'ip': ip,
                    'timestamp': time.time()
                }

                # Exact match check (case-insensitive)
                if found_name.lower() == device_name.lower():
                    _LOGGER.info("Matched device '%s' with IP %s", device_name, ip)
                    return ip

            # If we get here, no exact match was found
            found_names = [name for name, _ in found_devices]
            _LOGGER.warning("Device '%s' not found in scan results. Found devices: %s", device_name, found_names)
            _LOGGER.warning("Make sure the name matches exactly what appears in the scan output, or provide a direct IP address.")
            return None
        except Exception as e:
            _LOGGER.warning("Error scanning for devices: %s", e)
            return None

    async def async_is_media_playing(self, ip):
        """Check whether third-party media is playing or paused on the device.

        Waits for any concurrent media check to finish before running a new one.

        Args:
            ip: The device IP address.

        Returns:
            True if media content (not our dashboard) is active, False otherwise.
        """
        # Check if there's already a status check in progress for this device
        check_id = f"{ip}_media_check"
        if check_id in self.active_checks:
            _LOGGER.debug("Media check already in progress for %s, waiting...", ip)
            try:
                # Wait for a max of 10 seconds for the check to complete
                for _ in range(10):
                    if check_id not in self.active_checks:
                        break
                    await asyncio.sleep(1)
                
                if check_id in self.active_checks:
                    _LOGGER.warning("Previous media check for %s did not complete in time, proceeding with new check", ip)
                    # Clean up the stale check
                    self.active_checks.pop(check_id, None)
            except Exception as e:
                _LOGGER.error("Error waiting for previous media check: %s", e)
                self.active_checks.pop(check_id, None)
        
        # Mark this check as active
        self.active_checks[check_id] = time.time()
        
        try:
            _LOGGER.debug("Checking if media is playing on device at %s", ip)
            stdout_str, stderr_str, returncode, _ = await self._async_run_status_command(ip, timeout=TIMEOUT_STATUS_CHECK)

            if stdout_str is None or returncode is None:
                return False

            if returncode != 0:
                _LOGGER.warning("Status check failed with return code %s: %s", returncode, stderr_str)
                return False

            # Check for "idle" state that only shows volume info
            if len(stdout_str.splitlines()) <= 2 and all(line.startswith("Volume") for line in stdout_str.splitlines()):
                _LOGGER.debug("Device at %s is idle (only volume info returned)", ip)
                return False

            # Check for a status line that contains "Casting: Starting" which indicates media is about to play
            if "Casting: Starting" in stdout_str:
                _LOGGER.info("Device at %s is starting to cast media", ip)
                return True

            # Check for Google Assistant/timer activity
            if self._status_indicates_assistant_activity(stdout_str):
                _LOGGER.info("Device at %s has Google Assistant activity", ip)
                return True

            # If we get "Idle" or "Nothing is currently playing", no media is playing
            if "Idle" in stdout_str or "Nothing is currently playing" in stdout_str:
                _LOGGER.debug("Device at %s is idle or not playing anything", ip)
                return False

            # Check if we have a "State: PLAYING" or "State: PAUSED" or "State: BUFFERING" line
            for line in stdout_str.splitlines():
                if "State:" in line and ("PLAYING" in line or "PAUSED" in line or "BUFFERING" in line):
                    _LOGGER.info("Found %s - media is active on device at %s", line, ip)
                    return True

            # Check for a "Title:" line that is not "Dummy" (dashboard)
            for line in stdout_str.splitlines():
                if "Title:" in line and "Dummy" not in line:
                    _LOGGER.info("Found '%s' - media content is active on device at %s", line, ip)
                    return True

            # Check if any known media app name is in the output
            status_lower = stdout_str.lower()
            media_apps = ["spotify", "youtube", "netflix", "plex", "disney+", "hulu", "amazon prime", "music", "audio", "video", "cast"]
            for app in media_apps:
                if app in status_lower:
                    _LOGGER.info("Found '%s' in status - media app is active on device at %s", app, ip)
                    return True

            # At this point, check if anything is playing at all (that's not our dashboard)
            if "Dummy" not in stdout_str and ("playing" in status_lower or "paused" in status_lower or "buffering" in status_lower):
                _LOGGER.info("Found playing/paused/buffering state but not our dashboard - media is active on device at %s", ip)
                return True

            _LOGGER.debug("No media playing on device at %s", ip)
            return False
        except Exception as e:
            _LOGGER.warning("Error checking media status on device at %s: %s", ip, e)
            return False
        finally:
            # Clear the active check marker
            self.active_checks.pop(check_id, None)

    async def async_is_assistant_active(self, ip, status_output=None):
        """Check if Google Assistant (timer, alarm, or reminder) is active on the device.

        Args:
            ip: The device IP address.
            status_output: Previously fetched catt status text. If None, a fresh
                status call is made (or the short-lived cache is consulted first).

        Returns:
            True if Assistant activity is detected, False otherwise.
        """
        # Prefer provided status output
        if status_output is None:
            status_output = self._get_cached_status_output(ip)

        if status_output is None:
            stdout_str, stderr_str, returncode, _ = await self._async_run_status_command(ip, timeout=TIMEOUT_STATUS_CHECK)
            if stdout_str is None or returncode is None:
                return False
            if returncode != 0:
                _LOGGER.debug("Assistant status check failed with return code %s: %s", returncode, stderr_str)
                return False
            status_output = stdout_str

        return self._status_indicates_assistant_activity(status_output)

    async def async_check_device_status(self, ip):
        """Check whether the device is actively casting our dashboard.

        Waits for any concurrent dashboard check to finish before running a new one.

        Args:
            ip: The device IP address.

        Returns:
            True if our dashboard (Dummy title or dashboard URL indicator) is
            detected, False otherwise.
        """
        # Check if there's already a status check in progress for this device
        check_id = f"{ip}_dashboard_check"
        if check_id in self.active_checks:
            _LOGGER.debug("Dashboard status check already in progress for %s, waiting...", ip)
            try:
                # Wait for a max of 10 seconds for the check to complete
                for _ in range(10):
                    if check_id not in self.active_checks:
                        break
                    await asyncio.sleep(1)
                
                if check_id in self.active_checks:
                    _LOGGER.warning("Previous dashboard check for %s did not complete in time, proceeding with new check", ip)
                    # Clean up the stale check
                    self.active_checks.pop(check_id, None)
            except Exception as e:
                _LOGGER.error("Error waiting for previous dashboard check: %s", e)
                self.active_checks.pop(check_id, None)
        
        # Mark this check as active
        self.active_checks[check_id] = time.time()
        
        try:
            _LOGGER.debug("Checking status for device at %s", ip)
            stdout_str, stderr_str, returncode, _ = await self._async_run_status_command(ip, timeout=TIMEOUT_STATUS_CHECK)

            if stdout_str is None or returncode is None:
                return False

            _LOGGER.debug("Status command return code: %s", returncode)

            # Parse output to check if it's actually casting our dashboard
            if returncode == 0:
                output = stdout_str
                
                # Check for "idle" state that only shows volume info
                if len(stdout_str.splitlines()) <= 2 and all(line.startswith("Volume") for line in stdout_str.splitlines()):
                    _LOGGER.debug("Device at %s is idle (only volume info returned)", ip)
                    return False

                # If device explicitly says idle or nothing playing, return False
                if "Idle" in output or "Nothing is currently playing" in output:
                    _LOGGER.debug("Device at %s is idle or not casting", ip)
                    return False

                # Look for "Dummy" in the title, which indicates our dashboard is casting
                if "Dummy" in output:
                    dummy_line = next((line for line in output.splitlines() if "Dummy" in line), "")
                    _LOGGER.debug("Dashboard found: %s", dummy_line)
                    return True

                # Check for dashboard-specific indicators in the output
                dashboard_indicators = ["8123", "dashboard", "kiosk", "homeassistant"]
                if any(indicator in output.lower() for indicator in dashboard_indicators):
                    _LOGGER.debug("Dashboard indicators found in status")
                    return True

                # If we get here, device is playing something but not our dashboard
                _LOGGER.debug("Device at %s is playing something, but not our dashboard", ip)
                return False
            else:
                _LOGGER.warning("Status check failed with return code %s: %s", returncode, stderr_str)
                return False
        except Exception as e:
            _LOGGER.warning("Error checking device status at %s: %s", ip, e)
            return False
        finally:
            # Clear the active check marker
            self.active_checks.pop(check_id, None)
    
    async def async_check_speaker_group_state(self, ip, speaker_groups):
        """Check whether any speaker group in the list is actively playing.

        Args:
            ip: The primary device IP address (used for logging context).
            speaker_groups: A list of speaker group identifiers to check.

        Returns:
            True if at least one speaker group reports PLAYING state, False otherwise.
        """
        if not speaker_groups or not isinstance(speaker_groups, list):
            return False
            
        for speaker_group in speaker_groups:
            _LOGGER.debug("Checking Speaker Group: %s", speaker_group)
            try:
                cmd = ['catt', '-d', speaker_group, 'status']
                _LOGGER.debug("Executing command: %s", ' '.join(cmd))
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SPEAKER_GROUP)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Speaker group check timed out for %s", speaker_group)
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
                    except asyncio.TimeoutError:
                        process.kill()
                    continue
                
                # Log full output
                stdout_str = stdout.decode().strip()
                stderr_str = stderr.decode().strip()
                _LOGGER.debug("Status command stdout for Speaker Group %s: %s", speaker_group, stdout_str)
                _LOGGER.debug("Status command stderr for Speaker Group %s: %s", speaker_group, stderr_str)

                if "PLAYING" in stdout_str:
                    _LOGGER.info("Speaker Group playback is active on %s", speaker_group)
                    return True
                else:
                    _LOGGER.debug("Speaker Group playback is NOT active on %s", speaker_group)
            except Exception as e:
                _LOGGER.error("Error checking speaker group %s: %s", speaker_group, e)
                
        return False
            
    def get_active_device(self, device_key):
        """Return the tracked state dict for a device, or None if not found.

        Args:
            device_key: The device identifier string.
        """
        return self.active_devices.get(device_key)
        
    def update_active_device(self, device_key, status, **kwargs):
        """Update an existing device entry or create a new one.

        Args:
            device_key: The device identifier string.
            status: The new status string (e.g. 'connected', 'disconnected').
            **kwargs: Additional fields to store in the device entry.
        """
        if device_key in self.active_devices:
            self.active_devices[device_key].update(status=status, **kwargs)
        else:
            # First time seeing this device
            device_data = {'status': status}
            device_data.update(kwargs)
            self.active_devices[device_key] = device_data
            
    def get_all_active_devices(self):
        """Return the full dict of all tracked active devices."""
        return self.active_devices
        
    def get_device_current_dashboard(self, device_key):
        """Return the current dashboard URL for a device, or None if unavailable.

        Args:
            device_key: The device identifier string.
        """
        if device_key in self.active_devices:
            return self.active_devices[device_key].get('current_dashboard')
        return None

    def remove_device(self, device_key: str) -> None:
        """Remove a device from all tracking structures.

        Call this when a device is removed from configuration to prevent memory leaks.

        Args:
            device_key: The device identifier to remove.
        """
        self.active_devices.pop(device_key, None)
        # Also clean up any active checks for this device
        keys_to_remove = [k for k in self.active_checks if k.startswith(f"{device_key}_")]
        for key in keys_to_remove:
            self.active_checks.pop(key, None)
        _LOGGER.debug("Removed device %s from tracking", device_key)

    def cleanup_stale_caches(self, max_age_seconds: float = 600.0) -> None:
        """Clean up stale entries from caches to prevent memory leaks.

        Args:
            max_age_seconds: Maximum age in seconds for cache entries (default 10 min).
        """
        current_time = time.time()

        # Clean up device IP cache
        stale_ips = [
            name for name, data in self.device_ip_cache.items()
            if current_time - data.get('timestamp', 0) > max_age_seconds
        ]
        for name in stale_ips:
            del self.device_ip_cache[name]

        # Clean up status cache (should already be short-lived, but ensure cleanup)
        stale_status = [
            ip for ip, data in self.status_cache.items()
            if current_time - data.get('timestamp', 0) > 60.0  # 1 minute max
        ]
        for ip in stale_status:
            del self.status_cache[ip]

        # Clean up stale active checks (shouldn't happen, but safety)
        stale_checks = [
            check_id for check_id, timestamp in self.active_checks.items()
            if current_time - timestamp > 120.0  # 2 minutes max
        ]
        for check_id in stale_checks:
            del self.active_checks[check_id]

        if stale_ips or stale_status or stale_checks:
            _LOGGER.debug(
                "Cleaned up caches: %s IPs, %s status, %s checks",
                len(stale_ips),
                len(stale_status),
                len(stale_checks),
            )

    def clear_all_caches(self) -> None:
        """Clear all caches. Call on integration unload."""
        self.device_ip_cache.clear()
        self.status_cache.clear()
        self.active_checks.clear()
        self.active_devices.clear()
        _LOGGER.debug("Cleared all device manager caches")
