"""The Continuously Cast Dashboards integration."""
from .const import DOMAIN, PLATFORMS
from .dashboard_caster import HaContinuousCastingDashboard
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Continuously Cast Dashboards integration."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True

    hass.data.setdefault(DOMAIN, {})

    # Start the HaContinuousCastingDashboard
    caster = HaContinuousCastingDashboard(hass, conf)
    hass.loop.create_task(caster.start())
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Continuously Cast Dashboards integration from a config entry."""
    conf = entry.data

    # Start the HaContinuousCastingDashboard
    caster = HaContinuousCastingDashboard(hass, conf)
    hass.loop.create_task(caster.start())

    return True
