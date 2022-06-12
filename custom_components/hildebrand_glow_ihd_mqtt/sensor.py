"""Support for hildebrand glow MQTT sensors."""
from __future__ import annotations

import json
import re
import logging
from typing import Iterable
import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA, 
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import (
    CONF_DEVICE_ID,
    ATTR_DEVICE_ID,

    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        # NOTE: WE ABSOLUTELY ASSUME IS THIS IS NOT CONFIGURED, THERES ONLY ONE DEVICE CONNECTED TO MQTT. IF THIS IS NOT THE CASE, BAD THINGS WILL HAPPEN
        vol.Optional(CONF_DEVICE_ID, default='+'): cv.string
    }
)

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

ELECTRICITY_SENSORS = [
  {
    "name": "Smart Meter Electricity: Export",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    #"value_template": "{{ value_json['electricitymeter']['energy']['export']['cumulative'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['export']['cumulative'],
  },
  {
    "name": "Smart Meter Electricity: Import",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    #"value_template": "{% if value_json['electricitymeter']['energy']['import']['cumulative'] == 0 %}\n  {{ states('sensor.smart_meter_electricity_import') }}\n{% else %}\n  {{ value_json['electricitymeter']['energy']['import']['cumulative'] }}\n{% endif %}\n",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['cumulative'],
    "ignore_zero_values": True,
  },
  {
    "name": "Smart Meter Electricity: Import (Today)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['day'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['day'],
  },
  {
    "name": "Smart Meter Electricity: Import (This week)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['week'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['week'],
  },
  {
    "name": "Smart Meter Electricity: Import (This month)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    # "value_template": "{{ value_json['electricitymeter']['energy']['import']['month'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['energy']['import']['month'],
  },
  {
    "name": "Smart Meter Electricity: Import Unit Rate",
    "device_class": SensorDeviceClass.MONETARY,
    "unit_of_measurement": "GBP/kWh",
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['price']['unitrate'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['electricitymeter']['energy']['import']['price']['unitrate'],
  },
  {
    "name": "Smart Meter Electricity: Import Standing Charge",
    "device_class": SensorDeviceClass.MONETARY,
    "unit_of_measurement": "GBP",
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['electricitymeter']['energy']['import']['price']['standingcharge'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['electricitymeter']['energy']['import']['price']['standingcharge'],
  },
  {
    "name": "Smart Meter Electricity: Power",
    "device_class": SensorDeviceClass.POWER,
    "unit_of_measurement": POWER_KILO_WATT,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['electricitymeter']['power']['value'] }}",
    "icon": "mdi:flash",
    "func": lambda js : js['electricitymeter']['power']['value'],
  }
]

GAS_SENSORS = [
  {
    "name": "Smart Meter Gas: Import",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    #"value_template": "{% if value_json['gasmeter']['energy']['import']['cumulative'] == 0 %}\n  {{ states('sensor.smart_meter_gas_import') }}\n{% else %}\n  {{ value_json['gasmeter']['energy']['import']['cumulative'] }}\n{% endif %}\n",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['cumulative'],
    "ignore_zero_values": True,
  },
  {
    "name": "Smart Meter Gas: Import (Today)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['day'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['day']
  },
  {
    "name": "Smart Meter Gas: Import (This week)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['week'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['week']
  },
  {
    "name": "Smart Meter Gas: Import (This month)",
    "device_class": SensorDeviceClass.ENERGY,
    "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['month'] }}",
    "icon": "mdi:fire",
    "func": lambda js : js['gasmeter']['energy']['import']['month']
  },
  {
    "name": "Smart Meter Gas: Import Unit Rate",
    "device_class": SensorDeviceClass.MONETARY,
    "unit_of_measurement": "GBP/kWh",
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['price']['unitrate'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['gasmeter']['energy']['import']['price']['unitrate']
  },
  {
    "name": "Smart Meter Gas: Import Standing Charge",
    "device_class": SensorDeviceClass.MONETARY,
    "unit_of_measurement": "GBP",
    "state_class": SensorStateClass.MEASUREMENT,
    #"value_template": "{{ value_json['gasmeter']['energy']['import']['price']['standingcharge'] }}",
    "icon": "mdi:cash",
    "func": lambda js : js['gasmeter']['energy']['import']['price']['standingcharge']
  },
  {
    "name": "Smart Meter Gas: Power",
    "device_class": SensorDeviceClass.POWER,
    "unit_of_measurement": POWER_KILO_WATT,
    "state_class": SensorStateClass.MEASUREMENT,
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

    # the config is defaulted to + which happens to mean we will subscribe to all devices (note, THERE MUST ONLY BE ONE!)
    device_mac = config.get(CONF_DEVICE_ID).upper()

    # state_sub = await mqtt.async_subscribe(
    #   hass, f"glow/{device_mac}/STATE", 1
    # )
    updateGroups = [
        HildebrandGlowMqttSensorUpdateGroup(device_mac, "electricitymeter", ELECTRICITY_SENSORS),
        HildebrandGlowMqttSensorUpdateGroup(device_mac, "gasmeter", GAS_SENSORS)
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

    data_topic = f"glow/{device_mac}/SENSOR/+"

    await mqtt.async_subscribe(
        hass, data_topic, mqtt_message_received, 1
    ) 

    all_sensor_entities = [sensorEntity for updateGroup in updateGroups for sensorEntity in updateGroup.all_sensors]

    async_add_entities(
        all_sensor_entities
    )

class HildebrandGlowMqttSensorUpdateGroup:
    """Representation of Hildebrand Glow MQTT Meter Sensors that all get updated together."""

    def __init__(self, device_id: str, topic_regex: str, meters: Iterable) -> None:
        """Initialize the sensor collection."""
        self._topic_regex = re.compile(topic_regex)
        self._sensors = [HildebrandGlowMqttSensor(device_id = device_id, **meter) for meter in meters]

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if (self._topic_regex.search(topic)):
            _LOGGER.debug("Matched on %s", self._topic_regex.pattern)
            parsed_data = json.loads(payload)
            for sensor in self._sensors:
                sensor.process_update(parsed_data)

    @property
    def all_sensors(self) -> Iterable[HildebrandGlowMqttSensor]:
        """Return all meters."""
        return self._sensors

class HildebrandGlowMqttSensor(SensorEntity):
    """Representation of a room sensor that is updated via MQTT."""

    def __init__(self, device_id, name, icon, device_class, unit_of_measurement, state_class, func, ignore_zero_values = False) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._ignore_zero_values = ignore_zero_values
        self._attr_name = name
        self._attr_unique_id = slugify(device_id + "_" + name)
        #self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_state_class = state_class
        self._func = func        
        self._attr_device_info = DeviceInfo(
            identifiers={("subscription_mode", device_id)},
            manufacturer="Hildebrand Technology Limited",
            model="Glow Smart Meter IHD",
            name="Glow Smart Meter IHD",
        )
        self._attr_native_value = None

    def process_update(self, mqtt_data) -> None:
        """Update the state of the sensor."""
        new_value = self._func(mqtt_data)
        if (self._ignore_zero_values and new_value == 0):
            _LOGGER.debug("Ignored new value of %s on %s.", new_value, self._attr_unique_id)
            return
        self._attr_native_value = new_value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if (self._device_id == "+"):
          return {}
        return {ATTR_DEVICE_ID: self._device_id}