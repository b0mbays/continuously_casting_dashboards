"""Regression tests for background Cast startup with long inter-device delays.

These execute the integration's real initialize_devices and background startup
methods without a live HA instance or Chromecast.
"""

import asyncio
from datetime import datetime
import logging
from types import SimpleNamespace
import unittest

from test_cast_reliability import isolated_method


LOGGER = logging.getLogger("tests.background_cast_initialization")


class StartupDelayTests(unittest.TestCase):
    def create_manager(self, names, *, eligible=None, playing=None):
        eligible = eligible or {name: True for name in names}
        playing = set(playing or ())
        sleeps = []
        attempted = []

        async def sleep(seconds):
            sleeps.append(seconds)

        async def resolve(name):
            return f"192.0.2.{names.index(name) + 1}"

        async def select(name, configs):
            if not eligible.get(name, True):
                return None, False
            return configs[0], True

        async def check_window(_name, _config):
            return True

        async def check_media(ip):
            return any(ip == f"192.0.2.{names.index(name) + 1}" for name in playing)

        async def start(name, config, ip):
            attempted.append((name, ip, config["dashboard_url"]))

        harness = isolated_method(
            "monitoring.py",
            "MonitoringManager",
            "initialize_devices",
            {
                "asyncio": SimpleNamespace(sleep=sleep),
                "datetime": datetime,
                "_LOGGER": LOGGER,
            },
        )
        manager = harness()
        manager.devices = {
            name: [{"dashboard_url": f"https://ha.example/{name}"}]
            for name in names
        }
        manager._async_resolve_device_ip = resolve
        manager._async_select_device_config = select
        manager.time_window_checker = SimpleNamespace(
            async_is_within_time_window=check_window
        )
        manager._ha_state_indicates_user_media = lambda _name: False
        manager.device_manager = SimpleNamespace(async_is_media_playing=check_media)
        manager.async_start_device = start
        manager.cast_delay = 60
        manager.active_device_configs = {}
        return manager, sleeps, attempted

    def test_one_healthy_device_has_no_trailing_sixty_second_delay(self):
        manager, sleeps, attempted = self.create_manager(["Kitchen"])
        self.assertTrue(asyncio.run(manager.initialize_devices()))
        self.assertEqual(sleeps, [2])
        self.assertEqual([a[0] for a in attempted], ["Kitchen"])
        self.assertIn("Kitchen", manager.active_device_configs)

    def test_two_healthy_devices_are_spaced_only_between_casts(self):
        manager, sleeps, attempted = self.create_manager(["Kitchen", "Office"])
        self.assertTrue(asyncio.run(manager.initialize_devices()))
        self.assertEqual(sleeps, [2, 60])
        self.assertEqual([a[0] for a in attempted], ["Kitchen", "Office"])

    def test_skipped_dashboard_does_not_consume_inter_device_delay(self):
        manager, sleeps, attempted = self.create_manager(
            ["Kitchen", "Office"], eligible={"Kitchen": False}
        )
        self.assertTrue(asyncio.run(manager.initialize_devices()))
        self.assertEqual(sleeps, [2])
        self.assertEqual([a[0] for a in attempted], ["Office"])

    def test_media_playback_does_not_delay_other_initial_caster(self):
        manager, sleeps, attempted = self.create_manager(
            ["Kitchen", "Office"], playing={"Kitchen"}
        )
        manager._extend_media_hold = lambda *_args: None
        manager._mark_media_playing = lambda *_args: None
        self.assertTrue(asyncio.run(manager.initialize_devices()))
        self.assertEqual(sleeps, [2])
        self.assertEqual([a[0] for a in attempted], ["Office"])


class BackgroundStartupTests(unittest.TestCase):
    def test_no_global_deadline_and_starts_monitoring_after_initialization(self):
        order = []

        async def initialize():
            order.append("initializing")
            await asyncio.sleep(0)
            order.append("initialized")

        async def stats():
            order.append("status")

        async def monitor(_arg):
            order.append("monitoring")

        harness = isolated_method(
            "__init__.py",
            "ContinuouslyCastingDashboards",
            "start_background_initialization",
            {"_LOGGER": LOGGER},
        )
        obj = harness()
        obj.background_started = False
        obj._background_tasks = []
        obj.monitoring_manager = SimpleNamespace(
            initialize_devices=initialize,
            async_monitor_devices=monitor,
        )
        obj.stats_manager = SimpleNamespace(async_generate_status_data=stats)
        obj.hass = SimpleNamespace(async_create_task=asyncio.create_task)

        async def check():
            result = await obj.start_background_initialization()
            await asyncio.gather(*obj._background_tasks)
            return result

        self.assertTrue(asyncio.run(check()))
        self.assertEqual(order, ["initializing", "initialized", "status", "monitoring"])
        self.assertTrue(obj.background_started)


    def test_unload_cancels_pending_background_initialization(self):
        cancel_seen = []

        async def cleanup():
            return None

        harness = isolated_method(
            "__init__.py",
            "ContinuouslyCastingDashboards",
            "stop",
            {"_LOGGER": LOGGER, "asyncio": asyncio},
        )
        obj = harness()
        obj._background_tasks = []
        obj.unsubscribe_listeners = []
        obj.monitoring_manager = SimpleNamespace(cleanup=cleanup)
        obj.readiness_tracker = SimpleNamespace(clear=lambda: None)
        obj.frontend_diagnostics = SimpleNamespace(clear=lambda: None)
        obj.device_manager = SimpleNamespace(clear_all_caches=lambda: None)
        obj.casting_manager = SimpleNamespace(cleanup=cleanup)

        async def initialisation():
            try:
                await asyncio.Event().wait()
            finally:
                cancel_seen.append("cancelled")

        async def check():
            task = asyncio.create_task(initialisation())
            obj._background_tasks.append(task)
            await asyncio.sleep(0)
            self.assertTrue(await obj.stop())
            self.assertTrue(task.cancelled())

        asyncio.run(check())
        self.assertEqual(cancel_seen, ["cancelled"])
        self.assertEqual(obj._background_tasks, [])

    def test_setup_and_reload_track_initialization_task(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "continuously_casting_dashboards"
            / "__init__.py"
        ).read_text()
        self.assertIn("caster._background_tasks.append(startup_task)", source)
        self.assertIn("new_instance._background_tasks.append(startup_task)", source)


if __name__ == "__main__":
    unittest.main()
