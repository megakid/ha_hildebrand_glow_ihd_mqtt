"""Config flow tests."""
from homeassistant.data_entry_flow import FlowResultType

DOMAIN = "hildebrand_glow_ihd"


async def _create_entry(hass, device_id):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "device_id": device_id,
            "topic_prefix": "glow",
            "time_zone_electricity": "Europe/London",
            "time_zone_gas": "Europe/London",
        },
    )


async def test_entry_has_a_title(hass, mqtt_mock):
    """An empty title shows up as 'Created configuration for .' (issue #88)."""
    result = await _create_entry(hass, "+")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hildebrand Glow IHD MQTT"


async def test_entry_title_names_a_specific_device(hass, mqtt_mock):
    result = await _create_entry(hass, "AABBCCDDEEFF")

    assert result["title"] == "Hildebrand Glow IHD MQTT (AABBCCDDEEFF)"


def test_config_flow_uses_no_deprecated_connection_class():
    """CONN_CLASS_LOCAL_PUSH is removed in Home Assistant 2027.5 (issue #95).

    The IoT class comes from manifest.json, so the flow must not set one.
    """
    from custom_components.hildebrand_glow_ihd import config_flow

    assert not hasattr(config_flow, "CONN_CLASS_LOCAL_PUSH")
    assert "CONNECTION_CLASS" not in vars(config_flow.HildebrandGlowIHDMQTTConfigFlow)
