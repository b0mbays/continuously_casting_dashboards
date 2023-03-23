import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN

class HaContinuousCastingDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chromecast Dashboard Cast."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Chromecast Dashboard Cast", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional("cast_delay", default=10): int,
                    vol.Required("devices"): vol.All(
                        [vol.Schema(
                            {
                                vol.Required("name"): str,
                                vol.Required("dashboard_url"): str,
                            }
                        )],
                    ),
                }
            ),
            errors=errors,
        )