"""Regression tests for the operational Cast control milestone.

The tests isolate real integration methods by AST so they run without the
complete Home Assistant runtime or physical Cast devices.
"""

import ast
import asyncio
from collections import Counter
from datetime import time as dt_time
import logging
from pathlib import Path
import time
import types
from typing import Any
import unittest

from test_cast_reliability import isolated_method

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "continuously_casting_dashboards"
LOGGER = logging.getLogger("tests.cast_operations")


def run(coroutine):
    return asyncio.run(coroutine)


class PauseControlTests(unittest.TestCase):
    def manager(self):
        method = isolated_method(
            "monitoring.py", "MonitoringManager", "async_pause_device",
            {"time": time},
        )
        obj = method()
        obj.devices = {"Kitchen Hub": [{"dashboard_url": "/kiosk"}]}
        obj._paused_devices = {}
        obj._schedule_selection_refresh = lambda: None
        return obj

    def test_pause_indefinitely_and_validate_input(self):
        obj = self.manager()
        run(obj.async_pause_device("Kitchen Hub", 0))
        self.assertIn("Kitchen Hub", obj._paused_devices)
        self.assertIsNone(obj._paused_devices["Kitchen Hub"])
        with self.assertRaises(ValueError):
            run(obj.async_pause_device("Missing", 0))
        with self.assertRaises(ValueError):
            run(obj.async_pause_device("Kitchen Hub", 90000))

    def test_timed_pause_expires(self):
        pause_harness = isolated_method(
            "monitoring.py", "MonitoringManager", "async_pause_device",
            {"time": types.SimpleNamespace(monotonic=lambda: 100.0)},
        )
        status_harness = isolated_method(
            "monitoring.py", "MonitoringManager", "is_paused",
            {"time": types.SimpleNamespace(monotonic=lambda: 111.0)},
        )
        obj = pause_harness()
        obj.devices = {"Kitchen Hub": [{}]}
        obj._paused_devices = {}
        obj._schedule_selection_refresh = lambda: None
        run(obj.async_pause_device("Kitchen Hub", 10))
        self.assertEqual(obj._paused_devices["Kitchen Hub"], 110)
        # The real is_paused method removes the expired pause and resumes rules.
        self.assertFalse(status_harness.is_paused(obj, "Kitchen Hub"))
        self.assertEqual(obj._paused_devices, {})

    def test_manual_pause_prevents_cast_selection(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_async_select_device_config",
            {"time": time},
        )
        obj = harness()
        obj.is_paused = lambda name: name == "Kitchen Hub"
        obj._rotation_state = {}
        obj._manual_overrides = {}
        async def should_not_check(*args):
            raise AssertionError("Paused device must not evaluate dashboard rules")
        obj.time_window_checker = types.SimpleNamespace(
            async_is_within_time_window=should_not_check
        )
        obj.switch_checker = types.SimpleNamespace(
            async_check_switch_entity=should_not_check
        )
        self.assertEqual(
            run(obj._async_select_device_config("Kitchen Hub", [{}])),
            (None, False),
        )

    def test_resume_clears_pause_and_schedules_refresh(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "async_resume_device",
        )
        obj = harness()
        obj.devices = {"Kitchen Hub": [{}]}
        obj._paused_devices = {"Kitchen Hub": None}
        events = []
        obj._schedule_selection_refresh = lambda: events.append("refresh")
        run(obj.async_resume_device("Kitchen Hub"))
        self.assertNotIn("Kitchen Hub", obj._paused_devices)
        self.assertEqual(events, ["refresh"])


class RepairsValidationTests(unittest.TestCase):
    def detector(self):
        source = (MODULE / "repairs.py").read_text()
        tree = ast.parse(source)
        node = next(
            n for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "ambiguous_device_names"
        )
        scope = {"Counter": Counter}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<repair>", "exec"), scope)
        return scope["ambiguous_device_names"]

    def test_duplicate_name_without_ip_is_actionable(self):
        detector = self.detector()
        self.assertEqual(
            detector({
                "a": {"device_name": "Kitchen Hub", "device_ip": ""},
                "b": {"device_name": "kitchen HUB", "device_ip": ""},
            }),
            ["kitchen hub"],
        )

    def test_explicit_ip_prevents_false_ambiguity(self):
        detector = self.detector()
        self.assertEqual(
            detector({
                "a": {"device_name": "Kitchen Hub", "device_ip": "192.0.2.1"},
                "b": {"device_name": "Kitchen Hub", "device_ip": "192.0.2.2"},
            }), [],
        )
        self.assertEqual(
            detector({
                "a": {"device_name": "Kitchen Hub", "device_ip": "192.0.2.1"},
                "b": {"device_name": "Kitchen Hub", "device_ip": ""},
            }), [],
        )

    def test_repairs_are_entry_scoped_and_explain_actions(self):
        code = (MODULE / "repairs.py").read_text()
        self.assertIn("config_entry_id=entry.entry_id", code)
        self.assertIn("catt_executable_missing", code)
        self.assertIn("ir.async_delete_issue", code)
        self.assertNotIn("device_unreachable", code)


class GlobalSettingsTests(unittest.TestCase):
    def test_notifications_off_persists_and_unknown_options_are_preserved(self):
        harness = isolated_method(
            "config_flow.py", "GlobalSettingsOptionsFlow", "async_step_init",
            {
                "Any": Any,
                "ConfigFlowResult": dict,
                "_normalise_time_selector": lambda value: (
                    value.strftime("%H:%M:%S")
                    if isinstance(value, dt_time) else value
                ),
                "_LOGGER": LOGGER,
            },
        )
        obj = harness()
        obj._config = {"enable_notifications": True}
        obj._entry = types.SimpleNamespace(
            options={
                "devices": {"Kitchen Hub": [{}]},
                "legacy_setting": "keep-me",
                "enable_notifications": True,
            },
            subentries={},
        )
        obj.async_create_entry = lambda **kwargs: kwargs
        saved = run(obj.async_step_init({
            "enable_notifications": False,
            "logging_level": "warning",
            "cast_delay": 30,
            "start_time": dt_time(7, 30),
            "end_time": dt_time(23, 0),
            "include_entity": False,
        }))
        opts = saved["data"]
        self.assertFalse(opts["enable_notifications"])
        self.assertEqual(opts["devices"], {"Kitchen Hub": [{}]})
        self.assertEqual(opts["legacy_setting"], "keep-me")
        self.assertEqual(opts["start_time"], "07:30:00")


if __name__ == "__main__":
    unittest.main()
