"""The hildebrand_glow_ihd_mqtt component."""
import logging

from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION, CONF_DEVICE_ID  # noqa: N812
from homeassistant.core import HomeAssistant

from .const import (
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    MIN_HA_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Hildebrand Glow IHD MQTT integration."""

    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):  # pragma: no cover
        msg = (
            "This integration requires at least HomeAssistant version "
            f" {MIN_HA_VERSION}, you are running version {HA_VERSION}."
            " Please upgrade HomeAssistant to continue use of this integration."
        )
        _LOGGER.critical(msg)
        return False

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("Setting up Hildebrand Glow IHD MQTT integration")

    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {}

    hass.data[DOMAIN][entry.entry_id][CONF_DEVICE_ID] = entry.data[CONF_DEVICE_ID].strip().upper().replace(":", "").replace(" ", "")
    hass.data[DOMAIN][entry.entry_id][CONF_TOPIC_PREFIX] = entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX).strip().replace("#", "").replace(" ", "")
    hass.data[DOMAIN][entry.entry_id][CONF_TIME_ZONE_ELECTRICITY] = entry.data.get(CONF_TIME_ZONE_ELECTRICITY)
    hass.data[DOMAIN][entry.entry_id][CONF_TIME_ZONE_GAS] = entry.data.get(CONF_TIME_ZONE_GAS)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Finished setting up Hildebrand Glow IHD MQTT integration")
    return True

