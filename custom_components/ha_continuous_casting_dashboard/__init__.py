"""The Continuously Cast Dashboards integration."""
from .const import DOMAIN, PLATFORMS
from .cast import HaContinuousCastingDashboard
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

CONFIG_SCHEMA = cv.deprecated(DOMAIN)

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
