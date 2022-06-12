from itertools import cycle, islice
from typing import Final

DOMAIN: Final = "hildebrand_glow_ihd_mqtt"

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

CONF_OFFPEAK_START: Final = "offpeak_start"
CONF_OFFPEAK_END: Final = "offpeak_end"

CONF_OFFPEAK_START_DEFAULT: Final = "23:30"
CONF_OFFPEAK_END_DEFAULT: Final = "05:30"

# a hardcoded array of time strings in HH:mm every 30 mins for 24 hours
INTELLIGENT_MINS_PAST_HOURS: Final = [0, 30]
INTELLIGENT_24HR_TIMES: Final = [f"{hour:02}:{mins:02}" for hour in range(24) for mins in INTELLIGENT_MINS_PAST_HOURS]
INTELLIGENT_CHARGE_TIMES: Final = [f"{hour:02}:{mins:02}" for hour in range(4, 12) for mins in INTELLIGENT_MINS_PAST_HOURS][:-1]
INTELLIGENT_SOC_OPTIONS: Final = list(range(10, 105, 5))
