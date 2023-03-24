"""The Continuously Cast Dashboards integration."""
from .const import DOMAIN, PLATFORMS
from .dashboard_caster import HaContinuousCastingDashboard
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.const import CONF_DEVICES, CONF_SCAN_INTERVAL

CONF_START_TIME = "start_time"
CONF_END_TIME = "end_time"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(cv.url),
                vol.Optional(CONF_SCAN_INTERVAL, default=60): cv.positive_int,
                vol.Optional(CONF_START_TIME, default="06:00"): cv.string,
                vol.Optional(CONF_END_TIME, default="01:00"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

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