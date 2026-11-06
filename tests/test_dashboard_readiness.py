"""Opt-in Lovelace readiness tracker regression tests."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[1] /
    "custom_components" / "continuously_casting_dashboards" / "readiness.py"
)
spec = importlib.util.spec_from_file_location("ccd_readiness", SOURCE)
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class FrontendReadinessTests(unittest.TestCase):
    def test_opt_out_has_no_session_or_alert(self):
        tracker = readiness.ReadinessTracker()
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/home", enabled=False, now=100
        )
        self.assertEqual(tracker.snapshot("Kitchen", now=1000),
                         {"status": "disabled"})

    def test_pending_becomes_unconfirmed_without_forced_recast(self):
        tracker = readiness.ReadinessTracker(grace_seconds=120)
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/home", enabled=True, now=100
        )
        self.assertEqual(tracker.snapshot("Kitchen", now=200)["status"], "pending")
        self.assertEqual(tracker.snapshot("Kitchen", now=221)["status"], "unconfirmed")

    def test_matching_path_reports_ready_and_ignores_host_or_query(self):
        tracker = readiness.ReadinessTracker()
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/home?kiosk",
            enabled=True, now=100,
        )
        self.assertTrue(tracker.report(
            "Kitchen", "/dashboard/home", True, now=110
        ))
        self.assertEqual(tracker.snapshot("Kitchen", now=110)["status"], "ready")

    def test_wrong_dashboard_does_not_replace_readiness(self):
        tracker = readiness.ReadinessTracker()
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/home", True, now=100,
        )
        self.assertFalse(tracker.report(
            "Kitchen", "/dashboard/other", True, now=101
        ))
        self.assertEqual(tracker.snapshot("Kitchen", now=101)["status"], "pending")

    def test_missing_elements_then_fresh_ready_then_stale(self):
        tracker = readiness.ReadinessTracker(stale_seconds=180)
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/home", True, now=100,
        )
        self.assertTrue(tracker.report(
            "Kitchen", "/dashboard/home", False,
            ["salah-timetable-card"], now=105,
        ))
        state = tracker.snapshot("Kitchen", now=106)
        self.assertEqual(state["status"], "missing_elements")
        self.assertEqual(state["missing_elements"], ["salah-timetable-card"])
        tracker.report("Kitchen", "/dashboard/home", True, [], now=120)
        self.assertEqual(tracker.snapshot("Kitchen", now=121)["status"], "ready")
        self.assertEqual(tracker.snapshot("Kitchen", now=300)["status"], "ready")
        self.assertEqual(tracker.snapshot("Kitchen", now=301)["status"], "stale")

    def test_recasting_resets_previous_session(self):
        tracker = readiness.ReadinessTracker()
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/a", True, now=100,
        )
        tracker.report("Kitchen", "/dashboard/a", True, now=110)
        tracker.cast_started(
            "Kitchen", "https://ha.example/dashboard/b", True, now=120,
        )
        self.assertEqual(tracker.snapshot("Kitchen", now=130)["status"], "pending")
        self.assertFalse(tracker.report(
            "Kitchen", "/dashboard/a", True, now=130
        ))
        tracker.clear()
        self.assertEqual(tracker.snapshot("Kitchen", now=300)["status"], "disabled")


class ReadinessWiringTests(unittest.TestCase):
    def test_service_and_resource_are_explicitly_opt_in(self):
        root = SOURCE.parent
        integration = (root / "__init__.py").read_text()
        monitor = (root / "monitoring.py").read_text()
        self.assertIn("report_dashboard_ready", integration)
        self.assertIn("async_register_static_paths", integration)
        self.assertIn('config.get("verify_readiness", False)', integration)
        self.assertIn('device_config.get("verify_readiness", False)', monitor)
        self.assertNotIn("async_reconnect_device(", (root / "readiness.py").read_text())


if __name__ == "__main__":
    unittest.main()
