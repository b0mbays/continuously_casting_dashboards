"""Ensure the integration version and HACS metadata remain consistent."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "continuously_casting_dashboards"


class VersionMetadataTests(unittest.TestCase):
    def test_manifest_and_hacs_versions_match(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        version = manifest["version"]
        self.assertEqual(version, hacs["version"])
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_metadata_links_point_to_same_fork(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        fork = "github.com/anaschillin/continuously_casting_dashboards"
        self.assertIn(fork, manifest["documentation"])
        self.assertIn(fork, manifest["issue_tracker"])
        self.assertIn(fork, hacs["documentation"])


if __name__ == "__main__":
    unittest.main()
