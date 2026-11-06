"""Check the pinned CATT CLI contract without connecting to a Chromecast.

CI installs the actual pinned release alongside Home Assistant's Google Cast
PyChromecast version. These tests intentionally never attempt network discovery.
"""

from contextlib import redirect_stdout
from importlib import import_module, metadata
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import json

from click.testing import CliRunner


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "continuously_casting_dashboards" / "manifest.json"


class CattCompatibilityTests(TestCase):
    def test_installed_version_matches_manifest(self):
        pinned = json.loads(MANIFEST.read_text())["requirements"]
        self.assertEqual(pinned, ["catt==0.13.3"])
        self.assertEqual(metadata.version("catt"), "0.13.3")

    def test_dashboard_control_subcommands_still_exist(self):
        cli = import_module("catt.cli").cli
        commands = {"scan", "status", "cast_site", "volume", "stop"}
        self.assertTrue(commands.issubset(cli.commands.keys()))
        runner = CliRunner()
        for command in sorted(commands):
            with self.subTest(command=command):
                args = ["-d", "192.0.2.1", command, "--help"]
                result = runner.invoke(cli, args, obj={"options": {}, "aliases": {}})
                self.assertEqual(result.exit_code, 0, msg=result.output)

    def test_scan_output_preserves_device_name_suffix_format(self):
        catt_cli = import_module("catt.cli")
        runner = CliRunner()
        sample = SimpleNamespace(
            host="192.0.2.10",
            friendly_name="Kitchen",
            manufacturer="Google Inc.",
            model_name="Google Nest Hub",
        )
        with patch.object(catt_cli, "get_cast_infos", return_value=[sample]):
            result = runner.invoke(catt_cli.cli, ["scan"], obj={"options": {}, "aliases": {}})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(
            "192.0.2.10 - Kitchen - Google Inc. Google Nest Hub",
            result.output,
        )

    def test_status_output_preserves_volume_state_and_title_labels(self):
        status_output = StringIO()
        from catt.util import echo_status

        with redirect_stdout(status_output):
            echo_status({
                "title": "Dashboard",
                "volume_level": "55",
                "volume_muted": False,
                "player_state": "PLAYING",
            })

        text = status_output.getvalue()
        for expected in (
            "Title: Dashboard",
            "State: PLAYING",
            "Volume: 55",
            "Volume muted: False",
        ):
            self.assertIn(expected, text)
