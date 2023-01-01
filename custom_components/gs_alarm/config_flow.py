"""
Config flow for `gs_alarm` integrarion.
"""

from __future__ import annotations
import logging

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
    SelectSelectorMode,
)
from pyg90alarm import G90Alarm

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("ip_addr", default=False): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handles the config flow for `gs_alarm` integration.
    """
    VERSION = 1

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Handles discovering devices upon user confirmation.
        """
        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(step_id="confirm")

        devices = await self.hass.async_create_task(G90Alarm.discover())
        _LOGGER.debug('Discovered devices: %s', devices)
        # No devices discovered, present form for manual hostname/IP entry
        if not devices:
            return await self.async_step_custom_host(None)

        # Instantiate the integration for discovered devices
        # Need to properly handle the result for multiple devices
        for device in devices:
            res = self.async_create_entry(
                title=DOMAIN, data={'ip_addr': device['host']}
            )
        return res

    async def async_step_user(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Handles the initial step.
        """
        return await self.async_step_confirm(None)

    async def async_step_custom_host(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Handles adding integration with manual hostname/IP specified.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="custom_host", data_schema=STEP_USER_DATA_SCHEMA
            )
        errors = {}

        # Register the integration when hostname/IP is provided
        if not user_input.get('ip_addr', None):
            errors['ip_addr'] = 'ip_addr_required'
        else:
            return self.async_create_entry(title=DOMAIN, data=user_input)

        # Hostname/IP address is required
        return self.async_show_form(
            step_id="custom_host", data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """
        Instantiates options flow handler.
        """
        return OptionsFlowHandler(config_entry)


# pylint:disable=too-few-public-methods
class OptionsFlowHandler(config_entries.OptionsFlow):
    """
    Handle options (configure) flows.
    """
    def __init__(self, config_entry):
        """
        Initialize options flow.
        """
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """
        Manage the options.
        """
        # Attempt to retrieve `G90Alarm()` instance from integration data
        g90_client = (
            self.hass.data[DOMAIN]
            .get(self.config_entry.entry_id, {})
            .get('client', None)
        )

        schema = {
            vol.Required(
                "sms_alert_when_armed",
                default=self.config_entry.options.get(
                    "sms_alert_when_armed", False
                ),
            ): BooleanSelector(),
        }

        # `G90Alarm` instance might be missing, for example if integration has
        # failed to load, not configuration is possible then for
        # enabling/disabling the sensors
        if g90_client:
            # Retrieve all sensors support enabling/disabling
            g90_sensors = await g90_client.get_sensors()
            all_sensors = [
                SelectOptionDict(label=x.name, value=str(x.index))
                for x in g90_sensors
                if x.supports_enable_disable
            ]
            _LOGGER.debug(
                'configure: all sensor entries for selector: %s', all_sensors
            )
            # Determine currently sensors currently disabled, out of those
            # supports altering the state.
            # NOTE: If sensor doesn't support enabling/disabling thru
            # `pyg90alarm` it will not be shown on the form, thus requiring
            # mobile application to be managed
            disabled_sensors = [
                str(x.index) for x in g90_sensors if not x.enabled
            ]
            _LOGGER.debug('configure: disabled sensors: %s', disabled_sensors)
            # Add form element
            schema.update({
                vol.Optional(
                    "disabled_sensors",
                    default=disabled_sensors
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=all_sensors,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            })

        # Present the form back if no user input
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(schema)
            )

        # (Re)create the integration entry, that will fetch the options and
        # adjust its configuration
        return self.async_create_entry(title="", data=user_input)
