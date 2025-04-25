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
    _LOGGER.debug(f"Migrating config entry from version {config_entry.version}")

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

        _LOGGER.debug(f"{message}:")
        _LOGGER.debug(f"Entry ID: {entry.entry_id}")
        _LOGGER.debug(f"Entry Title: {entry.title}")
        _LOGGER.debug(f"Entry Domain: {entry.domain}")
        _LOGGER.debug(f"Entry Data: {entry.data}")
        _LOGGER.debug(f"Entry Options: {entry.options}")
        _LOGGER.debug(f"Entry State: {entry.state}")
        _LOGGER.debug(f"Entry Version: {entry.version}")
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
                # Clean up empty string values to avoid validation issues
                cleaned_input = {
                    k: v for k, v in user_input.items() if v != "" and v is not None
                }

                # Special handling for switch_entity_id - if empty, remove it
                if (
                    "switch_entity_id" in cleaned_input
                    and not cleaned_input["switch_entity_id"]
                ):
                    cleaned_input.pop("switch_entity_id")

                # Validate the user input
                return self.async_create_entry(
                    title="Continuously Cast Dashboards",
                    data=cleaned_input,
                )
            except Exception as ex:
                _LOGGER.exception("Unexpected exception in user step: %s", ex)
                errors["base"] = "unknown"

        # Get available switch entities
        switch_entities = []
        if self.hass:
            switch_entities = [
                f"{entity_id}"
                for entity_id in self.hass.states.async_entity_ids("switch")
            ]

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
                vol.Optional("switch_entity_id", default=""): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""] + switch_entities,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "switch_entity_state", default=""
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Not required", "value": ""},
                            {"label": "On", "value": "on"},
                            {"label": "Off", "value": "off"},
                            {"label": "Unavailable", "value": "unavailable"},
                            {"label": "Unknown", "value": "unknown"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
        _LOGGER.debug("Entering async_step_init")
        return await self.async_step_main_options()

    async def async_step_main_options(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Manage the main options."""
        errors = {}

        _LOGGER.debug("Entering async_step_main_options")
        _LOGGER.debug(f"User input: {user_input}")

        if user_input is not None:
            try:
                # Clean up empty string values
                cleaned_input = {
                    k: v for k, v in user_input.items() if v != "" and v is not None
                }

                # Special handling for switch_entity_id - if empty, remove it
                if (
                    "switch_entity_id" in cleaned_input
                    and not cleaned_input["switch_entity_id"]
                ):
                    cleaned_input.pop("switch_entity_id")

                _LOGGER.debug(f"Cleaned input: {cleaned_input}")

                # Update base configuration
                self._base_config.update(cleaned_input)

                # Proceed to device menu
                _LOGGER.debug("Proceeding to device menu")
                return await self.async_step_device_menu()
            except Exception as ex:
                _LOGGER.exception("Unexpected exception in main_options: %s", ex)
                errors["base"] = "unknown"

        # Get available switch entities
        switch_entities = []
        if self.hass:
            switch_entities = [
                f"{entity_id}"
                for entity_id in self.hass.states.async_entity_ids("switch")
            ]

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
                    "switch_entity_id",
                    default=self._base_config.get("switch_entity_id", ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""]
                        + [
                            f"{entity_id}"
                            for entity_id in self.hass.states.async_entity_ids("switch")
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "switch_entity_state",
                    default=self._base_config.get("switch_entity_state", ""),
                ): cv.string,  # Allow any valid state
            }
        )

        _LOGGER.debug("Showing main options form")
        return self.async_show_form(
            step_id="main_options",
            data_schema=schema,
            errors=errors,
            description_placeholders={"title": "Global Options"},
            last_step=True,  # This adds a back button
        )

    async def async_step_device_menu(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle the device menu for options flow."""
        errors = {}

        _LOGGER.debug("Entering async_step_device_menu")
        _LOGGER.debug(f"Current base config: {self._base_config}")
        _LOGGER.debug(f"Current devices: {self._devices}")

        if user_input is not None:
            try:
                action = user_input.get("action")

                _LOGGER.debug(f"Selected action: {action}")

                if action == "add_device":
                    _LOGGER.debug("Navigating to add_device step")
                    return await self.async_step_add_device()
                elif action == "edit_device":
                    if user_input.get("device"):
                        self._current_device = user_input.get("device")
                        _LOGGER.debug(
                            f"Navigating to edit_device step for {self._current_device}"
                        )
                        return await self.async_step_edit_device()
                    else:
                        _LOGGER.debug("No device selected for editing")
                        errors["device"] = "missing_device_selection"
                elif action == "remove_device":
                    if user_input.get("device"):
                        self._current_device = user_input.get("device")
                        _LOGGER.debug(
                            f"Navigating to remove_device step for {self._current_device}"
                        )
                        return await self.async_step_remove_device()
                    else:
                        _LOGGER.debug("No device selected for removal")
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

                    _LOGGER.debug(
                        f"Final options being created (cleaned for storage): {new_options}"
                    )

                    try:
                        # Log current state before update
                        log_config_entry_state(
                            self.hass, self._entry.entry_id, "Before updating config"
                        )

                        # Check if there are actual changes
                        current_options = self._entry.options
                        if new_options == current_options:
                            _LOGGER.debug("No changes detected, skipping reload")
                            return self.async_abort(reason="options_updated")

                        # Update the config entry (this returns a bool, don't await it)
                        self.hass.config_entries.async_update_entry(
                            self._entry, options=new_options
                        )

                        # Log state after updating
                        log_config_entry_state(
                            self.hass, self._entry.entry_id, "After updating config"
                        )

                        # Reload the entry (this is a coroutine, needs to be awaited)
                        await self.hass.config_entries.async_reload(
                            self._entry.entry_id
                        )

                        _LOGGER.info(
                            f"Successfully updated and reloaded entry {self._entry.entry_id}"
                        )

                        # Abort the flow instead of creating an empty entry
                        return self.async_abort(reason="options_updated")
                    except Exception as ex:
                        _LOGGER.exception(f"Detailed error updating config entry: {ex}")
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

        _LOGGER.debug("Showing device menu form")
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
                    _LOGGER.debug(f"Removing device {self._current_device}")
                    _LOGGER.debug(f"Devices before removal: {self._devices}")

                    # Check if device exists before attempting to remove
                    if self._current_device in self._devices:
                        # Remove the device
                        del self._devices[self._current_device]
                        _LOGGER.debug(f"Devices after removal: {self._devices}")
                    else:
                        _LOGGER.warning(
                            f"Device {self._current_device} not found in devices dict"
                        )

                    # Return to device menu
                    return await self.async_step_device_menu()

                # Return to device menu if not confirmed
                _LOGGER.debug("Device removal not confirmed, returning to menu")
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
                # Clean up empty string values to avoid validation issues
                cleaned_input = {
                    k: v for k, v in user_input.items() if v != "" and v is not None
                }

                # If time window is disabled, remove time settings
                if not cleaned_input.get("enable_time_window", False):
                    cleaned_input.pop("start_time", None)
                    cleaned_input.pop("end_time", None)
                # Remove enable_time_window as it's only for UI
                cleaned_input.pop("enable_time_window", None)

                # Ensure required field is present
                if (
                    "dashboard_url" not in cleaned_input
                    or not cleaned_input["dashboard_url"]
                ):
                    errors["dashboard_url"] = "missing_dashboard_url"
                else:
                    # Process speaker_groups if present
                    if "speaker_groups" in cleaned_input and isinstance(
                        cleaned_input["speaker_groups"], str
                    ):
                        speaker_groups = [
                            group.strip()
                            for group in cleaned_input["speaker_groups"].split(",")
                            if group.strip()
                        ]
                        cleaned_input["speaker_groups"] = speaker_groups

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
                    "switch_entity_id",
                    default="",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""]
                        + [
                            f"{entity_id}"
                            for entity_id in self.hass.states.async_entity_ids("switch")
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "switch_entity_state", default=""
                ): cv.string,  # Allow any valid state
                vol.Optional(
                    "speaker_groups",
                    default="",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""]
                        + [
                            f"{self.hass.states.get(entity_id).attributes.get('friendly_name', entity_id)}"
                            for entity_id in self.hass.states.async_entity_ids(
                                "media_player"
                            )
                            if not self.hass.states.get(entity_id).attributes.get(
                                "device_class"
                            )
                            and "group" in entity_id.lower()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
                "title": "Add Dashboard",
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
                # Clean up empty string values
                cleaned_input = {
                    k: v for k, v in user_input.items() if v != "" and v is not None
                }

                # If time window is disabled, remove time settings
                if not cleaned_input.get("enable_time_window", False):
                    cleaned_input.pop("start_time", None)
                    cleaned_input.pop("end_time", None)
                # Remove enable_time_window as it's only for UI
                cleaned_input.pop("enable_time_window", None)

                # Ensure required field is present
                if (
                    "dashboard_url" not in cleaned_input
                    or not cleaned_input["dashboard_url"]
                ):
                    errors["dashboard_url"] = "missing_dashboard_url"
                else:
                    # Process speaker_groups if present
                    if "speaker_groups" in cleaned_input and isinstance(
                        cleaned_input["speaker_groups"], str
                    ):
                        speaker_groups = [
                            group.strip()
                            for group in cleaned_input["speaker_groups"].split(",")
                            if group.strip()
                        ]
                        cleaned_input["speaker_groups"] = speaker_groups

                    # Update the dashboard with new values
                    device_dashboards[self._current_dashboard_index] = {
                        **current_dashboard,
                        **cleaned_input,
                    }

                    # If time window is disabled, ensure time settings are removed from the saved config
                    if not cleaned_input.get("enable_time_window", False):
                        device_dashboards[self._current_dashboard_index].pop(
                            "start_time", None
                        )
                        device_dashboards[self._current_dashboard_index].pop(
                            "end_time", None
                        )

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
                    "switch_entity_id",
                    default=self._base_config.get("switch_entity_id", ""),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""]
                        + [
                            f"{entity_id}"
                            for entity_id in self.hass.states.async_entity_ids("switch")
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "switch_entity_state",
                    default=current_dashboard.get("switch_entity_state", ""),
                ): cv.string,  # Allow any valid state
                vol.Optional(
                    "speaker_groups",
                    default="",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[""]
                        + [
                            f"{self.hass.states.get(entity_id).attributes.get('friendly_name', entity_id)}"
                            for entity_id in self.hass.states.async_entity_ids(
                                "media_player"
                            )
                            if not self.hass.states.get(entity_id).attributes.get(
                                "device_class"
                            )
                            and "group" in entity_id.lower()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="edit_dashboard",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device": self._current_device,
                "title": "Edit Dashboard",
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
