"""Config flow for Integration 101 Template integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import (
    CONF_APPLIANCES_TO_CONTROL,
    CONF_BATTERY_CAPACITY,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_SECOND_HOME_API_KEY,
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_SERVER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO: dropdown has entities with triggerable options only

    # TODO: shelly request returns 200 ok

    # TODO: solax remotecontrol is in grid control mode

    # TODO: solax entities are available

    return {"title": "Energy Management Integration"}


class ManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Example Integration."""

    VERSION = 1
    _input_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Called when you initiate adding an integration via the UI
        errors: dict[str, str] = {}

        if user_input is not None:
            # The form has been filled in and submitted, so process the data provided.
            try:
                # Validate that the setup data is valid and if not handle errors.
                # The errors["base"] values match the values in your strings.json and translation files.
                info = await validate_input(self.hass, user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if "base" not in errors:
                # Validation was successful, so create a unique id for this instance of your integration
                # and create the config entry.
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_MIN_SOC): vol.Coerce(int),
                vol.Required(CONF_MAX_SOC): vol.Coerce(int),
                vol.Required(CONF_BATTERY_CAPACITY): vol.Coerce(float),
                vol.Required(CONF_APPLIANCES_TO_CONTROL): selector(
                    {
                        "entity": {
                            "domain": ["switch", "relay", "climate"],
                            "multiple": True,
                        }
                    }
                ),
                vol.Optional(CONF_SECOND_HOME_SERVER): cv.string,
                vol.Optional(CONF_SECOND_HOME_API_KEY): cv.string,
                vol.Optional(CONF_SECOND_HOME_DEVICE_ID): cv.string,
            }
        )

        # Show initial form.
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to reconfigure a config entry."""
        # This methid displays a reconfigure option in the integration and is
        # different to options.
        # It can be used to reconfigure any of the data submitted when first installed.
        # This is optional and can be removed if you do not want to allow reconfiguration.
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if config_entry is None:
            raise Exception

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            # TODO: create exceptions
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    config_entry,
                    unique_id=config_entry.unique_id,
                    data={**config_entry.data, **user_input},
                    reason="reconfigure_successful",
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MIN_SOC,
                    default=config_entry.data.get(CONF_MIN_SOC, 20),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_MAX_SOC, default=config_entry.data.get(CONF_MAX_SOC, 80)
                ): vol.Coerce(int),
                vol.Required(
                    CONF_BATTERY_CAPACITY,
                    default=config_entry.data.get(CONF_BATTERY_CAPACITY, 5.0),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_APPLIANCES_TO_CONTROL,
                    default=config_entry.data.get(CONF_APPLIANCES_TO_CONTROL, []),
                ): selector(
                    {
                        "entity": {
                            "domain": ["switch", "relay", "climate"],
                            "multiple": True,
                        }
                    }
                ),
                vol.Optional(
                    CONF_SECOND_HOME_SERVER,
                    default=config_entry.data.get(CONF_SECOND_HOME_SERVER, ""),
                ): cv.string,
                vol.Optional(
                    CONF_SECOND_HOME_API_KEY,
                    default=config_entry.data.get(CONF_SECOND_HOME_API_KEY, ""),
                ): cv.string,
                vol.Optional(
                    CONF_SECOND_HOME_DEVICE_ID,
                    default=config_entry.data.get(CONF_SECOND_HOME_DEVICE_ID, ""),
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
