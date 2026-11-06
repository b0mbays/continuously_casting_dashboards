"""Regression tests for combined upstream PRs #152, #153, #154 and HA issue #161.

Tests isolate small methods using AST so Home Assistant is not required just to run
the branch's fast CI checks. Integration behaviour must also be verified on HA.
"""

import ast
import asyncio
import logging
from pathlib import Path
import sys
import textwrap
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "continuously_casting_dashboards"
LOGGER = logging.getLogger("tests.cast_reliability")


def isolated_method(filename: str, class_name: str, method_name: str, namespace=None):
    """Compile one real method from the repository without importing HA."""
    source = (COMPONENT / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    klass = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node for node in klass.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    )
    snippet = textwrap.dedent(ast.get_source_segment(source, method))
    scope = dict(namespace or {})
    exec("class Harness:\n" + textwrap.indent(snippet, "    "), scope)
    return scope["Harness"]


def cast_ha_modules(entities, registered_devices):
    """Fake HA registries while exercising the real DashCast fallback."""
    root = types.ModuleType("homeassistant")
    root.__path__ = []
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    entities_mod = types.ModuleType("homeassistant.helpers.entity_registry")
    devices_mod = types.ModuleType("homeassistant.helpers.device_registry")
    util = types.ModuleType("homeassistant.util")
    entities_mod.async_get = lambda hass: types.SimpleNamespace(entities=entities)
    devices_mod.async_get = lambda hass: types.SimpleNamespace(
        async_get=lambda device_id: registered_devices.get(device_id)
    )
    util.slugify = lambda name: name.lower().replace(" ", "_")
    helpers.entity_registry = entities_mod
    helpers.device_registry = devices_mod
    return {
        "homeassistant": root,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": entities_mod,
        "homeassistant.helpers.device_registry": devices_mod,
        "homeassistant.util": util,
    }


class DashCastTests(unittest.TestCase):
    def setUp(self):
        self.harness = isolated_method(
            "device.py", "DeviceManager", "_async_check_dashcast_via_ha",
            {"_LOGGER": LOGGER, "DASHCAST_APP_ID": "84912283"},
        )

    def check(self, target_app, other_app, target_entity="media_player.kitchen_hub"):
        entry = lambda entity, device: types.SimpleNamespace(
            domain="media_player", platform="cast", entity_id=entity,
            device_id=device,
        )
        state = lambda app: types.SimpleNamespace(attributes={"app_id": app})
        devices = {
            "target": types.SimpleNamespace(name="Kitchen Hub", name_by_user=None),
            "other": types.SimpleNamespace(name="Bedroom Display", name_by_user=None),
        }
        entities = {
            "one": entry(target_entity, "target"),
            "two": entry("media_player.bedroom_display", "other"),
        }
        states = {
            target_entity: state(target_app),
            "media_player.bedroom_display": state(other_app),
        }
        manager = self.harness()
        manager.config = {
            "device_identifiers": {
                "kitchen": {"device_name": "Kitchen Hub", "device_ip": "192.0.2.10"},
                "bedroom": {"device_name": "Bedroom Display", "device_ip": "192.0.2.11"},
            }
        }
        manager.device_ip_cache = {}
        manager.hass = types.SimpleNamespace(
            states=types.SimpleNamespace(get=states.get)
        )
        with patch.dict(sys.modules, cast_ha_modules(entities, devices)):
            return asyncio.run(
                manager._async_check_dashcast_via_ha("192.0.2.10")
            )

    def test_matching_dashcast_recognized(self):
        self.assertTrue(self.check("84912283", "backdrop"))

    def test_another_devices_dashcast_does_not_mask_idle_target(self):
        self.assertFalse(self.check("backdrop", "84912283"))

    def test_registered_device_name_works_for_renamed_entity(self):
        self.assertTrue(
            self.check("84912283", "backdrop", "media_player.renamed_target")
        )

    def test_non_dashboard_cast_is_not_recognized(self):
        self.assertFalse(self.check("youtube", "backdrop"))


class KeepaliveTests(unittest.TestCase):
    def setUp(self):
        self.harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_send_keepalive_button",
            {"asyncio": asyncio, "_LOGGER": LOGGER},
        )

    def test_keepalive_is_opt_in(self):
        calls = []

        async def call(**kwargs):
            calls.append(kwargs)

        manager = self.harness()
        manager.hass = types.SimpleNamespace(
            services=types.SimpleNamespace(async_call=call)
        )
        asyncio.run(manager._send_keepalive_button(None))
        self.assertEqual(calls, [])
        asyncio.run(manager._send_keepalive_button("remote.google_tv"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["domain"], "remote")
        self.assertEqual(calls[0]["service"], "send_command")
        self.assertEqual(calls[0]["service_data"]["command"], "MENU")
        self.assertEqual(calls[0]["target"]["entity_id"], "remote.google_tv")

    def test_keepalive_failure_is_contained(self):
        async def fails(**kwargs):
            raise RuntimeError("remote not available")

        manager = self.harness()
        manager.hass = types.SimpleNamespace(
            services=types.SimpleNamespace(async_call=fails)
        )
        asyncio.run(manager._send_keepalive_button("remote.offline"))


class TimeoutRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.harness = isolated_method(
            "monitoring.py", "MonitoringManager", "_ha_state_indicates_user_media",
            {"_LOGGER": LOGGER, "USER_MEDIA_STATES": {"playing", "paused", "buffering"}},
        )

    def test_paused_user_media_is_protected(self):
        manager = self.harness()
        manager._get_matching_media_player_state = lambda name: types.SimpleNamespace(
            state="paused", attributes={"app_name": "YouTube", "media_title": "Film"}
        )
        self.assertTrue(manager._ha_state_indicates_user_media("Kitchen Hub"))

    def test_dashcast_does_not_count_as_user_media(self):
        manager = self.harness()
        manager._get_matching_media_player_state = lambda name: types.SimpleNamespace(
            state="playing", attributes={"app_name": "DashCast", "media_title": "Dashboard"}
        )
        self.assertFalse(manager._ha_state_indicates_user_media("Kitchen Hub"))


class CompatibilityTests(unittest.TestCase):
    def test_entity_category_import_works_with_ha_2026_11(self):
        tree = ast.parse((COMPONENT / "sensor.py").read_text(encoding="utf-8"))
        sources = {
            node.module: {alias.name for alias in node.names}
            for node in tree.body if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("EntityCategory", sources["homeassistant.const"])
        self.assertNotIn(
            "EntityCategory", sources["homeassistant.components.sensor"]
        )

    def test_reconnect_after_timeouts_and_media_grace_are_present(self):
        code = (COMPONENT / "monitoring.py").read_text(encoding="utf-8")
        self.assertIn("skip_idle_status_check=True", code)
        self.assertIn("MEDIA_GRACE_PERIOD = 300", code)
        self.assertIn("_is_media_hold_active", code)

    def test_global_setup_has_no_undefined_current_keepalive_selector(self):
        code = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        begin = code.index("    async def async_step_user(")
        end = code.index("    async def async_step_import(", begin)
        self.assertNotIn("current.get(\"remote_device_for_keepalive\")", code[begin:end])
        self.assertIn("remote_device_for_keepalive", code[end:])


if __name__ == "__main__":
    unittest.main()
