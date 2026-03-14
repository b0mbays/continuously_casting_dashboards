"""Config flow for Continuously Cast Dashboards integration.

This module handles all configuration flows:
- Initial setup (global settings)
- Options flow (editing global settings)
- Device subentry flow (adding/editing devices and dashboards)
- YAML import/migration
"""

import logging
import re
import voluptuous as vol
from typing import Any
from urllib.parse import urlparse
import copy
import datetime

from homeassistant.helpers import selector
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_CAST_DELAY,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_START_TIME,
    DEFAULT_END_TIME,
    LOGGING_LEVELS,
)

_LOGGER = logging.getLogger(__name__)

# Validation constants
MAX_DEVICE_NAME_LENGTH = 100
ALLOWED_URL_SCHEMES = ("http", "https")
# Device names: alphanumeric, spaces, hyphens, underscores, periods
DEVICE_NAME_PATTERN = re.compile(r'^[\w\s\-\.]+$', re.UNICODE)


def validate_dashboard_url(url: str) -> tuple[bool, str]:
    """Validate a dashboard URL for security and correctness.

    Args:
        url: The URL string to validate.

    Returns:
        Tuple of (is_valid, error_key). error_key is empty string if valid.
    """
    if not url or not url.strip():
        return False, "missing_dashboard_url"

    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "invalid_url_format"

    # Must have a scheme
    if not parsed.scheme:
        return False, "invalid_url_format"

    # Only allow http/https schemes (block javascript:, file:, data:, etc.)
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return False, "invalid_url_scheme"

    # Must have a netloc (host)
    if not parsed.netloc:
        return False, "invalid_url_format"

    # Block obviously malicious patterns
    dangerous_patterns = [
        "javascript:",
        "vbscript:",
        "data:",
        "<script",
        "onerror=",
        "onclick=",
    ]
    url_lower = url.lower()
    for pattern in dangerous_patterns:
        if pattern in url_lower:
            return False, "invalid_url_format"

    return True, ""


def validate_device_name(name: str) -> tuple[bool, str]:
    """Validate a device name for security and correctness.

    Args:
        name: The device name to validate.

    Returns:
        Tuple of (is_valid, error_key). error_key is empty string if valid.
    """
    if not name or not name.strip():
        return False, "invalid_device_name"

    name = name.strip()

    # Check length
    if len(name) > MAX_DEVICE_NAME_LENGTH:
        return False, "device_name_too_long"

    # Check for path traversal attempts
    if ".." in name or "/" in name or "\\" in name:
        return False, "invalid_device_name"

    # Check allowed characters (alphanumeric, spaces, hyphens, underscores, periods)
    if not DEVICE_NAME_PATTERN.match(name):
        return False, "invalid_device_name"

    return True, ""


def validate_device_ip(ip: str) -> tuple[bool, str]:
    """Validate an IPv4 address string.

    Args:
        ip: The IP address string to validate.

    Returns:
        Tuple of (is_valid, error_key). error_key is empty string if valid.
    """
    if not ip or not ip.strip():
        return False, "invalid_device_ip"

    ip = ip.strip()
    parts = ip.split(".")
    if len(parts) != 4:
        return False, "invalid_device_ip"

    for part in parts:
        if not part.isdigit():
            return False, "invalid_device_ip"
        num = int(part)
        if num < 0 or num > 255:
            return False, "invalid_device_ip"
        if len(part) > 1 and part[0] == "0":
            return False, "invalid_device_ip"

    return True, ""


def get_device_display_title(device_name: str, device_ip: str, device_alias: str) -> str:
    """Return the display title for a device subentry.

    Priority order: alias > device_name > device_ip.

    Args:
        device_name: The Chromecast device name.
        device_ip: The device IP address.
        device_alias: An optional human-friendly alias.

    Returns:
        The best available display title, or 'Unknown Device' if all are empty.
    """
    if device_alias and device_alias.strip():
        return device_alias.strip()
    if device_name and device_name.strip():
        return device_name.strip()
    if device_ip and device_ip.strip():
        return device_ip.strip()
    return "Unknown Device"

# Subentry type for devices
SUBENTRY_TYPE_DEVICE = "device"


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate an old config entry to the current version.

    Args:
        hass: The Home Assistant instance.
        config_entry: The config entry to migrate.

    Returns:
        True if migration succeeded or was not needed.
    """
    _LOGGER.info(f"Migrating config entry from version {config_entry.version}")

    if config_entry.version < 3:
        new_data = dict(config_entry.data)
        new_options = dict(config_entry.options)

        if "devices" in new_data:
            new_options["devices"] = new_data.pop("devices", {})

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, version=3
        )

        _LOGGER.info("Configuration migration completed successfully")

    return True


class ContinuouslyCastingDashboardsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Continuously Cast Dashboards."""

    VERSION = 3

    def __init__(self):
        """Initialize the config flow."""
        self._devices = {}


    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return the options flow handler for this config entry.

        Args:
            config_entry: The active config entry.
        """
        return GlobalSettingsOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return a mapping of subentry type names to their flow handler classes.

        Args:
            config_entry: The active config entry.
        """
        return {SUBENTRY_TYPE_DEVICE: DeviceSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step for global settings.

        Args:
            user_input: Form data submitted by the user, or None on first render.

        Returns:
            A ConfigFlowResult that either creates the entry or re-shows the form.
        """
        errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            try:
                cleaned_input = {}

                for key in ["logging_level", "cast_delay", "start_time", "end_time"]:
                    if key in user_input and user_input[key] is not None:
                        cleaned_input[key] = user_input[key]

                if user_input.get("include_entity", False):
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state

                if not errors:
                    return self.async_create_entry(
                        title="Continuously Casting Dashboards",
                        data=cleaned_input,
                    )
            except Exception as ex:
                _LOGGER.exception("Unexpected exception in user step: %s", ex)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    "logging_level", default=DEFAULT_LOGGING_LEVEL
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Debug", "value": "debug"},
                            {"label": "Info", "value": "info"},
                            {"label": "Warning", "value": "warning"},
                            {"label": "Error", "value": "error"},
                            {"label": "Critical", "value": "critical"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("cast_delay", default=DEFAULT_CAST_DELAY): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Optional(
                    "start_time", default=DEFAULT_START_TIME
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time", default=DEFAULT_END_TIME
                ): selector.TimeSelector(),
                vol.Optional("include_entity", default=False): cv.boolean,
                vol.Optional("switch_entity_id", default=""): cv.string,
                vol.Optional("switch_entity_state", default=""): cv.string,
                vol.Optional("enable_notifications", default=True): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_import(
        self, import_config: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a config entry by importing settings from YAML configuration.

        Args:
            import_config: The configuration dict parsed from configuration.yaml.

        Returns:
            A ConfigFlowResult that creates the entry or aborts if one already exists.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        data = {
            "logging_level": import_config.get("logging_level", DEFAULT_LOGGING_LEVEL),
            "cast_delay": import_config.get("cast_delay", DEFAULT_CAST_DELAY),
            "start_time": import_config.get("start_time", DEFAULT_START_TIME),
            "end_time": import_config.get("end_time", DEFAULT_END_TIME),
        }

        if "switch_entity_id" in import_config:
            data["switch_entity_id"] = import_config["switch_entity_id"]

        if "switch_entity_state" in import_config:
            data["switch_entity_state"] = import_config["switch_entity_state"]

        # Store devices in options for migration
        options = {}
        if "devices" in import_config:
            options["devices"] = import_config["devices"]

        return self.async_create_entry(
            title="Continuously Casting Dashboards (imported)",
            data=data,
            options=options,
        )


class GlobalSettingsOptionsFlow(config_entries.OptionsFlow):
    """Handle global settings options flow."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize the global settings options flow.

        Args:
            config_entry: The config entry being edited.
        """
        super().__init__()
        self._entry = config_entry
        self._config = dict(config_entry.data)
        self._config.update(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Present and process the global settings form.

        Args:
            user_input: Submitted form data, or None on first render.

        Returns:
            A ConfigFlowResult that saves updated options or re-shows the form.
        """
        errors = {}

        if user_input is not None:
            try:
                cleaned_input = {}

                for key in ["logging_level", "cast_delay", "start_time", "end_time"]:
                    if key in user_input and user_input[key] is not None:
                        cleaned_input[key] = user_input[key]

                if user_input.get("include_entity", False):
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state

                if not errors:
                    # Preserve devices from options
                    devices = self._entry.options.get("devices", {})
                    new_options = {**cleaned_input, "devices": devices}

                    # Clean up empty entity fields
                    if "switch_entity_id" not in cleaned_input:
                        new_options.pop("switch_entity_id", None)
                        new_options.pop("switch_entity_state", None)

                    return self.async_create_entry(title="", data=new_options)

            except Exception as ex:
                _LOGGER.exception("Unexpected exception in options: %s", ex)
                errors["base"] = "unknown"

        has_entity = bool(self._config.get("switch_entity_id"))

        schema = vol.Schema(
            {
                vol.Required(
                    "logging_level",
                    default=self._config.get("logging_level", DEFAULT_LOGGING_LEVEL),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Debug", "value": "debug"},
                            {"label": "Info", "value": "info"},
                            {"label": "Warning", "value": "warning"},
                            {"label": "Error", "value": "error"},
                            {"label": "Critical", "value": "critical"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "cast_delay",
                    default=self._config.get("cast_delay", DEFAULT_CAST_DELAY),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Optional(
                    "start_time",
                    default=self._config.get("start_time", DEFAULT_START_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=self._config.get("end_time", DEFAULT_END_TIME),
                ): selector.TimeSelector(),
                vol.Optional("include_entity", default=has_entity): cv.boolean,
                vol.Optional(
                    "switch_entity_id",
                    default=self._config.get("switch_entity_id", ""),
                ): cv.string,
                vol.Optional(
                    "switch_entity_state",
                    default=self._config.get("switch_entity_state", ""),
                ): cv.string,
                vol.Optional(
                    "enable_notifications",
                    default=self._config.get("enable_notifications", True),
                ): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_count": str(len(self._entry.subentries)),
            },
        )


class DeviceSubentryFlow(ConfigSubentryFlow):
    """Handle device subentry flow - each device gets its own Configure button."""

    def __init__(self):
        """Initialize the device subentry flow."""
        super().__init__()
        self._dashboards: list[dict] = []
        self._current_dashboard_index: int | None = None
        self._device_name: str = ""
        self._device_ip: str = ""
        self._device_alias: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Collect device name, IP, and optional alias when adding a new device.

        Args:
            user_input: Submitted form data, or None on first render.

        Returns:
            A SubentryFlowResult that advances to the dashboard step or re-shows the form.
        """
        errors = {}

        if user_input is not None:
            try:
                device_name = user_input.get("device_name", "").strip()
                device_ip = user_input.get("device_ip", "").strip()
                device_alias = user_input.get("device_alias", "").strip()

                # At least one of device_name or device_ip must be provided
                if not device_name and not device_ip:
                    errors["device_name"] = "device_name_or_ip_required"

                # Validate device name if provided
                if device_name and not errors:
                    is_valid, error_key = validate_device_name(device_name)
                    if not is_valid:
                        errors["device_name"] = error_key

                # Validate device IP if provided
                if device_ip and not errors:
                    is_valid, error_key = validate_device_ip(device_ip)
                    if not is_valid:
                        errors["device_ip"] = error_key

                # Validate alias if provided
                if device_alias and not errors:
                    is_valid, error_key = validate_device_name(device_alias)
                    if not is_valid:
                        errors["device_alias"] = error_key

                # Check for duplicate subentries (match on alias > name > ip)
                if not errors:
                    new_title = get_device_display_title(device_name, device_ip, device_alias).lower()
                    for subentry in self._get_entry().subentries.values():
                        existing_title = get_device_display_title(
                            subentry.data.get("device_name", ""),
                            subentry.data.get("device_ip", ""),
                            subentry.data.get("device_alias", ""),
                        ).lower()
                        if existing_title == new_title:
                            errors["device_name"] = "device_already_exists"
                            break

                if not errors:
                    self._device_name = device_name
                    self._device_ip = device_ip
                    self._device_alias = device_alias
                    self._dashboards = []
                    return await self.async_step_add_dashboard()

            except Exception as ex:
                _LOGGER.exception("Error adding device: %s", ex)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Optional("device_name", default=""): cv.string,
                vol.Optional("device_ip", default=""): cv.string,
                vol.Optional("device_alias", default=""): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Collect dashboard URL and optional settings when adding a dashboard.

        Args:
            user_input: Submitted form data, or None on first render.

        Returns:
            A SubentryFlowResult that creates the subentry or loops back to add another.
        """
        errors = {}

        if user_input is not None:
            try:
                cleaned_input = {}

                dashboard_url = user_input.get("dashboard_url", "").strip()
                # Validate URL format and security
                is_valid, error_key = validate_dashboard_url(dashboard_url)
                if not is_valid:
                    errors["dashboard_url"] = error_key
                else:
                    cleaned_input["dashboard_url"] = dashboard_url

                if user_input.get("volume") is not None:
                    cleaned_input["volume"] = user_input["volume"]

                if user_input.get("enable_time_window", False):
                    if user_input.get("start_time"):
                        cleaned_input["start_time"] = user_input["start_time"]
                    if user_input.get("end_time"):
                        cleaned_input["end_time"] = user_input["end_time"]

                if user_input.get("include_entity", False):
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state

                if user_input.get("include_speaker_groups", False):
                    speaker_groups_input = user_input.get("speaker_groups", "").strip()
                    if speaker_groups_input:
                        speaker_groups = [
                            g.strip()
                            for g in speaker_groups_input.split(",")
                            if g.strip()
                        ]
                        if speaker_groups:
                            cleaned_input["speaker_groups"] = speaker_groups

                if not errors:
                    self._dashboards.append(cleaned_input)

                    if user_input.get("add_another", False):
                        return await self.async_step_add_dashboard()
                    else:
                        return self._create_device_entry()

            except Exception as ex:
                _LOGGER.exception("Error adding dashboard: %s", ex)
                errors["base"] = "unknown"

        # Get global settings for defaults
        entry = self._get_entry()
        global_config = dict(entry.data)
        global_config.update(entry.options)

        schema = vol.Schema(
            {
                vol.Required("dashboard_url"): cv.string,
                vol.Optional("volume", default=5): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional("enable_time_window", default=False): cv.boolean,
                vol.Optional(
                    "start_time",
                    default=global_config.get("start_time", DEFAULT_START_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=global_config.get("end_time", DEFAULT_END_TIME),
                ): selector.TimeSelector(),
                vol.Optional("include_entity", default=False): cv.boolean,
                vol.Optional("switch_entity_id", default=""): cv.string,
                vol.Optional("switch_entity_state", default=""): cv.string,
                vol.Optional("include_speaker_groups", default=False): cv.boolean,
                vol.Optional("speaker_groups", default=""): cv.string,
                vol.Optional("add_another", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="add_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": get_device_display_title(self._device_name, self._device_ip, self._device_alias),
                "dashboard_count": str(len(self._dashboards)),
            },
        )

    def _create_device_entry(self) -> SubentryFlowResult:
        """Finalise and create the device subentry from accumulated flow state.

        Returns:
            A SubentryFlowResult that persists the new subentry.
        """
        # Clean up dashboards
        cleaned_dashboards = []
        for dashboard in self._dashboards:
            cleaned = {}
            for key, value in dashboard.items():
                if isinstance(value, (datetime.datetime, datetime.time)):
                    continue
                if key in ["switch_entity_id", "switch_entity_state"]:
                    if value and str(value).strip():
                        cleaned[key] = value
                elif key == "speaker_groups":
                    if value and isinstance(value, list) and any(value):
                        cleaned[key] = value
                else:
                    cleaned[key] = value
            cleaned_dashboards.append(cleaned)

        title = get_device_display_title(self._device_name, self._device_ip, self._device_alias)
        return self.async_create_entry(
            title=title,
            data={
                "device_name": self._device_name,
                "device_ip": self._device_ip,
                "device_alias": self._device_alias,
                "dashboards": cleaned_dashboards,
            },
        )

    # ============ RECONFIGURE FLOW (for editing existing devices) ============

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguring an existing device subentry.

        Shows a unified settings form with all device configuration.
        """
        # Load existing data from the subentry being reconfigured
        subentry = self._get_reconfigure_subentry()
        self._device_name = subentry.data.get("device_name", "")
        self._device_ip = subentry.data.get("device_ip", "")
        self._device_alias = subentry.data.get("device_alias", "")
        self._dashboards = copy.deepcopy(subentry.data.get("dashboards", []))

        # If device has exactly one dashboard, go directly to edit it
        if len(self._dashboards) == 1:
            self._current_dashboard_index = 0
            return await self.async_step_reconfigure_device()
        elif len(self._dashboards) == 0:
            # No dashboards, go to add one
            return await self.async_step_reconfigure_add_dashboard()
        else:
            # Multiple dashboards, show selection menu
            return await self.async_step_reconfigure_select_dashboard()

    async def async_step_reconfigure_select_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show a list of dashboards to edit, add, or delete for multi-dashboard devices.

        Args:
            user_input: Selected action from the list, or None on first render.

        Returns:
            A SubentryFlowResult routing to the appropriate next step.
        """
        errors = {}

        if user_input is not None:
            action = user_input.get("dashboard_action")

            if action == "add_dashboard":
                return await self.async_step_reconfigure_add_dashboard()
            elif action and action.startswith("edit:"):
                self._current_dashboard_index = int(action.split(":")[1])
                return await self.async_step_reconfigure_device()
            elif action and action.startswith("delete:"):
                index = int(action.split(":")[1])
                if 0 <= index < len(self._dashboards):
                    self._dashboards.pop(index)
                    # If only one left, go to edit it
                    if len(self._dashboards) == 1:
                        self._current_dashboard_index = 0
                        return await self.async_step_reconfigure_device()
                    elif len(self._dashboards) == 0:
                        return await self.async_step_reconfigure_add_dashboard()
                return await self.async_step_reconfigure_select_dashboard()

        # Build options showing all dashboards
        options = []

        for i, dashboard in enumerate(self._dashboards):
            url = dashboard.get("dashboard_url", "Unknown")
            # Extract just the path for cleaner display
            if "://" in url:
                url_path = url.split("://", 1)[1]
                if "/" in url_path:
                    url_path = "/" + url_path.split("/", 1)[1]
                else:
                    url_path = url
            else:
                url_path = url
            display_url = url_path[:40] + "..." if len(url_path) > 40 else url_path

            info_parts = []
            if dashboard.get("volume") is not None:
                info_parts.append(f"Vol:{dashboard.get('volume')}")
            if dashboard.get("start_time") or dashboard.get("end_time"):
                start = dashboard.get("start_time", "")
                end = dashboard.get("end_time", "")
                if start or end:
                    info_parts.append(f"{start}-{end}")

            info_str = f" ({', '.join(info_parts)})" if info_parts else ""

            options.append({
                "label": f"Dashboard {i + 1}: {display_url}{info_str}",
                "value": f"edit:{i}",
            })

        options.append({"label": "Add another dashboard", "value": "add_dashboard"})

        # Add delete options at the end
        for i in range(len(self._dashboards)):
            options.append({
                "label": f"Delete dashboard {i + 1}",
                "value": f"delete:{i}",
            })

        schema = vol.Schema(
            {
                vol.Required("dashboard_action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfigure_select_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": get_device_display_title(self._device_name, self._device_ip, self._device_alias),
                "dashboard_count": str(len(self._dashboards)),
            },
        )

    async def async_step_reconfigure_device(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show a unified form for editing device identity and dashboard settings.

        Args:
            user_input: Submitted form data, or None on first render.

        Returns:
            A SubentryFlowResult that saves the updated subentry or re-shows the form.
        """
        errors = {}

        # Get current dashboard data
        if self._current_dashboard_index is not None and self._current_dashboard_index < len(self._dashboards):
            current = self._dashboards[self._current_dashboard_index]
        else:
            current = {}

        if user_input is not None:
            try:
                add_another = user_input.get("add_another_dashboard", False)
                delete_this = user_input.get("delete_this_dashboard", False)
                change_dashboard = user_input.get("change_dashboard", False)

                if delete_this:
                    if len(self._dashboards) > 1 and self._current_dashboard_index is not None:
                        self._dashboards.pop(self._current_dashboard_index)
                        self._current_dashboard_index = 0
                        return await self.async_step_reconfigure_device()
                    errors["base"] = "cannot_delete_last"

                if change_dashboard:
                    # Save without validation and go to dashboard selection
                    self._save_dashboard_from_input(user_input, current)
                    return await self.async_step_reconfigure_select_dashboard()

                # Save action - validate and save
                cleaned_input = {}

                # Device identifier fields (name and/or IP required, alias optional)
                new_device_name = user_input.get("device_name", "").strip()
                new_device_ip = user_input.get("device_ip", "").strip()
                new_device_alias = user_input.get("device_alias", "").strip()

                if not new_device_name and not new_device_ip:
                    errors["device_name"] = "device_name_or_ip_required"

                if new_device_name and not errors:
                    is_valid, error_key = validate_device_name(new_device_name)
                    if not is_valid:
                        errors["device_name"] = error_key

                if new_device_ip and not errors:
                    is_valid, error_key = validate_device_ip(new_device_ip)
                    if not is_valid:
                        errors["device_ip"] = error_key

                if new_device_alias and not errors:
                    is_valid, error_key = validate_device_name(new_device_alias)
                    if not is_valid:
                        errors["device_alias"] = error_key

                if not errors:
                    new_title = get_device_display_title(new_device_name, new_device_ip, new_device_alias).lower()
                    current_title = get_device_display_title(self._device_name, self._device_ip, self._device_alias).lower()
                    if new_title != current_title:
                        # Check for conflict with other subentries
                        entry = self._get_entry()
                        current_subentry = self._get_reconfigure_subentry()
                        for sid, subentry in entry.subentries.items():
                            if sid != current_subentry.subentry_id:
                                existing_title = get_device_display_title(
                                    subentry.data.get("device_name", ""),
                                    subentry.data.get("device_ip", ""),
                                    subentry.data.get("device_alias", ""),
                                ).lower()
                                if existing_title == new_title:
                                    errors["device_name"] = "device_already_exists"
                                    break

                if not errors:
                    self._device_name = new_device_name
                    self._device_ip = new_device_ip
                    self._device_alias = new_device_alias

                # Dashboard URL - validate format and security
                dashboard_url = user_input.get("dashboard_url", "").strip()
                is_valid, error_key = validate_dashboard_url(dashboard_url)
                if not is_valid:
                    errors["dashboard_url"] = error_key
                else:
                    cleaned_input["dashboard_url"] = dashboard_url

                if user_input.get("volume") is not None:
                    cleaned_input["volume"] = user_input["volume"]

                if user_input.get("enable_time_window", False):
                    if user_input.get("start_time"):
                        cleaned_input["start_time"] = user_input["start_time"]
                    if user_input.get("end_time"):
                        cleaned_input["end_time"] = user_input["end_time"]

                if user_input.get("include_entity", False):
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state

                if user_input.get("include_speaker_groups", False):
                    speaker_groups_input = user_input.get("speaker_groups", "").strip()
                    if speaker_groups_input:
                        speaker_groups = [
                            g.strip()
                            for g in speaker_groups_input.split(",")
                            if g.strip()
                        ]
                        if speaker_groups:
                            cleaned_input["speaker_groups"] = speaker_groups

                if not errors:
                    # Update the dashboard
                    if self._current_dashboard_index is not None and self._current_dashboard_index < len(self._dashboards):
                        self._dashboards[self._current_dashboard_index] = cleaned_input
                    else:
                        self._dashboards.append(cleaned_input)

                    if add_another:
                        return await self.async_step_reconfigure_add_dashboard()

                    return self._save_reconfigure()

            except Exception as ex:
                _LOGGER.exception("Error in device settings: %s", ex)
                errors["base"] = "unknown"

        # Build the form with current values
        speaker_groups = current.get("speaker_groups", [])
        speaker_groups_str = (
            ", ".join(speaker_groups) if isinstance(speaker_groups, list) else ""
        )

        has_time = bool(current.get("start_time") or current.get("end_time"))
        has_entity = bool(current.get("switch_entity_id"))
        has_groups = bool(current.get("speaker_groups"))

        # Get global settings for defaults
        entry = self._get_entry()
        global_config = dict(entry.data)
        global_config.update(entry.options)

        schema_fields = {
            vol.Optional(
                "device_name", default=self._device_name
            ): cv.string,
            vol.Optional(
                "device_ip", default=self._device_ip
            ): cv.string,
            vol.Optional(
                "device_alias", default=self._device_alias
            ): cv.string,
            vol.Required(
                "dashboard_url", default=current.get("dashboard_url", "")
            ): cv.string,
            vol.Optional(
                "volume", default=current.get("volume", 5)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional("enable_time_window", default=has_time): cv.boolean,
            vol.Optional(
                "start_time",
                default=current.get(
                    "start_time",
                    global_config.get("start_time", DEFAULT_START_TIME),
                ),
            ): selector.TimeSelector(),
            vol.Optional(
                "end_time",
                default=current.get(
                    "end_time",
                    global_config.get("end_time", DEFAULT_END_TIME),
                ),
            ): selector.TimeSelector(),
            vol.Optional("include_entity", default=has_entity): cv.boolean,
            vol.Optional(
                "switch_entity_id",
                default=current.get("switch_entity_id", ""),
            ): cv.string,
            vol.Optional(
                "switch_entity_state",
                default=current.get("switch_entity_state", ""),
            ): cv.string,
            vol.Optional("include_speaker_groups", default=has_groups): cv.boolean,
            vol.Optional("speaker_groups", default=speaker_groups_str): cv.string,
        }

        if len(self._dashboards) > 1:
            schema_fields[vol.Optional("change_dashboard", default=False)] = cv.boolean
            schema_fields[vol.Optional("delete_this_dashboard", default=False)] = cv.boolean

        schema_fields[vol.Optional("add_another_dashboard", default=False)] = cv.boolean

        schema = vol.Schema(schema_fields)

        dashboard_info = ""
        if len(self._dashboards) > 1:
            dashboard_info = f" (Dashboard {self._current_dashboard_index + 1} of {len(self._dashboards)})"

        return self.async_show_form(
            step_id="reconfigure_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": get_device_display_title(self._device_name, self._device_ip, self._device_alias),
                "dashboard_info": dashboard_info,
            },
        )

    def _save_dashboard_from_input(self, user_input: dict[str, Any], current: dict) -> None:
        """Persist dashboard form data to internal state without running validation.

        Used when the user navigates away (e.g. to the dashboard selector) before
        saving, so partial edits are not silently discarded.

        Args:
            user_input: Raw form values from the reconfigure_device step.
            current: The existing dashboard dict being updated.
        """
        cleaned_input = {}

        dashboard_url = user_input.get("dashboard_url", "").strip()
        if dashboard_url:
            cleaned_input["dashboard_url"] = dashboard_url

        if user_input.get("volume") is not None:
            cleaned_input["volume"] = user_input["volume"]

        if user_input.get("enable_time_window", False):
            if user_input.get("start_time"):
                cleaned_input["start_time"] = user_input["start_time"]
            if user_input.get("end_time"):
                cleaned_input["end_time"] = user_input["end_time"]

        if user_input.get("include_entity", False):
            entity_id = user_input.get("switch_entity_id", "").strip()
            if entity_id:
                cleaned_input["switch_entity_id"] = entity_id
                entity_state = user_input.get("switch_entity_state", "").strip()
                if entity_state:
                    cleaned_input["switch_entity_state"] = entity_state

        if user_input.get("include_speaker_groups", False):
            speaker_groups_input = user_input.get("speaker_groups", "").strip()
            if speaker_groups_input:
                speaker_groups = [g.strip() for g in speaker_groups_input.split(",") if g.strip()]
                if speaker_groups:
                    cleaned_input["speaker_groups"] = speaker_groups

        # Update device identifier fields if provided
        new_device_name = user_input.get("device_name", "").strip()
        new_device_ip = user_input.get("device_ip", "").strip()
        new_device_alias = user_input.get("device_alias", "").strip()
        if new_device_name or new_device_ip:
            self._device_name = new_device_name
            self._device_ip = new_device_ip
            self._device_alias = new_device_alias

        # Update the dashboard
        if cleaned_input.get("dashboard_url"):
            if self._current_dashboard_index is not None and self._current_dashboard_index < len(self._dashboards):
                self._dashboards[self._current_dashboard_index] = cleaned_input

    async def async_step_reconfigure_rename(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle renaming a device (sets the alias display name) during reconfiguration."""
        errors = {}
        current_title = get_device_display_title(self._device_name, self._device_ip, self._device_alias)

        if user_input is not None:
            try:
                new_name = user_input.get("new_device_name", "").strip()

                # Validate name format
                is_valid, error_key = validate_device_name(new_name)
                if not is_valid:
                    errors["new_device_name"] = error_key
                elif new_name.lower() != current_title.lower():
                    # Check if this display title already exists in other subentries
                    entry = self._get_entry()
                    current_subentry = self._get_reconfigure_subentry()
                    for sid, subentry in entry.subentries.items():
                        if sid != current_subentry.subentry_id:
                            existing_title = get_device_display_title(
                                subentry.data.get("device_name", ""),
                                subentry.data.get("device_ip", ""),
                                subentry.data.get("device_alias", ""),
                            ).lower()
                            if existing_title == new_name.lower():
                                errors["new_device_name"] = "device_already_exists"
                                break

                if not errors:
                    # Store as alias so it becomes the display title
                    self._device_alias = new_name
                    return await self.async_step_reconfigure_device()

            except Exception as ex:
                _LOGGER.exception("Error renaming device: %s", ex)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required("new_device_name", default=current_title): cv.string,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_rename",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure_add_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new dashboard to an existing device during reconfiguration.

        Args:
            user_input: Submitted form data, or None on first render.

        Returns:
            A SubentryFlowResult that saves the updated subentry or re-shows the form.
        """
        errors = {}

        if user_input is not None:
            try:
                cleaned_input = {}

                dashboard_url = user_input.get("dashboard_url", "").strip()
                # Validate URL format and security
                is_valid, error_key = validate_dashboard_url(dashboard_url)
                if not is_valid:
                    errors["dashboard_url"] = error_key
                else:
                    cleaned_input["dashboard_url"] = dashboard_url

                if user_input.get("volume") is not None:
                    cleaned_input["volume"] = user_input["volume"]

                if user_input.get("enable_time_window", False):
                    if user_input.get("start_time"):
                        cleaned_input["start_time"] = user_input["start_time"]
                    if user_input.get("end_time"):
                        cleaned_input["end_time"] = user_input["end_time"]

                if user_input.get("include_entity", False):
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state

                if user_input.get("include_speaker_groups", False):
                    speaker_groups_input = user_input.get("speaker_groups", "").strip()
                    if speaker_groups_input:
                        speaker_groups = [
                            g.strip()
                            for g in speaker_groups_input.split(",")
                            if g.strip()
                        ]
                        if speaker_groups:
                            cleaned_input["speaker_groups"] = speaker_groups

                if not errors:
                    self._dashboards.append(cleaned_input)
                    # Set the new dashboard as current and go to the device form
                    self._current_dashboard_index = len(self._dashboards) - 1
                    return self._save_reconfigure()

            except Exception as ex:
                _LOGGER.exception("Error adding dashboard: %s", ex)
                errors["base"] = "unknown"

        # Get global settings for defaults
        entry = self._get_entry()
        global_config = dict(entry.data)
        global_config.update(entry.options)

        schema = vol.Schema(
            {
                vol.Required("dashboard_url"): cv.string,
                vol.Optional("volume", default=5): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional("enable_time_window", default=False): cv.boolean,
                vol.Optional(
                    "start_time",
                    default=global_config.get("start_time", DEFAULT_START_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=global_config.get("end_time", DEFAULT_END_TIME),
                ): selector.TimeSelector(),
                vol.Optional("include_entity", default=False): cv.boolean,
                vol.Optional("switch_entity_id", default=""): cv.string,
                vol.Optional("switch_entity_state", default=""): cv.string,
                vol.Optional("include_speaker_groups", default=False): cv.boolean,
                vol.Optional("speaker_groups", default=""): cv.string,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_add_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": get_device_display_title(self._device_name, self._device_ip, self._device_alias),
            },
        )

    def _save_reconfigure(self) -> SubentryFlowResult:
        """Persist the updated device subentry and abort the reconfigure flow.

        Returns:
            A SubentryFlowResult that commits the changes and closes the flow.
        """
        # Clean up dashboards
        cleaned_dashboards = []
        for dashboard in self._dashboards:
            cleaned = {}
            for key, value in dashboard.items():
                if isinstance(value, (datetime.datetime, datetime.time)):
                    continue
                if key in ["switch_entity_id", "switch_entity_state"]:
                    if value and str(value).strip():
                        cleaned[key] = value
                elif key == "speaker_groups":
                    if value and isinstance(value, list) and any(value):
                        cleaned[key] = value
                else:
                    cleaned[key] = value
            cleaned_dashboards.append(cleaned)

        title = get_device_display_title(self._device_name, self._device_ip, self._device_alias)
        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            title=title,
            data={
                "device_name": self._device_name,
                "device_ip": self._device_ip,
                "device_alias": self._device_alias,
                "dashboards": cleaned_dashboards,
            },
        )
