"""Fast regression tests for dashboard rules, scheduling, and volume controls.

These isolate actual repository methods via AST so CI can exercise their
behaviour without installing the full Home Assistant runtime.
"""

import asyncio
import datetime
import logging
import time
import types
import unittest
from unittest.mock import patch
from typing import Any

from test_cast_reliability import isolated_method


LOGGER = logging.getLogger("tests.dashboard_rules")


def run(coro):
    return asyncio.run(coro)


class ScheduleTests(unittest.TestCase):
    def checker(self, hour=12, minute=0):
        clock = types.SimpleNamespace(
            now=lambda: datetime.datetime(2026, 11, 6, hour, minute)
        )
        harness = isolated_method(
            "utils.py", "TimeWindowChecker", "async_is_within_time_window",
            {"dt_util": clock, "dt_time": datetime.time, "_LOGGER": LOGGER},
        )
        obj = harness()
        obj.default_start_time = "08:00"
        obj.default_end_time = "22:00"
        return obj

    def test_continuous_cast_ignores_global_schedule(self):
        self.assertTrue(
            run(self.checker(hour=3).async_is_within_time_window(
                "Kitchen", {"cast_continuously": True}
            ))
        )

    def test_legacy_schedule_unchanged_when_opt_out(self):
        self.assertFalse(
            run(self.checker(hour=3).async_is_within_time_window("Kitchen", {}))
        )
        self.assertTrue(
            run(self.checker(hour=12).async_is_within_time_window("Kitchen", {}))
        )

    def test_custom_midnight_window(self):
        config = {"start_time": "22:00:00", "end_time": "06:00:00"}
        self.assertTrue(
            run(self.checker(hour=23).async_is_within_time_window("Kitchen", config))
        )
        self.assertTrue(
            run(self.checker(hour=2).async_is_within_time_window("Kitchen", config))
        )
        self.assertFalse(
            run(self.checker(hour=12).async_is_within_time_window("Kitchen", config))
        )


class SelectionTests(unittest.TestCase):
    def manager(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_async_select_device_config",
            {"time": time},
        )

        async def check_time(name, config):
            return config.get("within", True)

        async def check_entity(name, config):
            return config.get("enabled", True)

        obj = harness()
        obj._rotation_state = {}
        obj._manual_overrides = {}
        obj.is_paused = lambda _name: False
        obj.time_window_checker = types.SimpleNamespace(
            async_is_within_time_window=check_time
        )
        obj.switch_checker = types.SimpleNamespace(
            async_check_switch_entity=check_entity
        )
        return obj

    def test_disabled_first_dashboard_does_not_mask_second(self):
        manager = self.manager()
        first = {"dashboard_url": "/first", "within": True, "enabled": False}
        second = {"dashboard_url": "/second", "within": True, "enabled": True}
        chosen, eligible = run(manager._async_select_device_config(
            "Kitchen", [first, second]
        ))
        self.assertIs(chosen, second)
        self.assertTrue(eligible)

    def test_out_of_window_dashboard_does_not_mask_next(self):
        first = {"dashboard_url": "/first", "within": False, "enabled": True}
        second = {"dashboard_url": "/second", "within": True, "enabled": True}
        chosen, _ = run(self.manager()._async_select_device_config(
            "Kitchen", [first, second]
        ))
        self.assertIs(chosen, second)

    def test_first_eligible_wins(self):
        first = {"dashboard_url": "/first"}
        second = {"dashboard_url": "/second"}
        chosen, _ = run(self.manager()._async_select_device_config(
            "Kitchen", [first, second]
        ))
        self.assertIs(chosen, first)

    def test_no_eligible_dashboard_means_none(self):
        config = {"dashboard_url": "/disabled", "enabled": False}
        chosen, eligible = run(self.manager()._async_select_device_config(
            "Kitchen", [config]
        ))
        self.assertIsNone(chosen)
        self.assertFalse(eligible)

    def test_selection_changes_flag_only_when_url_changes(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "async_update_device_configs",
            {"datetime": datetime.datetime, "_LOGGER": LOGGER},
        )
        obj = harness()
        obj.devices = {"Kitchen": [{"dashboard_url": "/one"}]}
        obj.active_device_configs = {}
        current = {"dashboard_url": "/one"}

        async def select(name, configs):
            return current, True

        obj._async_select_device_config = select
        self.assertEqual(run(obj.async_update_device_configs()), ["Kitchen"])
        self.assertTrue(obj.active_device_configs["Kitchen"]["instance_change"])
        self.assertEqual(run(obj.async_update_device_configs()), [])
        self.assertFalse(obj.active_device_configs["Kitchen"]["instance_change"])
        current = None
        self.assertEqual(run(obj.async_update_device_configs()), ["Kitchen"])
        self.assertIsNone(obj.active_device_configs["Kitchen"]["config"])

    def test_none_selection_stops_active_dashboard(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_process_single_device",
            {"datetime": datetime.datetime, "_LOGGER": LOGGER},
        )
        stopped = []
        statuses = []

        async def check_status(ip):
            return True

        async def stop(ip):
            stopped.append(ip)

        obj = harness()
        obj.device_manager = types.SimpleNamespace(
            async_check_device_status=check_status,
            update_active_device=lambda **kwargs: statuses.append(kwargs),
        )
        obj.async_stop_casting = stop
        obj.is_paused = lambda _name: False
        obj.readiness_tracker = types.SimpleNamespace(
            cast_started=lambda *args, **kwargs: None
        )
        run(obj._process_single_device("Kitchen", "192.0.2.10", None))
        self.assertEqual(stopped, ["192.0.2.10"])
        self.assertEqual(statuses[0]["status"], "stopped")


class EntityTests(unittest.TestCase):
    def test_missing_device_entity_does_not_inherit_global_on_state(self):
        harness = isolated_method(
            "utils.py", "SwitchEntityChecker", "async_check_switch_entity",
            {"_LOGGER": LOGGER},
        )
        obj = harness()
        states = {"input_boolean.global": types.SimpleNamespace(state="on")}
        obj.hass = types.SimpleNamespace(
            states=types.SimpleNamespace(get=states.get)
        )
        obj.switch_entity_id = "input_boolean.global"
        obj.switch_entity_state = None
        self.assertFalse(run(obj.async_check_switch_entity(
            "Kitchen", {"switch_entity_id": "input_boolean.missing"}
        )))

    def test_custom_state_compared_per_dashboard(self):
        harness = isolated_method(
            "utils.py", "SwitchEntityChecker", "async_check_switch_entity",
            {"_LOGGER": LOGGER},
        )
        obj = harness()
        states = {"person.alex": types.SimpleNamespace(state="home")}
        obj.hass = types.SimpleNamespace(
            states=types.SimpleNamespace(get=states.get)
        )
        obj.switch_entity_id = None
        obj.switch_entity_state = None
        self.assertTrue(run(obj.async_check_switch_entity(
            "Kitchen", {
                "switch_entity_id": "person.alex",
                "switch_entity_state": "home",
            }
        )))
        self.assertFalse(run(obj.async_check_switch_entity(
            "Kitchen", {
                "switch_entity_id": "person.alex",
                "switch_entity_state": "away",
            }
        )))


class PersistenceTests(unittest.TestCase):
    def test_form_navigation_keeps_options_and_time(self):
        normalise = lambda value: (
            value.strftime("%H:%M:%S")
            if isinstance(value, datetime.time) else value
        )
        harness = isolated_method(
            "config_flow.py", "DeviceSubentryFlow", "_save_dashboard_from_input",
            {"Any": Any, "_normalise_time_selector": normalise},
        )
        obj = harness()
        obj._dashboards = [{}]
        obj._current_dashboard_index = 0
        obj._device_name, obj._device_ip, obj._device_alias = "Kitchen", "", ""
        obj._save_dashboard_from_input({
            "dashboard_url": "https://example.org/kiosk",
            "volume": 13,
            "preserve_volume": True,
            "cast_continuously": True,
            "enable_time_window": True,
            "start_time": datetime.time(7, 15),
            "end_time": datetime.time(22, 30),
        }, {})
        config = obj._dashboards[0]
        self.assertTrue(config["preserve_volume"])
        self.assertTrue(config["cast_continuously"])
        self.assertEqual(config["start_time"], "07:15:00")
        self.assertEqual(config["end_time"], "22:30:00")

    def test_reconfigure_serializes_time_values(self):
        normalise = lambda value: (
            value.strftime("%H:%M:%S")
            if isinstance(value, datetime.time) else value
        )
        harness = isolated_method(
            "config_flow.py", "DeviceSubentryFlow", "_save_reconfigure",
            {
                "datetime": datetime,
                "_normalise_time_selector": normalise,
                "get_device_display_title": lambda a, b, c: a or b or c,
                "SubentryFlowResult": object,
            },
        )
        obj = harness()
        obj._dashboards = [{
            "dashboard_url": "https://example.org/kiosk",
            "start_time": datetime.time(6, 45),
            "end_time": "22:30",
            "preserve_volume": True,
        }]
        obj._device_name, obj._device_ip, obj._device_alias = "Kitchen", "", ""
        obj._get_entry = lambda: "entry"
        obj._get_reconfigure_subentry = lambda: "subentry"
        obj.async_update_and_abort = lambda *args, **kwargs: kwargs
        saved = obj._save_reconfigure()
        self.assertEqual(
            saved["data"]["dashboards"][0]["start_time"], "06:45:00"
        )
        self.assertTrue(saved["data"]["dashboards"][0]["preserve_volume"])


class VolumeTests(unittest.TestCase):
    def make_manager(self):
        harness = isolated_method(
            "casting.py", "CastingManager", "async_cast_dashboard",
            {
                "asyncio": asyncio, "time": time, "_LOGGER": LOGGER,
                "DEFAULT_MAX_RETRIES": 1,
                "DEFAULT_RETRY_DELAY": 0,
                "DEFAULT_VERIFICATION_WAIT_TIME": 0,
                "DEFAULT_CASTING_TIMEOUT": 3,
                "TIMEOUT_VOLUME_COMMAND": 3,
                "TIMEOUT_PROCESS_TERMINATE": 3,
            },
        )
        obj = harness()
        obj.config = {
            "max_retries": 1,
            "retry_delay": 0,
            "verification_wait_time": 0,
            "casting_timeout": 3,
        }
        obj.active_casting_operations = {}
        obj.active_subprocesses = {}

        async def false(ip):
            return False

        async def true(ip):
            return True

        obj.device_manager = types.SimpleNamespace(
            async_is_media_playing=false,
            async_check_device_status=true,
        )

        async def cleanup(ip):
            obj.active_casting_operations.pop(ip, None)
            obj.active_subprocesses.clear()

        async def get_volume(ip):
            return 31

        obj.cleanup_casting_operation = cleanup
        obj.async_get_current_volume = get_volume
        return obj

    def commands(self, config):
        manager = self.make_manager()
        commands = []

        class Process:
            returncode = 0

            async def communicate(self):
                return b"Casting dashboard on display", b""

        async def execute(*args, **kwargs):
            commands.append(args)
            return Process()

        with patch.object(asyncio, "create_subprocess_exec", execute):
            success = run(manager.async_cast_dashboard(
                "192.0.2.10", "https://example.org/kiosk", config
            ))
        self.assertTrue(success)
        return commands

    def test_preserve_volume_never_sends_a_volume_command(self):
        commands = self.commands({"preserve_volume": True, "volume": 17})
        self.assertIn("cast_site", [arg for cmd in commands for arg in cmd])
        self.assertFalse(any("volume" in cmd for cmd in commands))

    def test_legacy_volume_setting_remains_unchanged(self):
        commands = self.commands({"volume": 17})
        volume_calls = [cmd for cmd in commands if "volume" in cmd]
        self.assertEqual(len(volume_calls), 2)
        self.assertEqual(volume_calls[0][-1], "0")
        self.assertEqual(volume_calls[1][-1], "17")


if __name__ == "__main__":
    unittest.main()
