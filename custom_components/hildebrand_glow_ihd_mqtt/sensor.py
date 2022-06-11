"""Support for hildebrand glow MQTT sensors."""
from __future__ import annotations

import json
import re
import logging
from typing import Iterable
import itertools
import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    CONF_DEVICE_ID,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DEVICE_ID): cv.string
    }
)

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

ELECTRICITY_SENSORS = [
  {
    "name": "Smart Meter Electricity: Export",
    "unique_id": "glow_ihd_electricity_export",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "total_increasing",
    #"value_template": "{{ value_json['electricitymeter']['energy']['export']['cumulative'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['export']['cumulative'],
  },
  {
    "name": "Smart Meter Electricity: Import",
    "unique_id": "glow_ihd_electricity_import",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "total_increasing",
    #"value_template": "{% if value_json['electricitymeter']['energy']['import']['cumulative'] == 0 %}\n  {{ states('sensor.smart_meter_electricity_import') }}\n{% else %}\n  {{ value_json['electricitymeter']['energy']['import']['cumulative'] }}\n{% endif %}\n",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['cumulative'],
  },
  {
    "name": "Smart Meter Electricity: Import (Today)",
    "unique_id": "glow_ihd_electricity_import_day",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['day'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['day'],
  },
  {
    "name": "Smart Meter Electricity: Import (This week)",
    "unique_id": "glow_ihd_electricity_import_week",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['week'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['week'],
  },
  {
    "name": "Smart Meter Electricity: Import (This month)",
    "unique_id": "glow_ihd_electricity_import_month",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    # "value_template": "{{ value_json['electricitymeter']['energy']['import']['month'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['month'],
  },
  {
    "name": "Smart Meter Electricity: Import Unit Rate",
    "unique_id": "glow_ihd_electricity_import_unit_rate",
    "device_class": "monetary",
    "unit_of_measurement": "GBP/kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['price']['unitrate'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['electricitymeter']['energy']['import']['price']['unitrate'],
  },
  {
    "name": "Smart Meter Electricity: Import Standing Charge",
    "unique_id": "glow_ihd_electricity_import_standing_charge",
    "device_class": "monetary",
    "unit_of_measurement": "GBP",
    "state_class": "measurement",
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['price']['standingcharge'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['electricitymeter']['energy']['import']['price']['standingcharge'],
  },
  {
    "name": "Smart Meter Electricity: Power",
    "unique_id": "glow_ihd_electricity_power",
    "device_class": "power",
    "unit_of_measurement": "kW",
    "state_class": "measurement",
    #"value_template": "{{ value_json['electricitymeter']['power']['value'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['power']['value'],
  }
]

GAS_SENSORS = [
  {
    "name": "Smart Meter Gas: Import",
    "unique_id": "glow_ihd_gas_import",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "total_increasing",
    #"value_template": "{% if value_json['gasmeter']['energy']['import']['cumulative'] == 0 %}\n  {{ states('sensor.smart_meter_gas_import') }}\n{% else %}\n  {{ value_json['gasmeter']['energy']['import']['cumulative'] }}\n{% endif %}\n",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['cumulative']
  },
  {
    "name": "Smart Meter Gas: Import (Today)",
    "unique_id": "glow_ihd_gas_import_day",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['day'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['day']
  },
  {
    "name": "Smart Meter Gas: Import (This week)",
    "unique_id": "glow_ihd_gas_import_week",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['week'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['week']
  },
  {
    "name": "Smart Meter Gas: Import (This month)",
    "unique_id": "glow_ihd_gas_import_month",
    "device_class": "energy",
    "unit_of_measurement": "kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['month'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['month']
  },
  {
    "name": "Smart Meter Gas: Import Unit Rate",
    "unique_id": "glow_ihd_gas_import_unit_rate",
    "device_class": "monetary",
    "unit_of_measurement": "GBP/kWh",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['price']['unitrate'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['gasmeter']['energy']['import']['price']['unitrate']
  },
  {
    "name": "Smart Meter Gas: Import Standing Charge",
    "unique_id": "glow_ihd_gas_import_standing_charge",
    "device_class": "monetary",
    "unit_of_measurement": "GBP",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['price']['standingcharge'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['gasmeter']['energy']['import']['price']['standingcharge']
  },
  {
    "name": "Smart Meter Gas: Power",
    "unique_id": "glow_ihd_gas_power",
    "device_class": "power",
    "unit_of_measurement": "kW",
    "state_class": "measurement",
    #"value_template": "{{ value_json['gasmeter']['power']['value'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['power']['value']
  }
]

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:

    updateGroups = [
        HildebrandGlowMqttSensorUpdateGroup("electricitymeter", ELECTRICITY_SENSORS),
        HildebrandGlowMqttSensorUpdateGroup("gasmeter", GAS_SENSORS)
    ]

    @callback
    def mqtt_message_received(message: ReceiveMessage) -> None:
        """Handle received MQTT message."""
        topic = message.topic
        payload = message.payload
        _LOGGER.debug("Received message: %s", topic)
        _LOGGER.debug("  Payload: %s", payload)
        for updateGroup in updateGroups:
            updateGroup.process_update(message)


    device_mac = config.get(CONF_DEVICE_ID).upper()
    topic = f"glow/{device_mac}/SENSOR/+"

    await mqtt.async_subscribe(
        hass, topic, mqtt_message_received, 1
    ) 

    all_sensor_entities = [sensorEntity for updateGroup in updateGroups for sensorEntity in updateGroup.all_sensors]

    async_add_entities(
        all_sensor_entities
    )

class HildebrandGlowMqttSensorUpdateGroup:
    """Representation of Hildebrand Glow MQTT Meter Sensors that all get updated together."""

    def __init__(self, topicRegex: str, meters: Iterable) -> None:
        """Initialize the sensor collection."""
        self._topicRegex = re.compile(topicRegex)
        self._sensors = {}
        for meter in meters:
            self._sensors[meter['unique_id']] = HildebrandGlowMqttSensor(**meter)

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if (self._topicRegex.search(topic)):
            _LOGGER.debug("Matched on %s", self._topicRegex.pattern)
            parsed_data = json.loads(payload)
            for sensor in self._sensors.values():
                sensor.process_update(parsed_data)

    @property
    def all_sensors(self) -> Iterable[HildebrandGlowMqttSensor]:
        """Return all meters."""
        return self._sensors.values()

class HildebrandGlowMqttSensor(SensorEntity):
    """Representation of a room sensor that is updated via MQTT."""

    def __init__(self, unique_id, name, icon, unit_of_measurement, state_class, func, device_class = None):
        """Initialize the sensor."""
        self._unique_id = unique_id
        self._name = name
        self._icon = icon
        self._device_class = device_class
        self._unit_of_measurement = unit_of_measurement
        self._state_class = state_class
        self._func = func
        
        self._value = None
        self._updated = None

    def process_update(self, mqtt_data) -> None:
        """Update the state of the sensor."""
        self._value = self._func(mqtt_data)
        self._updated = dt.utcnow()

        self.async_write_ha_state()

    # async def async_added_to_hass(self):
    #     """Sensor added to hass."""

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def native_value(self):
        """Return the current room of the entity."""
        return self._value

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self._state_class

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return None #self._icon