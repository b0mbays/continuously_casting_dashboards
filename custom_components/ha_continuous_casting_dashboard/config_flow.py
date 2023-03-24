from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

import voluptuous as vol

class HaContinuousCastingDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_UNKNOWN

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            # Process the input and create a new config entry
            return self.async_create_entry(title="Continuously Casting Dashboard", data=user_input)

        # Define the configuration form schema
        data_schema = vol.Schema({
            vol.Required("logging_level", default="info"): str,
            # Add more configuration options here
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)