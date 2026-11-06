"""Regression tests for priority ordering, dashboard rotation and overrides."""

import asyncio
import types
import unittest

from test_cast_reliability import isolated_method


class PriorityAndRotationTests(unittest.TestCase):
    def selector(self):
        clock = {"now": 100.0}
        harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_async_select_device_config",
            {"time": types.SimpleNamespace(
                monotonic=lambda: clock["now"]
            )},
        )
        obj = harness()
        obj._rotation_state = {}
        obj._manual_overrides = {}
        obj.is_paused = lambda _name: False

        async def is_within(_name, config):
            return config.get("within", True)

        async def is_enabled(_name, config):
            return config.get("enabled", True)

        obj.time_window_checker = types.SimpleNamespace(
            async_is_within_time_window=is_within
        )
        obj.switch_checker = types.SimpleNamespace(
            async_check_switch_entity=is_enabled
        )
        return obj, clock

    def select(self, manager, dashboards):
        return asyncio.run(manager._async_select_device_config(
            "Kitchen", dashboards
        ))[0]

    def test_higher_priority_wins_regardless_of_config_order(self):
        mgr, _ = self.selector()
        low = {"dashboard_url": "/low", "priority": 1}
        high = {"dashboard_url": "/high", "priority": 40}
        self.assertIs(self.select(mgr, [low, high]), high)

    def test_disabled_high_priority_does_not_mask_fallback(self):
        mgr, _ = self.selector()
        high = {"dashboard_url": "/high", "priority": 80, "enabled": False}
        low = {"dashboard_url": "/low", "priority": 1}
        self.assertIs(self.select(mgr, [high, low]), low)

    def test_no_rotation_without_explicit_interval(self):
        mgr, _ = self.selector()
        dashboards = [{"dashboard_url": "/a"}, {"dashboard_url": "/b"}]
        self.assertIs(self.select(mgr, dashboards), dashboards[0])

    def test_rotation_stays_stable_until_interval(self):
        mgr, clock = self.selector()
        dashboards = [
            {"dashboard_url": "/a", "priority": 5, "rotation_seconds": 60},
            {"dashboard_url": "/b", "priority": 5, "rotation_seconds": 60},
        ]
        self.assertIs(self.select(mgr, dashboards), dashboards[0])
        clock["now"] = 159.9
        self.assertIs(self.select(mgr, dashboards), dashboards[0])
        clock["now"] = 160.1
        self.assertIs(self.select(mgr, dashboards), dashboards[1])
        clock["now"] = 221
        self.assertIs(self.select(mgr, dashboards), dashboards[0])

    def test_manual_override_works_only_while_eligible(self):
        mgr, clock = self.selector()
        low = {"dashboard_url": "/low", "priority": 0}
        high = {"dashboard_url": "/high", "priority": 50}
        mgr._manual_overrides["Kitchen"] = (0, 130)
        self.assertIs(self.select(mgr, [low, high]), low)
        low["enabled"] = False
        self.assertIs(self.select(mgr, [low, high]), high)
        low["enabled"] = True
        clock["now"] = 130
        self.assertIs(self.select(mgr, [low, high]), high)

    def test_zero_eligible_resets_rotation(self):
        mgr, _ = self.selector()
        candidate = {"dashboard_url": "/a", "enabled": False}
        mgr._rotation_state["Kitchen"] = {"position": 1}
        self.assertIsNone(self.select(mgr, [candidate]))
        self.assertNotIn("Kitchen", mgr._rotation_state)


class ManualControlTests(unittest.TestCase):
    def test_set_manual_dashboard_validates_index_and_duration(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager",
            "async_set_manual_dashboard",
            {"time": types.SimpleNamespace(monotonic=lambda: 100.0)},
        )
        obj = harness()
        obj.devices = {"Kitchen": [{"dashboard_url": "/one"}]}
        obj._manual_overrides = {}
        obj._schedule_selection_refresh = lambda: None
        asyncio.run(obj.async_set_manual_dashboard("Kitchen", 0, 30))
        self.assertEqual(obj._manual_overrides["Kitchen"], (0, 130))
        with self.assertRaises(ValueError):
            asyncio.run(obj.async_set_manual_dashboard("Kitchen", 1, 30))
        with self.assertRaises(ValueError):
            asyncio.run(obj.async_set_manual_dashboard("Kitchen", 0, 0))

    def test_clear_override_schedules_refresh(self):
        harness = isolated_method(
            "monitoring.py", "MonitoringManager",
            "async_clear_manual_dashboard"
        )
        obj = harness()
        obj._manual_overrides = {"Kitchen": (1, 500)}
        events = []
        obj._schedule_selection_refresh = lambda: events.append(True)
        asyncio.run(obj.async_clear_manual_dashboard("Kitchen"))
        self.assertEqual(obj._manual_overrides, {})
        self.assertEqual(events, [True])


if __name__ == "__main__":
    unittest.main()
