"""The hildebrand_glow_ihd_mqtt component."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
)
from homeassistant.core import HomeAssistant

from .const import(
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Hildebrand Glow IHD MQTT integration."""

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("Setting up Hildebrand Glow IHD MQTT integration")

    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {}

    hass.data[DOMAIN][entry.entry_id][CONF_DEVICE_ID] = entry.data[CONF_DEVICE_ID]



    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component))

    _LOGGER.debug("Finished setting up Hildebrand Glow IHD MQTT integration")
    return True

