"""Config flow for Integration 101 Template integration."""

from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, recorder
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import (
    COMBI_HEATER,
    ELETRIC_HEATER,
    CONF_AIR_CONDITIONING,
    CONF_BATTERY_CAPACITY,
    CONF_ELECTRICITY_PRICE,
    CONF_HEATER_ENTITY,
    CONF_HEATER_POWER,
    CONF_HEATER_TYPE,
    CONF_HEATER_VOLUME,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_SECOND_HOME_API_KEY,
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_SERVER,
    CONF_WEATHER_FORECAST,
    DOMAIN,
    REAL_PV_PRODUCTION,
)

_LOGGER = logging.getLogger(__name__)


def _validate_shelly(url, payload, headers):
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise CannotConnect from e


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    heater_fields = (
        CONF_HEATER_ENTITY,
        CONF_HEATER_POWER,
        CONF_HEATER_VOLUME,
        CONF_HEATER_TYPE,
    )

    heater_filled = [bool(data.get(f)) for f in heater_fields]

    if data[CONF_MIN_SOC] >= data[CONF_MAX_SOC]:
        raise InvalidBatterySettings
    if data[CONF_MIN_SOC] < 0 or data[CONF_MAX_SOC] > 100:
        raise InvalidBatterySettings
    if data[CONF_BATTERY_CAPACITY] <= 0:
        raise InvalidBatterySettings

    try:
        domain, _ = data[CONF_HEATER_ENTITY].split(".", 1)

        await hass.services.async_call(
            domain,
            "turn_off",
            {"entity_id": data[CONF_HEATER_ENTITY]},
            blocking=True,
        )
        if any(heater_filled) and not all(heater_filled):
            raise InvalidHeaterSettings
    except KeyError:
        data[CONF_HEATER_ENTITY] = ""
    except InvalidHeaterSettings:
        raise InvalidHeaterSettings from InvalidHeaterSettings
    except Exception:  # noqa: BLE001
        raise ApplianceNoncontrollable from Exception

    try:
        domain, _ = data[CONF_AIR_CONDITIONING].split(".", 1)

        await hass.services.async_call(
            domain,
            "set_hvac_mode",
            {"entity_id": data[CONF_AIR_CONDITIONING], "value": "off"},
            blocking=True,
        )
    except KeyError:
        data[CONF_AIR_CONDITIONING] = ""
    except Exception:  # noqa: BLE001
        raise ApplianceNoncontrollable from Exception

    shelly_fields = (
        CONF_SECOND_HOME_API_KEY,
        CONF_SECOND_HOME_DEVICE_ID,
        CONF_SECOND_HOME_SERVER,
    )

    shelly_filled = [bool(data.get(f)) for f in shelly_fields]

    if any(shelly_filled) and not all(shelly_filled):
        raise InvalidAuth
    if all(shelly_filled):
        url = f"{data[CONF_SECOND_HOME_SERVER]}/v2/devices/api/get?auth_key={data[CONF_SECOND_HOME_API_KEY]}"
        payload = {"ids": [data[CONF_SECOND_HOME_DEVICE_ID]], "select": ["status"]}
        headers = {"Content-Type": "application/json"}
        _ = await recorder.get_instance(hass).async_add_executor_job(
            _validate_shelly, url, payload, headers
        )

    # DEBUG: validate Solax entities exist and are available
    solax_state = hass.states.get(REAL_PV_PRODUCTION)
    if solax_state is None or solax_state.state in ("unknown", "unavailable"):
        raise SolaxInvalidState

    weather = hass.states.get(data[CONF_WEATHER_FORECAST])
    if (
        weather is None
        or weather.state in ("unknown", "unavailable")
        or not weather.attributes
    ):
        raise WeatherInvalidState

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
            except SolaxInvalidState:
                errors["base"] = "solax_invalid_state"
            except WeatherInvalidState:
                errors["base"] = "weather_invalid_state"
            except ApplianceNoncontrollable:
                errors["base"] = "appliance_noncontrollable"
            except InvalidBatterySettings:
                errors["base"] = "invalid_battery_settings"
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
                vol.Required(CONF_ELECTRICITY_PRICE): cv.string,
                vol.Required(CONF_MIN_SOC): vol.Coerce(int),
                vol.Required(CONF_MAX_SOC): vol.Coerce(int),
                vol.Required(CONF_BATTERY_CAPACITY): vol.Coerce(float),
                vol.Required(CONF_WEATHER_FORECAST): selector(
                    {
                        "entity": {
                            "domain": ["weather"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(CONF_AIR_CONDITIONING): selector(
                    {
                        "entity": {
                            "domain": ["climate"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(CONF_HEATER_ENTITY): selector(
                    {
                        "entity": {
                            "domain": ["switch"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(CONF_HEATER_POWER): vol.Coerce(float),
                vol.Optional(CONF_HEATER_VOLUME): vol.Coerce(int),
                vol.Optional(CONF_HEATER_TYPE): selector(
                    {
                        "select": {
                            "options": [COMBI_HEATER, ELETRIC_HEATER],
                            "multiple": False,
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
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except SolaxInvalidState:
                errors["base"] = "solax_invalid_state"
            except WeatherInvalidState:
                errors["base"] = "weather_invalid_state"
            except ApplianceNoncontrollable:
                errors["base"] = "appliance_noncontrollable"
            except InvalidBatterySettings:
                errors["base"] = "invalid_battery_settings"
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
                    CONF_ELECTRICITY_PRICE,
                    default=config_entry.data.get(CONF_ELECTRICITY_PRICE, ""),
                ): cv.string,
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
                    CONF_WEATHER_FORECAST,
                    default=config_entry.data.get(CONF_WEATHER_FORECAST, ""),
                ): selector(
                    {
                        "entity": {
                            "domain": ["weather"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(
                    CONF_AIR_CONDITIONING,
                ): selector(
                    {
                        "entity": {
                            "domain": ["climate"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(
                    CONF_HEATER_ENTITY,
                ): selector(
                    {
                        "entity": {
                            "domain": ["switch"],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(CONF_HEATER_POWER): vol.Coerce(float),
                vol.Optional(CONF_HEATER_VOLUME): vol.Coerce(int),
                vol.Optional(CONF_HEATER_TYPE): selector(
                    {
                        "select": {
                            "options": [COMBI_HEATER, ELETRIC_HEATER],
                            "multiple": False,
                        }
                    }
                ),
                vol.Optional(
                    CONF_SECOND_HOME_SERVER,
                ): cv.string,
                vol.Optional(
                    CONF_SECOND_HOME_API_KEY,
                ): cv.string,
                vol.Optional(
                    CONF_SECOND_HOME_DEVICE_ID,
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


class SolaxInvalidState(HomeAssistantError):
    """Error to indicate solax entity is in invalid state."""


class WeatherInvalidState(HomeAssistantError):
    """Error to indicate weather entity is in invalid state."""


class ApplianceNoncontrollable(HomeAssistantError):
    """Error to indicate appliance is non-controllable."""


class InvalidBatterySettings(HomeAssistantError):
    """Error to indicate battery is setup incorrectly."""


class InvalidHeaterSettings(HomeAssistantError):
    """Error to indicate heater is setup incorrectly."""
