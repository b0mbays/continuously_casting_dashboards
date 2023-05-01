import asyncio
import subprocess
import logging
import logging.handlers

_LOGGER = logging.getLogger(__name__)

from datetime import datetime

def is_hour_between(start, end, now):
    is_between = False
    start = start.hour + start.minute / 60
    end = end.hour + end.minute / 60
    now = now.hour + now.minute / 60
    _LOGGER.debug(start,"-",now,"-",end)
    is_between |= start <= now <= end
    is_between |= end < start and (start <= now or now <= end)
    return is_between

# Define the ContinuouslyCastingDashboards class
class ContinuouslyCastingDashboards:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.device_map = {}
        self.cast_delay = self.config['cast_delay']
        self.max_retries = 5
        self.retry_delay = 30
        global_start_time = config.get("start_time", "07:00")
        global_end_time = config.get("end_time", "01:00")

        # Parse devices from the configuration
        for device_name, device_info in self.config['devices'].items():

            # Use device-specific start and end times if provided, otherwise use global values
            start_time = datetime.strptime(device_info.get("start_time", global_start_time), '%H:%M').time()
            end_time = datetime.strptime(device_info.get("end_time", global_end_time), '%H:%M').time()
            #uses -1 as a default volume if not configured by user.
            self.device_map[device_name] = {
                "dashboard_url": device_info["dashboard_url"],
                "dashboard_state_name": device_info.get("dashboard_state_name", "Dummy"),
                "media_state_name": device_info.get("media_state_name", "PLAYING"),
                "volume": device_info.get("volume", -1),
                "start_time": start_time,
                "end_time": end_time
            }
            

        # Initialize state_triggers_map to keep track of state triggers
        self.state_triggers_map = {}
        self.casting_triggered_by_state_change = False
        for device_name, state_triggers_config in config.get("state_triggers", {}).items():
            self.state_triggers_map[device_name] = [
                {
                    "entity_id": trigger["entity_id"],
                    "to_state": trigger["to_state"],
                    "dashboard_url": trigger["dashboard_url"],
                    "time_out": int(trigger["time_out"]) if "time_out" in trigger else None,
                    "force_cast": trigger.get("force_cast", False),                }
                for trigger in state_triggers_config
            ]

        # Create a set of monitored entities
        self.monitored_entities = set()
        for state_triggers in self.state_triggers_map.values():
            for trigger in state_triggers:
                self.monitored_entities.add(trigger["entity_id"])

        # Set up logging
        log_level = config.get("logging_level", "info")
        numeric_log_level = getattr(logging, log_level.upper(), None)
        if not isinstance(numeric_log_level, int):
            raise ValueError(f"Invalid log level: {log_level}")
        _LOGGER.setLevel(numeric_log_level)

        _LOGGER.debug(f"state_triggers_map: {self.state_triggers_map}")
        _LOGGER.debug(f"monitored_entities: {self.monitored_entities}")

    # Function to handle state change events
    async def handle_state_change_event(self, event):
        entity_id = event.data['entity_id']

        # Skip state changes for entities not in the monitored_entities set
        if entity_id not in self.monitored_entities:
            return

        new_state = event.data.get('new_state')
        if new_state is None:
            return

        _LOGGER.debug(f"Entity '{entity_id}' state changed to: {new_state.state}")

        # Check if the state change matches a trigger and cast the dashboard if so
        for device_name, state_triggers in self.state_triggers_map.items():
            for trigger in state_triggers:
                if trigger["entity_id"] == entity_id and trigger["to_state"] == new_state.state:
                    force_cast = trigger.get("force_cast", False)
                    media_playing = await self.check_media_state(device_name)

                    # Only cast the dashboard if force_cast is True or media is not playing
                    if force_cast or not media_playing:
                        _LOGGER.debug(f"Matched state for entity '{entity_id}', casting dashboard to {device_name}")
                        self.casting_triggered_by_state_change = True
                        await self.cast_dashboard(device_name, trigger["dashboard_url"])
                        if "time_out" in trigger:
                            self.hass.loop.create_task(self.stop_casting_after_timeout(device_name, trigger["time_out"]))
                        self.casting_triggered_by_state_change = False
                        break
                    else:
                        _LOGGER.debug(f"Media is playing on {device_name}, not casting dashboard due to force_cast being set to False")

    # Function to stop casting after a configured timeout for the triggered casting functionality
    async def stop_casting_after_timeout(self, device_name, timeout):
        if timeout:
            await asyncio.sleep(timeout)
            _LOGGER.info(f"Stopping casting dashboard on {device_name} after {timeout} seconds timeout")
            try:
                process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "stop")
                await process.wait()
            except subprocess.CalledProcessError as e:
                _LOGGER.error(f"Error stopping dashboard on {device_name}: {e}")
                return None
            except ValueError as e:
                _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
                return None
            except asyncio.TimeoutError as e:
                _LOGGER.error(f"Timeout stopping dashboard on {device_name}: {e}")
                return None

    # Function to check the status of the device
    async def check_status(self, device_name, state):
        try:
            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "status", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            status_output = stdout.decode()
            return status_output
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error checking {state} state for {device_name}: {e}\nOutput: {e.output.decode()}")
            return None
        except subprocess.TimeoutExpired as e:
            _LOGGER.error(f"Timeout checking {state} state for {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None
        except asyncio.exceptions.TimeoutError as e:  # Add proper exception handling for TimeoutError
                _LOGGER.error(f"Asyncio TimeoutError checking {state} state for {device_name}: {e}")
                return None

    # Function to check if the dashboard state is active
    async def check_dashboard_state(self, device_name):
        try:
            dashboard_state_name = self.device_map[device_name]["dashboard_state_name"]
            status_output = await self.check_status(device_name, dashboard_state_name)
            if status_output is not None and dashboard_state_name in status_output:
                _LOGGER.debug(f"Status output for {device_name} when checking for dashboard state '{dashboard_state_name}': {status_output}")
                _LOGGER.debug("Dashboard active")
                return True
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error checking state for {device_name}: {e}\nOutput: {e.output.decode()}")
            return None
        except subprocess.TimeoutExpired as e:
            _LOGGER.error(f"Timeout checking state for {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None
        return None

    # Function to check if media is playing on the device
    async def check_media_state(self, device_name):
        try:
            media_state_name = self.device_map[device_name]["media_state_name"]
            status_output = await self.check_status(device_name, media_state_name)
            if status_output is not None and media_state_name in status_output:
                _LOGGER.debug(f"Status output for {device_name} when checking for dashboard state '{media_state_name}': {status_output}")
                _LOGGER.debug("Media is playing!")
                return True
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error checking state for {device_name}: {e}\nOutput: {e.output.decode()}")
            return None
        except subprocess.TimeoutExpired as e:
            _LOGGER.error(f"Timeout checking state for {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None
        return None

    # Function to check if either dashboard or media state is active
    async def check_both_states(self, device_name):
        dashboard_state_name = self.device_map[device_name]["dashboard_state_name"]
        status_output = await self.check_status(device_name, dashboard_state_name)
        
        if status_output is None or not status_output:
            return False
        _LOGGER.debug(f"Status output for {device_name} when checking for dashboard state '{dashboard_state_name}': {status_output}")

        is_dashboard_state = dashboard_state_name in status_output
        is_media_state = "PLAYING" in status_output or "Netflix" in status_output

        return is_dashboard_state or is_media_state

    # Function to cast the dashboard to the device
    async def cast_dashboard(self, device_name, dashboard_url):
        try:
            _LOGGER.info(f"Casting dashboard to {device_name}")

            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "stop")
            _LOGGER.debug("Executing stop command...")
            await asyncio.wait_for(process.wait(), timeout=10)
            
            # check the current volume of the device, if fails, default to 5
            media_state_name = self.device_map[device_name]["media_state_name"]
            status_output = await self.check_status(device_name, media_state_name)
            current_volume = status_output.rsplit(":",1)[1].strip()
            current_volume = current_volume if current_volume.isdigit() else 5
            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "volume", "0")
            _LOGGER.debug("Setting volume to 0...")
            await asyncio.wait_for(process.wait(), timeout=10)

            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "cast_site", dashboard_url)
            _LOGGER.info("Executing the dashboard cast command...")
            await asyncio.wait_for(process.wait(), timeout=10)

            # if the config didn't set a volume use the current device volume
            if self.device_map[device_name].get("volume",5) != -1:
                custom_volume = self.device_map[device_name].get("volume", 5) * 10
            else:
                custom_volume = current_volume
            
            custom_volume_str = str(custom_volume)
            
            process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "volume", custom_volume_str)            
            _LOGGER.info(f"Setting volume to {custom_volume_str}...")          
            await asyncio.wait_for(process.wait(), timeout=10)
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Error casting dashboard to {device_name}: {e}")
            return None
        except ValueError as e:
            _LOGGER.error(f"Invalid file descriptor for {device_name}: {e}")
            return None
        except asyncio.TimeoutError as e:
            _LOGGER.error(f"Timeout casting dashboard to {device_name}: {e}")
            return None


    # Main loop for the casting process
    max_retries = 5
    retry_delay = 30
    retry_count = 0
    async def start(self):
        self.hass.bus.async_listen('state_changed', self.handle_state_change_event)
        while True:
            now = datetime.now().time()
            for device_name, device_info in self.device_map.items():
                # Get device-specific start and end times
                start_time = device_info["start_time"]
                end_time = device_info["end_time"]

                # Check if the current time is within the allowed casting range for the device
                is_time_in_range = is_hour_between(start_time, end_time, now)
                
                if is_time_in_range:
                    _LOGGER.info(f"Current local time: {now}")
                    _LOGGER.info(f"Local time is inside the allowed casting time for {device_name}. Start time: {start_time} - End time: {end_time}")
                    # Skip normal flow if casting is triggered by state change
                    if self.casting_triggered_by_state_change:
                        _LOGGER.debug("Skipping normal flow as casting is triggered by state change")
                        try:
                            await asyncio.sleep(self.cast_delay)
                        except asyncio.CancelledError:
                            _LOGGER.error("Casting delayed, task cancelled.")
                        continue

                    # Retry casting in case of errors
                    retry_count = 0
                    while retry_count < self.max_retries:
                        try:
                            if (await self.check_both_states(device_name)) is None:
                                retry_count += 1
                                _LOGGER.warning(f"Retrying in {self.retry_delay} seconds for {retry_count} time(s) due to previous errors")
                                try:
                                    await asyncio.sleep(self.cast_delay)
                                except asyncio.CancelledError:
                                    _LOGGER.error("Casting delayed, task cancelled.")
                                continue
                            elif await self.check_both_states(device_name):
                                _LOGGER.info(f"HA Dashboard (or media) is playing on {device_name}...")
                            else:
                                _LOGGER.info(f"HA Dashboard (or media) is NOT playing on {device_name}!")
                                
                                await self.cast_dashboard(device_name, device_info["dashboard_url"])
                            break 
                        except TypeError as e:
                            _LOGGER.error(f"Error encountered while checking both states for {device_name}: {e}")
                            break
                    else:
                        _LOGGER.error(f"Max retries exceeded for {device_name}. Skipping...")
                        continue
                    try:
                        await asyncio.sleep(self.cast_delay)
                    except asyncio.CancelledError:
                        _LOGGER.error("Casting delayed, task cancelled.")

                # If the current time is outside the allowed range, check for active HA cast sessions
                else:
                    _LOGGER.info(f"Current local time: {now}")
                    _LOGGER.info(f"Local time is outside the allowed casting time for {device_name}. Start time: {start_time} - End time: {end_time}")
                    _LOGGER.info(f"Checking for any active HA cast sessions on {device_name} to stop if necessary...")

                    if not is_time_in_range:
                        try:
                            if await self.check_dashboard_state(device_name):
                                _LOGGER.info(f"HA Dashboard is currently being cast on {device_name}. Stopping...")
                                try:
                                    process = await asyncio.create_subprocess_exec("catt", "-d", device_name, "stop")
                                    await process.wait()
                                except subprocess.CalledProcessError as e:
                                    _LOGGER.error(f"Error stopping dashboard on {device_name}: {e}")
                                    continue
                            else:
                                _LOGGER.info(f"HA Dashboard is NOT currently being cast on {device_name}. Skipping...")
                                continue
                        except TypeError as e:
                            _LOGGER.error(f"Error encountered while checking dashboard state for {device_name}: {e}")
                            continue

                    try:
                        await asyncio.sleep(5)
                    except asyncio.CancelledError:
                        _LOGGER.error("Casting delayed, task cancelled.")