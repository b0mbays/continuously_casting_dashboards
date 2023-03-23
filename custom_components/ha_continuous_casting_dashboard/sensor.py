from homeassistant.helpers.entity import Entity

from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    async_add_entities([DummySensor()])

class DummySensor(Entity):
    @property
    def name(self):
        return "Dummy Sensor"

    @property
    def state(self):
        return "dummy"
