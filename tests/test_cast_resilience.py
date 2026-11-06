"""Reliability regression tests independent of a Home Assistant installation."""

import asyncio
import importlib.util
import logging
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

from test_cast_reliability import isolated_method

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "continuously_casting_dashboards" / "reliability.py"
)
spec = importlib.util.spec_from_file_location("ccd_reliability", SOURCE)
reliability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reliability)


class DiscoveryMatchingTests(unittest.TestCase):
    def test_case_insensitive_exact_match_wins_over_google_suffix(self):
        self.assertEqual(
            reliability.match_discovered_device(
                "Kitchen", [
                    ("Kitchen - Google Inc. Google Nest Hub", "192.0.2.4"),
                    ("KITCHEN", "192.0.2.2"),
                ]
            ), "192.0.2.2"
        )

    def test_google_suffix_is_supported(self):
        self.assertEqual(
            reliability.match_discovered_device(
                "Kitchen", [
                    ("Kitchen - Google Inc. Google Nest Hub", "192.0.2.4"),
                    ("Living Room", "192.0.2.7"),
                ]
            ), "192.0.2.4"
        )

    def test_generic_prefix_does_not_match_other_device(self):
        self.assertIsNone(reliability.match_discovered_device(
            "Kitchen", [("Kitchen Display", "192.0.2.4")]
        ))

    def test_ambiguous_google_suffix_fails_closed(self):
        self.assertIsNone(reliability.match_discovered_device(
            "Kitchen", [
                ("Kitchen - Google Inc. Google Nest Hub", "192.0.2.4"),
                ("Kitchen - Google Inc. Google Chromecast", "192.0.2.5"),
            ]
        ))

    def test_empty_name_or_duplicate_exact_ips_not_selected(self):
        self.assertIsNone(reliability.match_discovered_device(
            "", [("Living Room", "192.0.2.4")]
        ))
        self.assertIsNone(reliability.match_discovered_device(
            "Kitchen", [
                ("Kitchen", "192.0.2.4"),
                ("kitchen", "192.0.2.8"),
            ]
        ))


class BackoffTests(unittest.TestCase):
    def test_bounded_exponential_sequence_and_reset(self):
        backoff = reliability.ReconnectBackoff(base_seconds=10, max_seconds=45)
        self.assertEqual([backoff.record_failure("k", now=0) for _ in range(4)],
                         [10, 20, 40, 45])
        self.assertFalse(backoff.can_retry("k", now=0))
        self.assertTrue(backoff.can_retry("k", now=46))
        backoff.record_success("k")
        self.assertEqual(backoff.remaining("k", now=1), 0)
        self.assertEqual(backoff.failures("k"), 0)

    def test_failures_are_device_isolated(self):
        backoff = reliability.ReconnectBackoff()
        backoff.record_failure("a", now=0)
        self.assertFalse(backoff.can_retry("a", now=5))
        self.assertTrue(backoff.can_retry("b", now=5))
        backoff.clear()
        self.assertTrue(backoff.can_retry("a", now=5))


class DiscoveryProcessTests(unittest.TestCase):
    def create_manager(self):
        harness = isolated_method(
            "device.py", "DeviceManager", "_async_get_ip_by_name",
            {
                "asyncio": asyncio,
                "time": time,
                "datetime": __import__("datetime").datetime,
                "TIMEOUT_SCAN": 1.0,
                "TIMEOUT_SCAN_TERMINATE": 1.0,
                "TIMEOUT_PROCESS_TERMINATE": 1.0,
                "_LOGGER": logging.getLogger(__name__),
                "is_valid_ipv4": lambda v: v.count(".") == 3,
                "match_discovered_device": reliability.match_discovered_device,
                "terminate_process": reliability.terminate_process,
            },
        )
        manager = harness()
        manager.device_ip_cache = {}
        manager._scan_lock = asyncio.Lock()
        manager._scan_last_at = 0
        manager._scan_devices = []
        manager.last_scan_at = None
        manager.last_discovery_error = None
        return manager

    def test_concurrent_alias_lookups_share_one_scan(self):
        manager = self.create_manager()
        attempts = []

        class FakeProcess:
            returncode = 0

            async def communicate(self):
                return (
                    b"192.0.2.10 - Kitchen - Google Inc. Google Nest Hub\n"
                    b"192.0.2.11 - Office\n", b""
                )

        async def create_subprocess(*args, **kwargs):
            attempts.append(args)
            return FakeProcess()

        async def scenario():
            return await asyncio.gather(
                manager._async_get_ip_by_name("Kitchen"),
                manager._async_get_ip_by_name("Office"),
            )

        with patch.object(asyncio, "create_subprocess_exec", create_subprocess):
            self.assertEqual(
                asyncio.run(scenario()), ["192.0.2.10", "192.0.2.11"]
            )
        self.assertEqual(len(attempts), 1)


class ProcessCleanupTests(unittest.TestCase):
    def test_terminate_reaps_process(self):
        class FakeProcess:
            returncode = None

            def __init__(self):
                self.terminated = False
                self.waited = False

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            async def wait(self):
                self.waited = True
                return self.returncode

        process = FakeProcess()
        asyncio.run(reliability.terminate_process(process))
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)

    def test_exited_process_not_terminated(self):
        class FakeProcess:
            returncode = 0

            def terminate(self):
                raise AssertionError("Should not terminate an exited process")

        asyncio.run(reliability.terminate_process(FakeProcess()))


if __name__ == "__main__":
    unittest.main()
