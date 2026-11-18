"""End-to-end sensor tests: MQTT message in, entity state out."""
import json

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

DOMAIN = "hildebrand_glow_ihd"
TOPIC = "glow/AABBCCDDEEFF/SENSOR/electricitymeter"


def _electricity(*, unitrate, standingcharge, day=10.0, power=0.5):
    return json.dumps(
        {
            "electricitymeter": {
                "timestamp": "2025-12-28T20:30:03Z",
                "energy": {
                    "export": {"cumulative": 0.0, "units": "kWh"},
                    "import": {
                        "cumulative": 49221.641,
                        "day": day,
                        "week": 346.266,
                        "month": 1181.386,
                        "units": "kWh",
                        "mpan": "Metering PointID",
                        "supplier": "---",
                        "price": {
                            "unitrate": unitrate,
                            "standingcharge": standingcharge,
                        },
                    },
                },
                "power": {"value": power, "units": "kW"},
            }
        }
    )


@pytest.fixture
async def setup_glow(hass, mqtt_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="hildebrand_glow_ihd_+",
        data={
            "device_id": "+",
            "topic_prefix": "glow",
            "time_zone_electricity": "Europe/London",
            "time_zone_gas": "Europe/London",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass, suffix: str):
    return hass.states.get(f"sensor.glow_smart_meter_aabbccddeeff_smart_meter_{suffix}")


async def test_normal_message_updates_sensors(hass, setup_glow):
    async_fire_mqtt_message(
        hass, TOPIC, _electricity(unitrate=0.25, standingcharge=0.5)
    )
    await hass.async_block_till_done()

    assert _state(hass, "electricity_power").state == "0.5"
    assert _state(hass, "electricity_cost_today").state == "3.0"


async def test_missing_prices_do_not_stop_the_other_sensors(hass, setup_glow, caplog):
    """Suppliers that publish null prices (#90, #68, #29) must not break the rest."""
    async_fire_mqtt_message(
        hass, TOPIC, _electricity(unitrate=None, standingcharge=None, power=0.75)
    )
    await hass.async_block_till_done()

    assert _state(hass, "electricity_power").state == "0.75"
    assert _state(hass, "electricity_import_today").state == "10.0"
    assert _state(hass, "electricity_cost_today").state == "unknown"
    assert "Exception in mqtt_message_received" not in caplog.text


def _cost_sensor():
    from custom_components.hildebrand_glow_ihd.sensor import ELECTRICITY_SENSORS
    from custom_components.hildebrand_glow_ihd.sensor import HildebrandGlowMqttSensor

    meter = next(m for m in ELECTRICITY_SENSORS if m["name"].endswith("Cost (Today)"))
    return HildebrandGlowMqttSensor(
        device_id="AABBCCDDEEFF", time_zone="Europe/London", **meter
    )


def test_cost_sensor_survives_null_prices():
    sensor = _cost_sensor()

    sensor.process_update(
        json.loads(_electricity(unitrate=None, standingcharge=None))
    )

    assert sensor.native_value is None


def test_cost_sensor_survives_payload_without_timestamp():
    """The timestamp parser must raise ValueError, not break its own except clause."""
    sensor = _cost_sensor()
    payload = json.loads(_electricity(unitrate=0.25, standingcharge=0.5))
    del payload["electricitymeter"]["timestamp"]

    sensor.process_update(payload)

    assert sensor.native_value == 3.0


def test_sensor_skips_payload_missing_a_field():
    sensor = _cost_sensor()
    sensor.process_update(json.loads(_electricity(unitrate=0.25, standingcharge=0.5)))

    sensor.process_update({"electricitymeter": {"timestamp": "2025-12-28T20:30:03Z"}})

    assert sensor.native_value == 3.0
