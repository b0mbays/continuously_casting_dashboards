"""Regression tests for the Cast-only, opt-in custom-card recovery URL."""

import importlib.util
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "continuously_casting_dashboards" / "cast_guard.py"
)
spec = importlib.util.spec_from_file_location("ccd_cast_guard", SOURCE)
cast_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cast_guard)


class CastGuardUrlTests(unittest.TestCase):
    def test_default_does_not_change_url(self):
        original = "https://ha.example/lovelace/kiosk?kiosk&cast_test=2#details"
        self.assertEqual(cast_guard.prepare_cast_url(original), original)
        self.assertEqual(cast_guard.prepare_cast_url(original, False), original)

    def test_opt_in_preserves_dashboard_query_and_fragment(self):
        original = "https://ha.example/lovelace/kiosk?kiosk&cast_test=2#details"
        guarded = cast_guard.prepare_cast_url(original, True)
        parsed = urlsplit(guarded)
        self.assertEqual(parsed.path, "/lovelace/kiosk")
        self.assertEqual(parsed.fragment, "details")
        self.assertEqual(
            parse_qs(parsed.query, keep_blank_values=True),
            {"kiosk": [""], "cast_test": ["2"], "ccd_cast_guard": ["1"]},
        )

    def test_repeated_calls_do_not_duplicate_flag(self):
        original = "http://192.0.2.10:8123/dashboard?kiosk"
        guarded = cast_guard.prepare_cast_url(original, True)
        self.assertEqual(cast_guard.prepare_cast_url(guarded, True), guarded)

    def test_explicit_opt_in_replaces_stale_flag(self):
        original = "https://ha.example/lovelace?kiosk&ccd_cast_guard=0"
        parsed = urlsplit(cast_guard.prepare_cast_url(original, True))
        self.assertEqual(parse_qs(parsed.query)["ccd_cast_guard"], ["1"])

    def test_non_http_schemes_are_never_modified(self):
        for url in ["javascript:alert(1)", "data:text/plain,hi", "/dashboard/kiosk"]:
            with self.subTest(url=url):
                self.assertEqual(cast_guard.prepare_cast_url(url, True), url)


    def test_diagnostic_target_is_only_in_explicit_cast_urls(self):
        target = "0123456789abcdef"
        original = "https://ha.example/lovelace/kiosk?session=sensitive"
        regular = cast_guard.prepare_cast_url(original, enabled=False, diagnostic_target=target)
        self.assertEqual(regular, original)
        cast_url = cast_guard.prepare_cast_url(
            original, enabled=True, diagnostic_target=target
        )
        parsed = urlsplit(cast_url)
        self.assertEqual(parse_qs(parsed.query)["ccd_cast_target"], [target])
        self.assertEqual(parse_qs(parsed.query)["session"], ["sensitive"])
        self.assertEqual(
            cast_guard.prepare_cast_url(cast_url, enabled=True, diagnostic_target=target),
            cast_url,
        )
        with self.assertRaises(ValueError):
            cast_guard.prepare_cast_url(original, enabled=True, diagnostic_target="bad")


if __name__ == "__main__":
    unittest.main()
