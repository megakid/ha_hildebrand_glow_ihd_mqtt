"""End-to-end sensor tests: MQTT message in, entity state out."""
import json
import logging
from unittest.mock import patch

from homeassistant.core import State
from homeassistant.helpers.entity_component import EntityComponent

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

DOMAIN = "hildebrand_glow_ihd"
TOPIC = "glow/AABBCCDDEEFF/SENSOR/electricitymeter"


def _electricity(*, unitrate, standingcharge, day=10.0, power=0.5,
                 timestamp="2025-12-28T20:30:03Z"):
    return json.dumps(
        {
            "electricitymeter": {
                "timestamp": timestamp,
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
    sensor = HildebrandGlowMqttSensor(
        device_id="AABBCCDDEEFF", time_zone="Europe/London", **meter
    )
    # Unit tests bypass the HA lifecycle; integration tests exercise restoration.
    sensor._cost_ready = True
    return sensor


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

    # Without a timestamp, usage cannot safely be assigned to a meter day.
    assert sensor.native_value is None


def test_sensor_skips_payload_missing_a_field():
    sensor = _cost_sensor()
    sensor.process_update(json.loads(_electricity(unitrate=0.25, standingcharge=0.5)))

    sensor.process_update({"electricitymeter": {"timestamp": "2025-12-28T20:30:03Z"}})

    assert sensor.native_value == 3.0


async def test_tariff_change_does_not_reprice_previous_usage(hass, setup_glow):
    for day, rate, timestamp, expected in (
        (10, 0.20, "2025-12-28T20:00:00Z", "2.5"),
        (11, 0.30, "2025-12-28T21:00:00Z", "2.7"),
        (12, 0.30, "2025-12-28T22:00:00Z", "3.0"),
    ):
        async_fire_mqtt_message(hass, TOPIC, _electricity(
            unitrate=rate, standingcharge=0.5, day=day, timestamp=timestamp))
        await hass.async_block_till_done()
        assert _state(hass, "electricity_cost_today").state == expected


def _update_cost(sensor, day=10, rate=.20, timestamp="2025-12-28T20:00:00Z", standing=.50):
    sensor.process_update(json.loads(_electricity(
        unitrate=rate, standingcharge=standing, day=day, timestamp=timestamp)))


@pytest.mark.parametrize("bad", [None, "bad", float("nan"), float("inf")])
def test_invalid_reading_preserves_accumulator(bad):
    sensor = _cost_sensor()
    _update_cost(sensor)
    _update_cost(sensor, day=bad, timestamp="2025-12-28T21:00:00Z")
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["prev_kwh"] == 10
    _update_cost(sensor, day=12, timestamp="2025-12-28T22:00:00Z")
    assert sensor.native_value == 2.9


@pytest.mark.parametrize("field", ["unitrate", "standingcharge"])
def test_null_price_does_not_advance_baseline(field):
    sensor = _cost_sensor()
    _update_cost(sensor)
    payload = json.loads(_electricity(unitrate=.30, standingcharge=.50, day=11,
                                    timestamp="2025-12-28T21:00:00Z"))
    payload["electricitymeter"]["energy"]["import"]["price"][field] = None
    sensor.process_update(payload)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["prev_kwh"] == 10
    _update_cost(sensor, day=12, rate=.30, timestamp="2025-12-28T22:00:00Z")
    assert sensor.native_value == 2.9


def test_rollover_includes_first_reading():
    sensor = _cost_sensor()
    _update_cost(sensor)
    _update_cost(sensor, day=.1, rate=.30, timestamp="2025-12-29T00:01:00Z")
    assert sensor.native_value == .53
    assert sensor.last_reset.isoformat() == "2025-12-29T00:00:00+00:00"
    assert sensor.extra_state_attributes["cost_estimated"] is True


def test_summer_meter_day_uses_british_midnight():
    sensor = _cost_sensor()
    _update_cost(sensor, day=.1, timestamp="2025-07-01T23:01:00Z")
    assert sensor.last_reset.isoformat() == "2025-07-01T23:00:00+00:00"


def test_stale_and_decreasing_readings_do_not_double_count():
    sensor = _cost_sensor()
    _update_cost(sensor)
    _update_cost(sensor, day=9, timestamp="2025-12-28T19:00:00Z")
    assert sensor.native_value == 2.5
    _update_cost(sensor, day=0, timestamp="2025-12-28T21:00:00Z")
    assert sensor.native_value is None
    _update_cost(sensor, day=11, timestamp="2025-12-28T22:00:00Z")
    assert sensor.native_value == 2.7


def test_free_and_negative_rates_are_valid():
    sensor = _cost_sensor()
    _update_cost(sensor, day=0, rate=0)
    _update_cost(sensor, day=1, rate=-.1, timestamp="2025-12-28T21:00:00Z")
    assert sensor.native_value == .5
    _update_cost(sensor, day=2, rate=-.1, timestamp="2025-12-28T22:00:00Z")
    assert sensor.native_value == .4


async def test_restore_before_processing_queued_message(hass):
    sensor = _cost_sensor()
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    sensor.entity_id = "sensor.test_incremental_cost"
    sensor._cost_ready = False
    # Original custom-file attributes remain supported (no last_cost_timestamp).
    previous = State(sensor.entity_id, "1.5", {
        "cost_accum": 1., "prev_kwh": 10., "prev_rate": .20,
        "last_reset_utc": "2025-12-28T00:00:00+00:00",
    })
    _update_cost(sensor, day=11)
    assert sensor.native_value is None
    with patch.object(sensor, "async_get_last_state", return_value=previous):
        await component.async_add_entities([sensor])
    await hass.async_block_till_done()
    assert sensor.native_value == 1.7
    assert sensor.last_reset.isoformat() == "2025-12-28T00:00:00+00:00"
    await component.async_remove_entity(sensor.entity_id)


async def test_restore_reset_without_new_message(hass):
    original = _cost_sensor()
    _update_cost(original)
    sensor = _cost_sensor()
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    sensor.entity_id = "sensor.test_restored_cost"
    previous = State(sensor.entity_id, "2.5", original.extra_state_attributes)
    with patch.object(sensor, "async_get_last_state", return_value=previous):
        await component.async_add_entities([sensor])
    assert sensor.native_value == 2.5
    assert sensor.last_reset == original.last_reset
    _update_cost(sensor, day=11, timestamp="2025-12-28T21:00:00Z")
    assert sensor.native_value == 2.7
    await hass.async_block_till_done()
    await component.async_remove_entity(sensor.entity_id)
