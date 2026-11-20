"""Support for hildebrand glow MQTT sensors."""

from __future__ import annotations
from datetime import datetime, time, timedelta, tzinfo
import json
import logging
import math
import re
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE_ID,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import (
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_DEVICE_ID,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    MeterInterval,
)

_LOGGER = logging.getLogger(__name__)

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

def _electricity_cost_today(meter: dict) -> float | None:
    """Return today's cost, or None while the meter has not published its prices.

    Some suppliers (and an IHD that has not been provisioned yet) publish null
    for the unit rate and standing charge.
    """
    import_ = meter["energy"]["import"]
    price = import_["price"]
    standing_charge = price["standingcharge"]
    unit_rate = price["unitrate"]
    day = import_["day"]
    if standing_charge is None or unit_rate is None or day is None:
        return None
    return round(standing_charge + day * unit_rate, 2)


# The IHD reports the day/week/month gas volumes (dayvol, weekvol, monthvol) in
# the unit named by dayweekmonthvolunits: kWh on most devices, where they repeat
# day/week/month, and m3 on others (#98). The cumulative volume is always m3.
GAS_PERIOD_VOLUME_UNITS = {
    "kWh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
    "m3": (SensorDeviceClass.GAS, UnitOfVolume.CUBIC_METERS),
}

GAS_PERIOD_VOLUME = {
    # Until the first gas message (or a restored state) says otherwise, kWh, the
    # unit these sensors had before 1.9.2. Payloads without the field stay kWh.
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "units_func": lambda js: js["gasmeter"]["energy"]["import"].get(
        "dayweekmonthvolunits", "kWh"
    ),
    "units_by_name": GAS_PERIOD_VOLUME_UNITS,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "icon": "mdi:fire",
}


STATE_SENSORS = [
    {
        "name": "Smart Meter IHD Software Version",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["software"],
    },
    {
        "name": "Smart Meter IHD Hardware",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["hardware"],
    },
    {
        "name": "Smart Meter IHD HAN Status",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["han"]["status"],
    },
    {
        "name": "Smart Meter IHD HAN RSSI",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "unit_of_measurement": SIGNAL_STRENGTH_DECIBELS,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["rssi"],
    },
    {
        "name": "Smart Meter IHD HAN LQI",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["lqi"],
    },
]

ELECTRICITY_SENSORS = [
    {
        "name": "Smart Meter Electricity: Export",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["export"]["cumulative"],
    },
    {
        "name": "Smart Meter Electricity: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Electricity: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Electricity: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Electricity: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "unitrate"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Power",
        "device_class": SensorDeviceClass.POWER,
        "unit_of_measurement": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["power"]["value"],
        "error_response_values": [-8388.608],
    },
    {
        "name": "Smart Meter Electricity: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "meter_interval": MeterInterval.DAY,
        "func": lambda js: _electricity_cost_today(js["electricitymeter"]),
    },
]

GAS_SENSORS = [
    {
        "name": "Smart Meter Gas: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulativevol"],
        "ignore_zero_values": True,
    },
    {
        **GAS_PERIOD_VOLUME,
        "name": "Smart Meter Gas: Import Vol (Today)",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["dayvol"],
    },
    {
        **GAS_PERIOD_VOLUME,
        "name": "Smart Meter Gas: Import Vol (This week)",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["weekvol"],
    },
    {
        **GAS_PERIOD_VOLUME,
        "name": "Smart Meter Gas: Import Vol (This month)",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["monthvol"],
    },
    {
        "name": "Smart Meter Gas: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Gas: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Gas: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Gas: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"]["unitrate"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    # Removed June 2022 in IHD software update 1.8.13
    # {
    #   "name": "Smart Meter Gas: Power",
    #   "device_class": SensorDeviceClass.POWER,
    #   "unit_of_measurement": UnitOfPower.KILO_WATT,
    #   "state_class": SensorStateClass.MEASUREMENT,
    #   "icon": "mdi:fire",
    #   "func": lambda js : js['gasmeter']['power']['value'],
    # },
    {
        "name": "Smart Meter Gas: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "meter_interval": MeterInterval.DAY,
        "func": lambda js: round(
            (js["gasmeter"]["energy"]["import"]["price"]["standingcharge"] or 0)
            + (
                (js["gasmeter"]["energy"]["import"]["day"] or 0)
                * (js["gasmeter"]["energy"]["import"]["price"]["unitrate"] or 0)
            ),
            2,
        ),
    },
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Smart Meter sensors."""

    # the config is defaulted to + which happens to mean we will subscribe to all devices
    device_mac = hass.data[DOMAIN][config_entry.entry_id][CONF_DEVICE_ID]
    topic_prefix = hass.data[DOMAIN][config_entry.entry_id][CONF_TOPIC_PREFIX] or DEFAULT_TOPIC_PREFIX
    time_zone_electricity = hass.data[DOMAIN][config_entry.entry_id][
        CONF_TIME_ZONE_ELECTRICITY
    ]
    time_zone_gas = hass.data[DOMAIN][config_entry.entry_id][CONF_TIME_ZONE_GAS]

    deviceUpdateGroups = {}

    @callback
    async def mqtt_message_received(message: ReceiveMessage):
        """Handle received MQTT message."""
        topic = message.topic
        payload = message.payload
        device_id = topic.split("/")[1]
        if device_mac == DEFAULT_DEVICE_ID or device_id == device_mac:
            updateGroups = await async_get_device_groups(
                deviceUpdateGroups,
                async_add_entities,
                device_id,
                time_zone_electricity,
                time_zone_gas,
            )
            _LOGGER.debug("Received message: %s", topic)
            _LOGGER.debug("  Payload: %s", payload)
            for updateGroup in updateGroups:
                updateGroup.process_update(message)

    data_topic = f"{topic_prefix}/#"

    await mqtt.async_subscribe(hass, data_topic, mqtt_message_received, 1)


async def async_get_device_groups(
    deviceUpdateGroups,
    async_add_entities,
    device_id,
    time_zone_electricity,
    time_zone_gas,
):
    # add to update groups if not already there
    if device_id not in deviceUpdateGroups:
        _LOGGER.debug("New device found: %s", device_id)
        groups = [
            HildebrandGlowMqttSensorUpdateGroup(device_id, "STATE", STATE_SENSORS),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id,
                "electricitymeter",
                ELECTRICITY_SENSORS,
                time_zone_electricity,
            ),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id, "gasmeter", GAS_SENSORS, time_zone_gas
            ),
        ]
        async_add_entities(
            [
                sensorEntity
                for updateGroup in groups
                for sensorEntity in updateGroup.all_sensors
            ],
            # True
        )
        deviceUpdateGroups[device_id] = groups

    return deviceUpdateGroups[device_id]


class HildebrandGlowMqttSensorUpdateGroup:
    """Representation of Hildebrand Glow MQTT Meter Sensors that all get updated together."""

    def __init__(
        self, device_id: str, topic_regex: str, meters: Iterable, time_zone: str | None = None
    ) -> None:
        """Initialize the sensor collection."""
        self._topic_regex = re.compile(topic_regex)
        self._sensors = [
            HildebrandGlowMqttSensor(device_id=device_id, time_zone=time_zone, **meter)
            for meter in meters
        ]

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if self._topic_regex.search(topic):
            _LOGGER.debug("Matched on %s", self._topic_regex.pattern)
            parsed_data = json.loads(payload)
            for sensor in self._sensors:
                sensor.process_update(parsed_data)

    @property
    def all_sensors(self) -> Iterable[HildebrandGlowMqttSensor]:
        """Return all meters."""
        return self._sensors


class HildebrandGlowMqttSensor(RestoreSensor):
    """Representation of a room sensor that is updated via MQTT."""

    def __init__(
        self,
        device_id,
        time_zone,
        name,
        icon,
        device_class,
        unit_of_measurement,
        state_class,
        func,
        entity_category=None,
        ignore_zero_values=False,
        error_response_values=None,
        meter_interval: MeterInterval | None = None,
        units_func: Callable[[dict], str] | None = None,
        units_by_name: dict[str, tuple[SensorDeviceClass, str]] | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._time_zone = time_zone
        self._attr_name = name
        self._attr_icon = icon
        if device_class:
            self._attr_device_class = device_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement
        if state_class:
            self._attr_state_class = state_class
        self._attr_unique_id = slugify(device_id + "_" + name)
        self._attr_should_poll = False
        self._func = func
        self._attr_entity_category = entity_category
        self._ignore_zero_values = ignore_zero_values
        self._error_response_values = error_response_values
        self._meter_interval = meter_interval
        self._units_func = units_func
        self._units_by_name = units_by_name
        self._units_reported = False
        self._attr_device_info = DeviceInfo(
            connections={("mac", device_id)},
            manufacturer="Hildebrand Technology Limited",
            model="Glow Smart Meter IHD",
            name=f"Glow Smart Meter {device_id}",
        )
        self._is_incremental_cost = name == "Smart Meter Electricity: Cost (Today)"
        self._cost_accum = None
        self._prev_kwh = None
        self._prev_rate = None
        self._last_reset_utc = None
        self._last_cost_timestamp = None
        self._cost_estimated = False
        self._cost_ready = False
        self._pending_cost_data = None
        self._last_reset_reported = False
        self._attr_native_value = None
        if state_class == SensorStateClass.TOTAL and meter_interval:
            self._attr_last_reset = None
            self._last_reset_reported = True

    async def async_added_to_hass(self) -> None:
        """Restore the accumulator before processing the first MQTT reading."""
        await super().async_added_to_hass()
        if not self._is_incremental_cost:
            return
        last_state = await self.async_get_last_state()
        if last_state:
            attrs = last_state.attributes
            accum = _finite_float(attrs.get("cost_accum"))
            kwh = _finite_float(attrs.get("prev_kwh"))
            rate = _finite_float(attrs.get("prev_rate"))
            reset = _aware_datetime(attrs.get("last_reset_utc"))
            if accum is not None and kwh is not None and kwh >= 0 and rate is not None and reset:
                self._cost_accum = accum
                self._prev_kwh = kwh
                self._prev_rate = rate
                self._last_reset_utc = reset.isoformat()
                self._attr_last_reset = reset
                self._last_cost_timestamp = _aware_datetime(attrs.get("last_cost_timestamp"))
                self._cost_estimated = bool(attrs.get("cost_estimated", False))
                self._attr_native_value = _finite_float(last_state.state)
        self._cost_ready = True
        if self._pending_cost_data is not None:
            pending = self._pending_cost_data
            self._pending_cost_data = None
            self._process_incremental_cost(pending)

    def _process_incremental_cost(self, mqtt_data) -> None:
        """Accrue consumption at the previous observed tariff, in GBP.

        If no usable history exists, seed today's consumption at the current
        rate. This is an estimate: earlier tariff changes cannot be recovered
        from a single MQTT reading. Gaps likewise use the last observed rate.
        """
        if not self._cost_ready:
            self._pending_cost_data = mqtt_data
            return
        try:
            energy = mqtt_data["electricitymeter"]["energy"]["import"]
            price = energy["price"]
            day_value = energy["day"]
            rate_value = price["unitrate"]
            standing_value = price["standingcharge"]
        except (KeyError, TypeError):
            # Retain upstream's missing-field behaviour without advancing history.
            return
        today_kwh = _finite_float(day_value)
        unit_rate = _finite_float(rate_value)
        standing = _finite_float(standing_value)
        try:
            message_dt = self.get_message_datetime(mqtt_data)
        except (ValueError, TypeError, AttributeError):
            return
        if message_dt.tzinfo is None:
            return
        if self._last_cost_timestamp and message_dt <= self._last_cost_timestamp:
            return
        if today_kwh is None or today_kwh < 0 or unit_rate is None or standing is None:
            # Unknown prices are not free electricity. Keep the last good baseline.
            self._attr_native_value = None
            if self.hass is not None:
                self.async_schedule_update_ha_state()
            return
        zone = self._time_zone or (self.hass.config.time_zone if self.hass else "UTC")
        reset = self.determine_last_reset(message_dt, ZoneInfo(zone), MeterInterval.DAY)
        previous_reset = _aware_datetime(self._last_reset_utc)
        if previous_reset and reset < previous_reset:
            return
        if previous_reset != reset or self._cost_accum is None:
            self._cost_accum = today_kwh * unit_rate
            self._cost_estimated = today_kwh > 0
        elif today_kwh < self._prev_kwh:
            # A stale/invalid daily counter must not create a second charge later.
            self._attr_native_value = None
            if self.hass is not None:
                self.async_schedule_update_ha_state()
            return
        else:
            self._cost_accum += (today_kwh - self._prev_kwh) * self._prev_rate
        self._prev_kwh = today_kwh
        self._prev_rate = unit_rate
        self._last_reset_utc = reset.isoformat()
        self._attr_last_reset = reset
        self._last_cost_timestamp = message_dt
        self._attr_native_value = round(standing + self._cost_accum, 2)
        if self.hass is not None:
            self.async_schedule_update_ha_state()

    @staticmethod
    def determine_last_reset(
        message_datetime: datetime, meter_timezone: tzinfo, meter_interval: MeterInterval
    ) -> datetime:
        """Return midnight of the meter's reset interval in UTC."""
        meter_datetime = message_datetime.astimezone(meter_timezone)
        meter_midnight = datetime.combine(
            meter_datetime.date(), time.min, meter_datetime.tzinfo
        )
        if meter_interval == MeterInterval.DAY:
            last_reset = meter_midnight
        elif meter_interval == MeterInterval.WEEK:
            last_reset = meter_midnight - timedelta(days=meter_midnight.weekday())
        elif meter_interval == MeterInterval.MONTH:
            last_reset = meter_midnight.replace(day=1)
        elif meter_interval == MeterInterval.YEAR:
            last_reset = meter_midnight.replace(day=1, month=1)
        return last_reset.astimezone(ZoneInfo("UTC"))

    @staticmethod
    def get_message_datetime(mqtt_data) -> datetime:
        """Return the message timestamp as a datetime."""
        timestamp = (
            mqtt_data.get("timestamp")
            or mqtt_data.get("electricitymeter", {}).get("timestamp")
            or mqtt_data.get("gasmeter", {}).get("timestamp")
        )
        try:
            return datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            raise ValueError("Valid timestamp not present in MQTT data.")

    async def async_added_to_hass(self) -> None:
        """Restore the unit the IHD reported before Home Assistant restarted."""
        await super().async_added_to_hass()
        if not self._units_by_name or self._units_reported:
            return
        last_sensor_data = await self.async_get_last_sensor_data()
        if last_sensor_data is None:
            return
        for device_class, unit in self._units_by_name.values():
            if unit == last_sensor_data.native_unit_of_measurement:
                self._attr_device_class = device_class
                self._attr_native_unit_of_measurement = unit

    def process_update(self, mqtt_data) -> None:
        """Update the state of the sensor."""
        if self._is_incremental_cost:
            self._process_incremental_cost(mqtt_data)
            return
        try:
            new_value = self._func(mqtt_data)
            if self._units_by_name:
                units = self._units_by_name[self._units_func(mqtt_data)]
        except (KeyError, TypeError) as err:
            # A payload without this field, or in a unit this integration does
            # not know, must not break the other sensors or flood the log, so
            # keep the previous state.
            _LOGGER.debug(
                "Skipped update of %s, payload has no usable value: %r",
                self._attr_unique_id,
                err,
            )
            return
        if self._units_by_name:
            self._attr_device_class, self._attr_native_unit_of_measurement = units
            self._units_reported = True
        if self._ignore_zero_values and new_value == 0:
            _LOGGER.debug(
                "Ignored new value of %s on %s.", new_value, self._attr_unique_id
            )
            return
        if self._error_response_values and new_value in self._error_response_values:
            _LOGGER.debug(
                "Received error response value of %s on %s, state unknown.",
                new_value,
                self._attr_unique_id,
            )
            new_value = None
        self._attr_native_value = new_value

        zoneInfo = None
        if self._time_zone:
            zoneInfo = self._time_zone
        elif (self.hass is not None and 
              self.hass.config is not None):
            zoneInfo = self.hass.config.time_zone
            
        if zoneInfo and self._last_reset_reported and self._meter_interval:
            try:
                message_datetime = self.get_message_datetime(mqtt_data)
            except ValueError:
                _LOGGER.debug(
                    "No valid timestamp for %s, keeping the previous last_reset.",
                    self._attr_unique_id,
                )
            else:
                self._attr_last_reset = self.determine_last_reset(
                    message_datetime, ZoneInfo(zoneInfo), self._meter_interval
                )

        if (
            self.hass is not None
        ):  # this is a hack to get around the fact that the entity is not yet initialized at first
            self.async_schedule_update_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {ATTR_DEVICE_ID: self._device_id}
        if self._is_incremental_cost and self._cost_accum is not None:
            attrs.update(
                cost_accum=self._cost_accum,
                prev_kwh=self._prev_kwh,
                prev_rate=self._prev_rate,
                last_reset_utc=self._last_reset_utc,
                last_cost_timestamp=(
                    self._last_cost_timestamp.isoformat() if self._last_cost_timestamp else None
                ),
                cost_estimated=self._cost_estimated,
            )
        return attrs



def _finite_float(value):
    """Accept numeric readings, including zero/negative tariffs, but not NaN/inf."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _aware_datetime(value):
    """Read a persisted timestamp only if it has an explicit timezone."""
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return result if result.tzinfo is not None else None
