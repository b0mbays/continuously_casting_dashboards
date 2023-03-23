"""The Continuously Cast Dashboards integration."""
from .const import DOMAIN, PLATFORMS
from .cast import HaContinuousCastingDashboard
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_DEVICES): {cv.string: cv.url},
                vol.Optional("cast_delay", default=10): int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Continuously Cast Dashboards integration."""
    hass.data.setdefault(DOMAIN, {})
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    # Start the HaContinuousCastingDashboard
    caster = HaContinuousCastingDashboard(hass, entry.data)
    hass.loop.create_task(caster.start())
    return True
