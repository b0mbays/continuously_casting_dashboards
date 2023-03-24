import asyncio
import subprocess
import time
import logging
import logging.handlers

_LOGGER = logging.getLogger(__name__)

from datetime import datetime

class HaContinuousCastingDashboard:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config

        self.device_map = self.config['devices']
        self.cast_delay = self.config['cast_delay']
        self.max_retries = 5
        self.retry_delay = 30

        log_level = config.get("logging_level", "info")
        numeric_log_level = getattr(logging, log_level.upper(), None)
        if not isinstance(numeric_log_level, int):
            raise ValueError(f"Invalid log level: {log_level}")
        _LOGGER.setLevel(numeric_log_level)

    def check_status(self, device_name, state):
        try:
            status_output = subprocess.check_output(["catt", "-d", device_name, "status"]).decode()
            if state in status_output:
                return True
            return False
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error checking {state} state for {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None

    def check_dashboard_state(self, device_name):
        return self.check_status(device_name, "Dummy")

    def check_media_state(self, device_name):
        return self.check_status(device_name, "PLAYING")

    def check_both_states(self, device_name):
        try:
            return self.check_dashboard_state(device_name) or self.check_media_state(device_name)
        except TypeError:
            return None

    def cast_dashboard(self, device_name, dashboard_url):
        try:
            _LOGGER.info(f"Casting dashboard to {device_name}")
            subprocess.call(["catt", "-d", device_name, "stop"])
            subprocess.call(["catt", "-d", device_name, "volume", "0"])
            subprocess.call(["catt", "-d", device_name, "cast_site", dashboard_url])
            subprocess.call(["catt", "-d", device_name, "volume", "50"])
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error casting dashboard to {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None

    # Create a loop to continuously check the media and dashboard state and cast the dashboard if necessary
    max_retries = 5
    retry_delay = 30
    retry_count = 0

    async def start(self):
        while True:
            now = datetime.now().time()
            if self.start_time <= now <= datetime.strptime('23:59', '%H:%M').time() or datetime.strptime('00:00', '%H:%M').time() <= now < self.end_time:        
                for device_name, dashboard_url in self.device_map.items():
                    retry_count = 0
                    while retry_count < self.max_retries:
                        if self.check_both_states(device_name) is None:
                            retry_count += 1
                            _LOGGER.warning(f"Retrying in {self.retry_delay} seconds for {retry_count} time(s) due to previous errors")
                            await asyncio.sleep(self.retry_delay)
                            continue
                        elif self.check_both_states(device_name):
                            _LOGGER.info(f"HA Dashboard (or media) is playing on {device_name}...")
                        else:
                            _LOGGER.info(f"HA Dashboard (or media) is NOT playing on {device_name}!")
                            self.cast_dashboard(device_name, dashboard_url)
                        break
                    else:
                        _LOGGER.error(f"Max retries exceeded for {device_name}. Skipping...")
                        continue
                    await asyncio.sleep(self.cast_delay)
            else:
                _LOGGER.info("Local time is outside of allowed range for casting the screen. Checking for any active HA cast sessions...")
                ha_cast_active = False
                for device_name, dashboard_url in self.device_map.items():
                    if self.check_dashboard_state(device_name):
                        _LOGGER.info(f"HA Dashboard is currently being cast on {device_name}. Stopping...")
                        try:
                            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "stop")
                            await process.wait()
                            ha_cast_active = True
                        except subprocess.CalledProcessError as e:
                            _LOGGER.error(f"Error stopping dashboard on {device_name}: {e}")
                            continue
                    else:
                        _LOGGER.info(f"HA Dashboard is NOT currently being cast on {device_name}. Skipping...")
                        continue
                    await asyncio.sleep(self.cast_delay)
                if not ha_cast_active:
                    _LOGGER.info("No active HA cast sessions found. Sleeping for 5 minutes...")
                    await asyncio.sleep(self.cast_delay)