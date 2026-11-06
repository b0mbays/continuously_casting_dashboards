"""Cast receiver telemetry tests without a Home Assistant runtime."""

import importlib.util
from pathlib import Path
import unittest


ROOT = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "continuously_casting_dashboards"
)
spec = importlib.util.spec_from_file_location(
    "ccd_frontend_diagnostics", ROOT / "frontend_diagnostics.py"
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class CastReceiverTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tracker = diagnostics.FrontendDiagnosticsTracker()
        self.target = diagnostics.cast_target_token("192.0.2.15")

    def start(self, enabled=True):
        self.tracker.cast_started(
            "Kitchen",
            "192.0.2.15",
            "https://home.example/dashboard/kiosk?auth=never_export",
            enabled=enabled,
            now=100,
        )

    def test_opt_out_leaves_no_diagnostic_session(self):
        self.start(enabled=False)
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=1000), {"status": "disabled"}
        )
        self.assertFalse(self.tracker.can_accept(self.target, "/dashboard/kiosk"))

    def test_missing_reports_distinguishable_from_reported_errors(self):
        self.start()
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=101)["status"], "awaiting_report"
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=191)["status"], "no_report"
        )

    def test_report_requires_matching_receiver_and_path(self):
        self.start()
        self.assertFalse(self.tracker.can_accept(
            diagnostics.cast_target_token("192.0.2.16"), "/dashboard/kiosk"
        ))
        self.assertFalse(self.tracker.report(
            self.target, "/dashboard/other", "observing", {},
            now=150,
        ))
        self.assertFalse(self.tracker.report(
            "0000000000000000", "/dashboard/kiosk", "observing", {},
            now=150,
        ))
        self.assertTrue(self.tracker.can_accept(self.target, "/dashboard/kiosk"))

    def test_observes_resource_failure_and_configuration_error(self):
        self.start()
        self.assertTrue(self.tracker.report(
            self.target, "/dashboard/kiosk", "observing",
            {
                "error_cards": 2,
                "resource_errors": 1,
                "javascript_errors": 0,
                "script_resources": 20,
                "listed_custom_cards": 4,
                "registered_custom_cards": 3,
                "secret": "ignore",
            },
            document_state="complete",
            now=150,
        ))
        state = self.tracker.snapshot("Kitchen", now=151)
        self.assertEqual(state["status"], "error_cards")
        self.assertEqual(state["error_cards"], 2)
        self.assertEqual(state["resource_errors"], 1)
        self.assertEqual(state["registered_custom_cards"], 3)
        self.assertEqual(state["document_state"], "complete")
        self.assertNotIn("secret", str(state))
        self.assertNotIn("auth", str(state))
        self.assertNotIn("home.example", str(state))

    def test_good_report_becomes_stale_without_new_heartbeat(self):
        self.start()
        self.tracker.report(
            self.target, "/dashboard/kiosk", "boot", {}, now=140
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=140)["status"], "observed"
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=321)["status"], "stale"
        )

    def test_reload_then_after_reload_status(self):
        self.start()
        self.tracker.report(
            self.target, "/dashboard/kiosk",
            "reload_requested", {"error_cards": 1}, now=140
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=141)["status"], "reload_requested"
        )
        self.tracker.report(
            self.target, "/dashboard/kiosk",
            "after_reload", {"error_cards": 0}, now=160
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=161)["status"], "observed"
        )

    def test_counters_are_bounded_and_bad_types_ignored(self):
        self.start()
        self.tracker.report(
            self.target, "/dashboard/kiosk",
            "observing",
            {
                "error_cards": 100_000,
                "resource_errors": "-2",
                "javascript_errors": [],
                "script_resources": True,
            },
            now=150,
        )
        state = self.tracker.snapshot("Kitchen", now=151)
        self.assertEqual(state["error_cards"], 999)
        self.assertEqual(state["resource_errors"], 0)
        self.assertEqual(state["javascript_errors"], 0)
        self.assertEqual(state["script_resources"], 0)
        self.assertFalse(self.tracker.report(
            self.target, "/dashboard/kiosk", "unknown", {}, now=170
        ))

    def test_new_cast_resets_old_report_and_mismatched_path(self):
        self.start()
        self.tracker.report(
            self.target, "/dashboard/kiosk", "observing",
            {"error_cards": 2}, now=150,
        )
        self.tracker.cast_started(
            "Kitchen", "192.0.2.15",
            "https://home.example/dashboard/other",
            enabled=True, now=160,
        )
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=161)["status"], "awaiting_report"
        )
        self.assertFalse(self.tracker.can_accept(self.target, "/dashboard/kiosk"))
        self.tracker.clear()
        self.assertEqual(
            self.tracker.snapshot("Kitchen", now=162), {"status": "disabled"}
        )


if __name__ == "__main__":
    unittest.main()
