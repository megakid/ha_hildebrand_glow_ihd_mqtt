"""The hildebrand_glow_ihd_mqtt component."""
import logging

from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION, CONF_DEVICE_ID  # noqa: N812
from homeassistant.core import HomeAssistant

from .const import (
    CONF_FORCE_UPDATE,
    CONF_HIDE_GAS_SENSORS,
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_FORCE_UPDATE,
    DEFAULT_HIDE_GAS_SENSORS,
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

    # Prefer options over data so users can adjust settings via Options Flow
    device_id_raw = entry.options.get(CONF_DEVICE_ID, entry.data[CONF_DEVICE_ID])
    topic_prefix_raw = entry.options.get(
        CONF_TOPIC_PREFIX, entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    )
    time_zone_electricity = entry.options.get(
        CONF_TIME_ZONE_ELECTRICITY, entry.data.get(CONF_TIME_ZONE_ELECTRICITY)
    )
    time_zone_gas = entry.options.get(
        CONF_TIME_ZONE_GAS, entry.data.get(CONF_TIME_ZONE_GAS)
    )
    force_update = entry.options.get(
        CONF_FORCE_UPDATE, entry.data.get(CONF_FORCE_UPDATE, DEFAULT_FORCE_UPDATE)
    )
    hide_gas_sensors = entry.options.get(
        CONF_HIDE_GAS_SENSORS, entry.data.get(CONF_HIDE_GAS_SENSORS, DEFAULT_HIDE_GAS_SENSORS)
    )

    hass.data[DOMAIN][entry.entry_id][CONF_DEVICE_ID] = (
        device_id_raw.strip().upper().replace(":", "").replace(" ", "")
    )
    hass.data[DOMAIN][entry.entry_id][CONF_TOPIC_PREFIX] = (
        topic_prefix_raw.strip().replace("#", "").replace(" ", "")
    )
    hass.data[DOMAIN][entry.entry_id][CONF_TIME_ZONE_ELECTRICITY] = time_zone_electricity
    hass.data[DOMAIN][entry.entry_id][CONF_TIME_ZONE_GAS] = time_zone_gas
    hass.data[DOMAIN][entry.entry_id][CONF_FORCE_UPDATE] = force_update
    hass.data[DOMAIN][entry.entry_id][CONF_HIDE_GAS_SENSORS] = hide_gas_sensors

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry on options update
    entry.async_on_unload(entry.add_update_listener(_async_entry_update_listener))

    _LOGGER.debug("Finished setting up Hildebrand Glow IHD MQTT integration")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        try:
            del hass.data[DOMAIN][entry.entry_id]
        except KeyError:
            pass
    return unload_ok


async def _async_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry options update by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
    return None
