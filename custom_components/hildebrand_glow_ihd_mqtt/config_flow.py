"""Config flow for Hildebrand Glow IHD MQTT."""
from collections import OrderedDict
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE_ID,
)

from .const import (
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class HildebrandGlowIHDMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def _show_setup_form(self, errors=None):
        """Show the setup form to the user."""
        errors = {}

        fields = OrderedDict()
        fields[vol.Required(CONF_DEVICE_ID, default='+')] = str

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return await self._show_setup_form()

        unique_id = user_input[CONF_DEVICE_ID]

        await self.async_set_unique_id('{}_{}'.format(DOMAIN, unique_id))
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="",
            data={
                CONF_DEVICE_ID: unique_id,
            })

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     return GardenaSmartSystemOptionsFlowHandler(config_entry)


# class GardenaSmartSystemOptionsFlowHandler(config_entries.OptionsFlow):
#     def __init__(self, config_entry):
#         """Initialize Gardena Smart Sytem options flow."""
#         self.config_entry = config_entry

#     async def async_step_init(self, user_input=None):
#         """Manage the options."""
#         return await self.async_step_user()

#     async def async_step_user(self, user_input=None):
#         """Handle a flow initialized by the user."""
#         errors = {}
#         if user_input is not None:
#             # TODO: Validate options (min, max values)
#             return self.async_create_entry(title="", data=user_input)

#         fields = OrderedDict()
#         fields[vol.Optional(
#             CONF_MOWER_DURATION,
#             default=self.config_entry.options.get(
#                 CONF_MOWER_DURATION, DEFAULT_MOWER_DURATION))] = cv.positive_int
#         fields[vol.Optional(
#             CONF_SMART_IRRIGATION_DURATION,
#             default=self.config_entry.options.get(
#                 CONF_SMART_IRRIGATION_DURATION, DEFAULT_SMART_IRRIGATION_DURATION))] = cv.positive_int
#         fields[vol.Optional(
#             CONF_SMART_WATERING_DURATION,
#             default=self.config_entry.options.get(
#                 CONF_SMART_WATERING_DURATION, DEFAULT_SMART_WATERING_DURATION))] = cv.positive_int

#         return self.async_show_form(step_id="user", data_schema=vol.Schema(fields), errors=errors)

