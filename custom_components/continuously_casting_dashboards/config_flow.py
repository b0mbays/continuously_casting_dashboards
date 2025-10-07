"""Config flow for Continuously Cast Dashboards integration."""

import logging
import voluptuous as vol
from typing import Any, Dict, List, Optional
import copy
import datetime

from homeassistant.helpers import selector
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL, CONF_HOST
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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate an old config entry to a new version."""
    _LOGGER.info(f"Migrating config entry from version {config_entry.version}")

    if config_entry.version < 2:
        # Migrate configuration to new structure
        new_data = dict(config_entry.data)
        new_options = dict(config_entry.options)

        # Ensure devices are in options if they were previously in data
        if "devices" in new_data:
            new_options["devices"] = new_data.pop("devices", {})

        # Update the config entry
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, version=2
        )

        _LOGGER.info("Configuration migration completed successfully")

    return True


def log_config_entry_state(hass, entry_id, message="Current config entry state"):
    """Log the current state of a config entry for debugging purposes."""
    try:
        if not hass:
            _LOGGER.error("Cannot log config state: hass is None")
            return

        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            _LOGGER.error(f"Cannot log config state: entry {entry_id} not found")
            return

        _LOGGER.info(f"{message}:")
        _LOGGER.info(f"Entry ID: {entry.entry_id}")
        _LOGGER.info(f"Entry Title: {entry.title}")
        _LOGGER.info(f"Entry Domain: {entry.domain}")
        _LOGGER.info(f"Entry Data: {entry.data}")
        _LOGGER.info(f"Entry Options: {entry.options}")
        _LOGGER.info(f"Entry State: {entry.state}")
        _LOGGER.info(f"Entry Version: {entry.version}")

    except Exception as ex:
        _LOGGER.exception(f"Error logging config state: {ex}")


class ContinuouslyCastingDashboardsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Continuously Cast Dashboards."""

    VERSION = 2  # Increment version to trigger config entry migration if needed

    def __init__(self):
        """Initialize the config flow."""
        self._devices = {}
        self._current_device = None
        self._current_dashboard_index = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ContinuouslyCastingDashboardsOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors = {}

        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            try:
                # Start with a clean slate
                cleaned_input = {}

                # Handle all basic config options
                for key in ["logging_level", "cast_delay", "start_time", "end_time"]:
                    if key in user_input and user_input[key] is not None:
                        cleaned_input[key] = user_input[key]

                # Handle entity selection
                if user_input.get("include_entity", False):
                    # Only include entity if the checkbox is checked
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        # Validate that the entity exists
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            # Include state if provided
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state
                    else:
                        # Empty entity but checkbox is checked - this is OK, we just won't add the config
                        pass

                if not errors:
                    # Proceed to create entry
                    return self.async_create_entry(
                        title="Continuously Cast Dashboards",
                        data=cleaned_input,
                    )
            except Exception as ex:
                _LOGGER.exception("Unexpected exception in user step: %s", ex)
                errors["base"] = "unknown"

        # Show the form
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
                vol.Optional(
                    "include_entity",
                    default=False,
                ): cv.boolean,
                vol.Optional(
                    "switch_entity_id",
                    default="",
                ): cv.string,
                vol.Optional(
                    "switch_entity_state",
                    default=self._base_config.get("switch_entity_state", ""),
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            last_step=True,  # This adds a back button
        )

    async def async_step_import(
        self, import_config=None
    ) -> config_entries.ConfigFlowResult:
        """Import a config entry from YAML."""
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Extract the base configuration
        data = {
            "logging_level": import_config.get("logging_level", DEFAULT_LOGGING_LEVEL),
            "cast_delay": import_config.get("cast_delay", DEFAULT_CAST_DELAY),
            "start_time": import_config.get("start_time", DEFAULT_START_TIME),
            "end_time": import_config.get("end_time", DEFAULT_END_TIME),
        }

        # Handle optional parameters
        if "switch_entity_id" in import_config:
            data["switch_entity_id"] = import_config["switch_entity_id"]

        if "switch_entity_state" in import_config:
            data["switch_entity_state"] = import_config["switch_entity_state"]

        # Handle devices - will be stored in options
        options = {}
        if "devices" in import_config:
            options["devices"] = import_config["devices"]

        return self.async_create_entry(
            title="Continuously Cast Dashboards (imported)", data=data, options=options
        )


class ContinuouslyCastingDashboardsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ContinuouslyCastingDashboards."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        super().__init__()
        self._entry = config_entry

        # Retrieve data, prioritizing options over data
        self._base_config = dict(config_entry.data)
        self._base_config.update(config_entry.options)

        # Devices will be stored and retrieved from options
        self._devices = config_entry.options.get("devices", {})

        # Temporary storage for current operation
        self._current_device = None
        self._current_dashboard_index = None

    async def async_step_init(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Manage the options flow."""
        return await self.async_step_main_options()

    async def async_step_main_options(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Manage the main options."""
        errors = {}

        if user_input is not None:
            try:
                # Start with a clean slate
                cleaned_input = {}

                # Handle all basic config options
                for key in ["logging_level", "cast_delay", "start_time", "end_time"]:
                    if key in user_input and user_input[key] is not None:
                        cleaned_input[key] = user_input[key]

                # Handle entity selection
                if user_input.get("include_entity", False):
                    # Only include entity if the checkbox is checked
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        # Validate that the entity exists
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            # Include state if provided
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state
                    else:
                        # Empty entity but checkbox is checked - this is OK, we just won't add the config
                        pass
                else:
                    # Remove entity config from base config if checkbox is unchecked
                    self._base_config.pop("switch_entity_id", None)
                    self._base_config.pop("switch_entity_state", None)

                if not errors:
                    # Update base configuration
                    self._base_config.update(cleaned_input)

                    # Remove entity config if not included in cleaned_input
                    if "switch_entity_id" not in cleaned_input:
                        self._base_config.pop("switch_entity_id", None)
                        self._base_config.pop("switch_entity_state", None)

                    # Proceed to device menu
                    return await self.async_step_device_menu()

            except Exception as ex:
                _LOGGER.exception("Unexpected exception in main_options: %s", ex)
                errors["base"] = "unknown"

        # Determine if entity is currently configured
        has_entity = bool(self._base_config.get("switch_entity_id"))

        # Create schema with default values from existing configuration
        schema = vol.Schema(
            {
                vol.Required(
                    "logging_level",
                    default=self._base_config.get(
                        "logging_level", DEFAULT_LOGGING_LEVEL
                    ),
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
                    default=self._base_config.get("cast_delay", DEFAULT_CAST_DELAY),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Optional(
                    "start_time",
                    default=self._base_config.get("start_time", DEFAULT_START_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=self._base_config.get("end_time", DEFAULT_END_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "include_entity",
                    default=bool(self._base_config.get("switch_entity_id")),
                ): cv.boolean,
                vol.Optional(
                    "switch_entity_id",
                    default=self._base_config.get("switch_entity_id", ""),
                ): cv.string,
                vol.Optional(
                    "switch_entity_state",
                    default=self._base_config.get("switch_entity_state", ""),
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="main_options",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": "Global Options",
                "entity_hint": "Type an entity ID (e.g., switch.my_switch) or leave blank if checkbox is unchecked",
                "state_hint": "Type a valid state value (can leave blank if 'on', 'true', 'home', or 'open')",
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_device_menu(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle the device menu for options flow."""
        errors = {}

        if user_input is not None:
            try:
                action = user_input.get("action")

                if action == "add_device":
                    return await self.async_step_add_device()
                elif action == "edit_device":
                    if user_input.get("device"):
                        self._current_device = user_input.get("device")
                        return await self.async_step_edit_device()
                    else:
                        errors["device"] = "missing_device_selection"
                elif action == "remove_device":
                    if user_input.get("device"):
                        self._current_device = user_input.get("device")
                        return await self.async_step_remove_device()
                    else:
                        errors["device"] = "missing_device_selection"
                elif action == "finish":
                    # Prepare final options with deep copy to avoid modifying originals
                    new_options = copy.deepcopy(self._base_config)
                    new_options["devices"] = copy.deepcopy(self._devices)

                    # Remove non-serializable objects from options
                    for device_name, dashboards in new_options.get(
                        "devices", {}
                    ).items():
                        for dashboard in dashboards:
                            # Remove datetime objects which aren't JSON serializable
                            keys_to_remove = []
                            for key, value in dashboard.items():
                                if isinstance(
                                    value, (datetime.datetime, datetime.time)
                                ):
                                    keys_to_remove.append(key)

                            # Remove the keys in a separate loop to avoid modifying during iteration
                            for key in keys_to_remove:
                                dashboard.pop(key, None)

                    # Thoroughly clean up the switch entity fields
                    # First, check global config switch entity and remove if empty
                    if "switch_entity_id" in new_options:
                        # Remove if empty, whitespace, or matches the default
                        if (
                            not new_options["switch_entity_id"]
                            or not new_options["switch_entity_id"].strip()
                        ):
                            new_options.pop("switch_entity_id", None)
                            new_options.pop("switch_entity_state", None)

                    # Special handling for switch_entity_state without switch_entity_id
                    if (
                        "switch_entity_state" in new_options
                        and "switch_entity_id" not in new_options
                    ):
                        new_options.pop("switch_entity_state", None)

                    # Then check each dashboard's switch entity settings
                    for device_name, dashboards in new_options.get(
                        "devices", {}
                    ).items():
                        for dashboard in dashboards:
                            # Remove empty switch entity fields
                            if "switch_entity_id" in dashboard:
                                if (
                                    not dashboard["switch_entity_id"]
                                    or not dashboard["switch_entity_id"].strip()
                                ):
                                    dashboard.pop("switch_entity_id", None)
                                    dashboard.pop("switch_entity_state", None)

                            # Also catch orphaned switch_entity_state without switch_entity_id
                            if (
                                "switch_entity_state" in dashboard
                                and "switch_entity_id" not in dashboard
                            ):
                                dashboard.pop("switch_entity_state", None)

                    # Final cleanup to ensure no empty switch entity settings remain
                    if (
                        "switch_entity_id" in new_options
                        and not new_options["switch_entity_id"]
                    ):
                        new_options.pop("switch_entity_id", None)
                        new_options.pop("switch_entity_state", None)

                    for device_name, dashboards in new_options.get(
                        "devices", {}
                    ).items():
                        for dashboard in dashboards:
                            if (
                                "switch_entity_id" in dashboard
                                and not dashboard["switch_entity_id"]
                            ):
                                dashboard.pop("switch_entity_id", None)
                                dashboard.pop("switch_entity_state", None)

                    # Remove empty speaker_groups from each dashboard
                    for device_name, dashboards in new_options.get(
                        "devices", {}
                    ).items():
                        for dashboard in dashboards:
                            if "speaker_groups" in dashboard:
                                speaker_groups = dashboard["speaker_groups"]
                                if not speaker_groups or (
                                    isinstance(speaker_groups, list)
                                    and not any(speaker_groups)
                                ):
                                    dashboard.pop("speaker_groups", None)

                    try:
                        # Check if there are actual changes
                        current_options = self._entry.options
                        current_dict = dict(current_options)
                        new_dict = dict(new_options)

                        if new_dict == current_dict:
                            return self.async_abort(reason="options_updated")

                        # Update the config entry
                        self.hass.config_entries.async_update_entry(
                            self._entry, options=new_options
                        )

                        # Reload the entry
                        await self.hass.config_entries.async_reload(
                            self._entry.entry_id
                        )

                        _LOGGER.info(
                            f"Successfully updated and reloaded entry {self._entry.entry_id}"
                        )

                        return self.async_abort(reason="options_updated")
                    except Exception as ex:
                        _LOGGER.exception(f"Error updating config entry: {ex}")
                        errors["base"] = f"update_failed: {str(ex)}"
            except Exception as ex:
                _LOGGER.exception("Error in device menu: %s", ex)
                errors["base"] = "unknown"

        # Get the device list
        device_names = list(self._devices.keys()) if self._devices else []

        # Create the action options
        actions = [
            {"label": "Add a new device", "value": "add_device"},
            {"label": "Finish configuration", "value": "finish"},
        ]

        if device_names:
            actions.insert(
                1, {"label": "Edit an existing device", "value": "edit_device"}
            )
            actions.insert(
                2, {"label": "Remove an existing device", "value": "remove_device"}
            )

        # Build the form schema
        schema_dict = {
            vol.Required("action", default="add_device"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=actions,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        # Only add device selector if we have devices
        if device_names:
            # Convert device names to label/value pairs
            device_options = [{"label": name, "value": name} for name in device_names]

            # Add empty option for when add/finish is selected
            device_options.insert(
                0, {"label": "Not required for Add/Finish", "value": ""}
            )

            schema_dict[vol.Optional("device", default="")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=device_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="device_menu",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": "Device Management",
                "devices": (
                    ", ".join(device_names)
                    if device_names
                    else "No devices configured yet"
                ),
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_add_device(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle adding a new device."""
        errors = {}

        if user_input is not None:
            try:
                device_name = user_input.get("device_name", "").strip()

                if not device_name:
                    errors["device_name"] = "invalid_device_name"
                elif device_name in self._devices:
                    errors["device_name"] = "device_already_exists"
                else:
                    # Add new device with empty dashboard list
                    self._devices[device_name] = []
                    self._current_device = device_name

                    # Go to dashboard configuration for this device
                    return await self.async_step_dashboard_menu()
            except Exception as ex:
                _LOGGER.exception("Error adding device: %s", ex)
                errors["base"] = "unknown"

        # Basic UI for device name input
        schema = vol.Schema(
            {
                vol.Required("device_name"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="add_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={"title": "Add Device"},
            last_step=True,  # This adds a back button
        )

    async def async_step_edit_device(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle editing a device."""
        if not self._current_device:
            _LOGGER.warning("Attempting to edit device with no device selected")
            return await self.async_step_device_menu()

        # Go directly to dashboard menu for this device
        return await self.async_step_dashboard_menu()

    async def async_step_remove_device(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle removing a device."""
        errors = {}

        if not self._current_device:
            _LOGGER.warning("Attempting to remove device with no device selected")
            return await self.async_step_device_menu()

        if user_input is not None:
            try:
                if user_input.get("confirm_remove"):
                    # Check if device exists before attempting to remove
                    if self._current_device in self._devices:
                        # Remove the device
                        del self._devices[self._current_device]
                    else:
                        _LOGGER.warning(
                            f"Device {self._current_device} not found in devices dict"
                        )

                    # Return to device menu
                    return await self.async_step_device_menu()

                # Return to device menu if not confirmed
                return await self.async_step_device_menu()
            except Exception as ex:
                _LOGGER.exception(f"Error removing device {self._current_device}: {ex}")
                errors["base"] = "unknown"

        # Basic UI for confirmation
        schema = vol.Schema(
            {
                vol.Required("confirm_remove", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="remove_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
                "title": "Remove Device",
                "confirmation": f"Are you sure you want to remove device '{self._current_device}'?",
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_dashboard_menu(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle the dashboard menu for a device."""
        errors = {}

        if not self._current_device:
            _LOGGER.warning(
                "Attempting to access dashboard menu with no device selected"
            )
            return await self.async_step_device_menu()

        try:
            if user_input is not None:
                action = user_input.get("action")

                if action == "add_dashboard":
                    return await self.async_step_add_dashboard()
                elif action == "edit_dashboard" and "dashboard" in user_input:
                    self._current_dashboard_index = int(user_input["dashboard"])
                    return await self.async_step_edit_dashboard()
                elif action == "remove_dashboard" and "dashboard" in user_input:
                    self._current_dashboard_index = int(user_input["dashboard"])
                    return await self.async_step_remove_dashboard()
                elif action == "back":
                    return await self.async_step_device_menu()
                else:
                    if action in ["edit_dashboard", "remove_dashboard"]:
                        errors["dashboard"] = "missing_dashboard_selection"
        except Exception as ex:
            _LOGGER.exception("Error in dashboard menu: %s", ex)
            errors["base"] = "unknown"

        # Get device dashboards
        device_dashboards = self._devices.get(self._current_device, [])

        # Create labels for dashboards
        dashboard_labels = {}
        for i, dashboard in enumerate(device_dashboards):
            url = dashboard.get("dashboard_url", "Dashboard")
            start = dashboard.get("start_time", DEFAULT_START_TIME)
            end = dashboard.get("end_time", DEFAULT_END_TIME)
            dashboard_labels[str(i)] = f"{url} ({start}-{end})"

        # Prepare action options
        actions = [
            {"label": "Add a new dashboard", "value": "add_dashboard"},
            {"label": "Back to device menu", "value": "back"},
        ]

        if device_dashboards:  # Only show edit/remove if we have dashboards
            actions.insert(
                1, {"label": "Edit an existing dashboard", "value": "edit_dashboard"}
            )
            actions.insert(
                2,
                {"label": "Remove an existing dashboard", "value": "remove_dashboard"},
            )

        # Build the form schema
        schema_dict = {
            vol.Required("action", default="add_dashboard"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=actions,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        # Only add dashboard selector if we have dashboards
        if dashboard_labels:
            # Convert dashboard labels to label/value pairs
            dashboard_options = [
                {"label": label, "value": key}
                for key, label in dashboard_labels.items()
            ]
            schema_dict[vol.Optional("dashboard")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=dashboard_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="dashboard_menu",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
                "title": "Dashboard Management",
                "dashboards_count": str(len(device_dashboards)),
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_add_dashboard(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle adding a new dashboard for a device."""
        errors = {}

        if not self._current_device:
            _LOGGER.warning("Attempting to add dashboard with no device selected")
            return await self.async_step_device_menu()

        if user_input is not None:
            try:
                # Start with a clean slate
                cleaned_input = {}

                # Handle basic dashboard options
                for key in [
                    "dashboard_url",
                    "volume",
                    "enable_time_window",
                    "start_time",
                    "end_time",
                ]:
                    if key in user_input and user_input[key] is not None:
                        if key == "dashboard_url" and not user_input[key].strip():
                            # Must have a dashboard URL
                            errors["dashboard_url"] = "missing_dashboard_url"
                            continue
                        cleaned_input[key] = user_input[key]

                # Ensure required field is present
                if not errors and (
                    "dashboard_url" not in cleaned_input
                    or not cleaned_input["dashboard_url"]
                ):
                    errors["dashboard_url"] = "missing_dashboard_url"

                # Handle entity selection
                if user_input.get("include_entity", False):
                    # Only include entity if the checkbox is checked
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        # Validate that the entity exists
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            # Include state if provided
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state
                    else:
                        # Empty entity but checkbox is checked - this is OK, we just won't add the config
                        pass

                # Handle speaker groups
                if user_input.get("include_speaker_groups", False):
                    # Only include speaker groups if the checkbox is checked
                    speaker_groups_input = user_input.get("speaker_groups", "").strip()

                    if speaker_groups_input:  # Not empty
                        speaker_groups = [
                            group.strip()
                            for group in speaker_groups_input.split(",")
                            if group.strip()
                        ]

                        for group in speaker_groups:
                            # Check if it's a valid speaker group by friendly name
                            found = False
                            for entity_id in self.hass.states.async_entity_ids(
                                "media_player"
                            ):
                                state = self.hass.states.get(entity_id)
                                if (
                                    state
                                    and not state.attributes.get("device_class")
                                    and "group" in entity_id.lower()
                                    and state.attributes.get("friendly_name") == group
                                ):
                                    found = True
                                    break
                            if not found:
                                errors["speaker_groups"] = "entity_not_found"
                                break

                        if not errors.get("speaker_groups"):
                            cleaned_input["speaker_groups"] = speaker_groups
                    else:
                        # Empty but checkbox is checked - this is OK, we just won't add the config
                        pass
                else:
                    # Explicitly remove speaker_groups when checkbox is unchecked
                    cleaned_input["speaker_groups"] = None

                # If time window is disabled, remove time settings
                if not cleaned_input.get("enable_time_window", False):
                    cleaned_input.pop("start_time", None)
                    cleaned_input.pop("end_time", None)
                # Remove enable_time_window as it's only for UI
                cleaned_input.pop("enable_time_window", None)

                if not errors:
                    # Add new dashboard to device
                    if self._current_device not in self._devices:
                        self._devices[self._current_device] = []

                    self._devices[self._current_device].append(cleaned_input)

                    # Return to dashboard menu
                    return await self.async_step_dashboard_menu()
            except Exception as ex:
                _LOGGER.exception("Error adding dashboard: %s", ex)
                errors["base"] = "unknown"

        # Basic UI for dashboard configuration
        schema = vol.Schema(
            {
                vol.Required("dashboard_url"): cv.string,
                vol.Optional("volume", default=3): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10)
                ),
                vol.Optional("enable_time_window", default=False): cv.boolean,
                vol.Optional(
                    "start_time",
                    default=self._base_config.get("start_time", DEFAULT_START_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=self._base_config.get("end_time", DEFAULT_END_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    "include_entity",
                    default=False,
                ): cv.boolean,
                vol.Optional(
                    "switch_entity_id",
                    default="",
                ): cv.string,
                vol.Optional(
                    "switch_entity_state",
                    default="",
                ): cv.string,
                vol.Optional(
                    "include_speaker_groups",
                    default=False,
                ): cv.boolean,
                vol.Optional(
                    "speaker_groups",
                    default="",
                ): cv.string,  # Comma-separated list
            }
        )

        return self.async_show_form(
            step_id="add_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_edit_dashboard(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle editing a dashboard for a device."""
        errors = {}
        if not self._current_device or self._current_dashboard_index is None:
            _LOGGER.warning(
                "Attempting to edit dashboard with no device or dashboard selected"
            )
            return await self.async_step_dashboard_menu()

        device_dashboards = self._devices.get(self._current_device, [])

        if len(device_dashboards) <= self._current_dashboard_index:
            # Index out of range, go back to dashboard menu
            _LOGGER.warning("Dashboard index out of range")
            return await self.async_step_dashboard_menu()

        current_dashboard = device_dashboards[self._current_dashboard_index]

        if user_input is not None:
            try:
                # Start with a clean slate
                cleaned_input = {}

                # Handle basic dashboard options
                for key in [
                    "dashboard_url",
                    "volume",
                    "enable_time_window",
                    "start_time",
                    "end_time",
                ]:
                    if key in user_input and user_input[key] is not None:
                        if key == "dashboard_url" and not user_input[key].strip():
                            # Must have a dashboard URL
                            errors["dashboard_url"] = "missing_dashboard_url"
                            continue
                        cleaned_input[key] = user_input[key]

                # Ensure required field is present
                if not errors and (
                    "dashboard_url" not in cleaned_input
                    or not cleaned_input["dashboard_url"]
                ):
                    errors["dashboard_url"] = "missing_dashboard_url"

                # Handle entity selection
                if user_input.get("include_entity", False):
                    # Only include entity if the checkbox is checked
                    entity_id = user_input.get("switch_entity_id", "").strip()
                    if entity_id:
                        # Validate that the entity exists
                        if self.hass and self.hass.states.get(entity_id) is None:
                            errors["switch_entity_id"] = "entity_not_found"
                        else:
                            cleaned_input["switch_entity_id"] = entity_id
                            # Include state if provided
                            entity_state = user_input.get(
                                "switch_entity_state", ""
                            ).strip()
                            if entity_state:
                                cleaned_input["switch_entity_state"] = entity_state
                    else:
                        # Empty entity but checkbox is checked - this is OK, we just won't add the config
                        pass

                # Handle speaker groups
                if user_input.get("include_speaker_groups", False):
                    # Only include speaker groups if the checkbox is checked
                    speaker_groups_input = user_input.get("speaker_groups", "").strip()

                    if speaker_groups_input:  # Not empty
                        speaker_groups = [
                            group.strip()
                            for group in speaker_groups_input.split(",")
                            if group.strip()
                        ]

                        if speaker_groups:  # Has valid entries after cleaning
                            for group in speaker_groups:
                                # Check if it's a valid speaker group by friendly name
                                found = False
                                for entity_id in self.hass.states.async_entity_ids(
                                    "media_player"
                                ):
                                    state = self.hass.states.get(entity_id)
                                    if (
                                        state
                                        and not state.attributes.get("device_class")
                                        and "group" in entity_id.lower()
                                        and state.attributes.get("friendly_name")
                                        == group
                                    ):
                                        found = True
                                        break
                                if not found:
                                    errors["speaker_groups"] = "entity_not_found"
                                    break

                            if not errors.get("speaker_groups"):
                                cleaned_input["speaker_groups"] = speaker_groups
                    else:
                        # Empty but checkbox is checked - this is OK, we just won't add the config
                        pass
                else:
                    # Explicitly remove speaker_groups when checkbox is unchecked
                    cleaned_input["speaker_groups"] = None

                # If time window is disabled, remove time settings
                if not cleaned_input.get("enable_time_window", False):
                    cleaned_input.pop("start_time", None)
                    cleaned_input.pop("end_time", None)
                # Remove enable_time_window as it's only for UI
                cleaned_input.pop("enable_time_window", None)

                if not errors:
                    # Update the dashboard with new values
                    updated_dashboard = {**current_dashboard}
                    updated_dashboard.update(cleaned_input)

                    # Remove entity config if not included
                    if "switch_entity_id" not in cleaned_input:
                        updated_dashboard.pop("switch_entity_id", None)
                        updated_dashboard.pop("switch_entity_state", None)

                    # Remove time settings if time window is disabled
                    if not user_input.get("enable_time_window", False):
                        updated_dashboard.pop("start_time", None)
                        updated_dashboard.pop("end_time", None)

                    # Remove speaker_groups if checkbox not checked
                    if not user_input.get("include_speaker_groups", False):
                        updated_dashboard.pop("speaker_groups", None)
                    elif "speaker_groups" not in cleaned_input:
                        # Checkbox checked but no valid input - remove it
                        updated_dashboard.pop("speaker_groups", None)
                    elif cleaned_input.get("speaker_groups") is None:
                        # Explicitly handle None case
                        updated_dashboard.pop("speaker_groups", None)

                    device_dashboards[self._current_dashboard_index] = updated_dashboard
                    # Return to dashboard menu
                    return await self.async_step_dashboard_menu()
            except Exception as ex:
                _LOGGER.exception("Error editing dashboard: %s", ex)
                errors["base"] = "unknown"

        # Convert speaker_groups list to comma-separated string for the form
        speaker_groups = current_dashboard.get("speaker_groups", [])
        speaker_groups_str = (
            ", ".join(speaker_groups) if isinstance(speaker_groups, list) else ""
        )

        # Determine if speaker groups are currently configured
        has_speaker_groups = bool(current_dashboard.get("speaker_groups"))

        # Determine if entity is currently configured
        has_entity = bool(current_dashboard.get("switch_entity_id"))

        # Basic UI for dashboard editing
        schema = vol.Schema(
            {
                vol.Required(
                    "dashboard_url", default=current_dashboard.get("dashboard_url", "")
                ): cv.string,
                vol.Optional(
                    "volume", default=current_dashboard.get("volume", 3)
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Optional(
                    "enable_time_window",
                    default=bool(
                        current_dashboard.get("start_time")
                        or current_dashboard.get("end_time")
                    ),
                ): cv.boolean,
                vol.Optional(
                    "start_time",
                    default=current_dashboard.get(
                        "start_time",
                        self._base_config.get("start_time", DEFAULT_START_TIME),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "end_time",
                    default=current_dashboard.get(
                        "end_time",
                        self._base_config.get("end_time", DEFAULT_END_TIME),
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    "include_entity",
                    default=has_entity,
                ): cv.boolean,
                vol.Optional(
                    "switch_entity_id",
                    default=current_dashboard.get("switch_entity_id", ""),
                ): cv.string,
                vol.Optional(
                    "switch_entity_state",
                    default=current_dashboard.get("switch_entity_state", ""),
                ): cv.string,
                vol.Optional(
                    "include_speaker_groups",
                    default=has_speaker_groups,
                ): cv.boolean,
                vol.Optional(
                    "speaker_groups",
                    default=speaker_groups_str,
                ): cv.string,  # Comma-separated list
            }
        )

        return self.async_show_form(
            step_id="edit_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
            },
            last_step=True,  # This adds a back button
        )

    async def async_step_remove_dashboard(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle removing a dashboard for a device."""
        errors = {}

        if not self._current_device or self._current_dashboard_index is None:
            _LOGGER.warning(
                "Attempting to remove dashboard with no device or dashboard selected"
            )
            return await self.async_step_dashboard_menu()

        device_dashboards = self._devices.get(self._current_device, [])

        if len(device_dashboards) <= self._current_dashboard_index:
            # Index out of range, go back to dashboard menu
            _LOGGER.warning("Dashboard index out of range")
            return await self.async_step_dashboard_menu()

        if user_input is not None:
            try:
                if user_input.get("confirm_remove"):
                    # Remove the dashboard
                    device_dashboards.pop(self._current_dashboard_index)
                    self._devices[self._current_device] = device_dashboards

                    # Return to dashboard menu
                    return await self.async_step_dashboard_menu()

                # Return to dashboard menu if not confirmed
                return await self.async_step_dashboard_menu()
            except Exception as ex:
                _LOGGER.exception("Error removing dashboard: %s", ex)
                errors["base"] = "unknown"

        # Get dashboard info for confirmation
        dashboard = device_dashboards[self._current_dashboard_index]
        dashboard_url = dashboard.get("dashboard_url", "Unknown dashboard")

        # Basic UI for confirmation
        schema = vol.Schema(
            {
                vol.Required("confirm_remove", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="remove_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
                "dashboard": dashboard_url,
                "title": "Remove Dashboard",
            },
            last_step=True,  # This adds a back button
        )
