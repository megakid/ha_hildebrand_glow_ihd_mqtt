from enum import Enum
from typing import Final

DOMAIN: Final = "hildebrand_glow_ihd"
MIN_HA_VERSION = "2024.12"

ATTR_NAME = "name"
ATTR_ACTIVITY = "activity"
ATTR_BATTERY_STATE = "battery_state"
ATTR_RF_LINK_LEVEL = "rf_link_level"
ATTR_RF_LINK_STATE = "rf_link_state"
ATTR_SERIAL = "serial"
ATTR_OPERATING_HOURS = "operating_hours"
ATTR_LAST_ERROR = "last_error"
ATTR_ERROR = "error"
ATTR_STATE = "state"

CONF_TIME_ZONE_ELECTRICITY = "time_zone_electricity"
CONF_TIME_ZONE_GAS = "time_zone_gas"
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_FORCE_UPDATE = "force_update"

DEFAULT_DEVICE_ID = "+"
DEFAULT_TOPIC_PREFIX= "glow"
DEFAULT_FORCE_UPDATE = False

# Meter intervals
class MeterInterval(Enum):
    """Meter intervals."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"