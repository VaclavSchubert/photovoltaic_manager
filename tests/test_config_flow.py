"""Tests for Photovoltaic Manager config flow."""

from __future__ import annotations
from unittest.mock import patch

from custom_components.photovoltaic_manager.const import (
    BUY_PRICE_MODE_FIXED,
    COMBI_HEATER,
    CONF_AIR_CONDITIONING,
    CONF_BATTERY_CAPACITY,
    CONF_BUY_DISTRIBUTION_COST,
    CONF_BUY_PRICE_MODE,
    CONF_ELECTRICITY_PRICE,
    CONF_HEATER_ENTITY,
    CONF_HEATER_POWER,
    CONF_HEATER_TYPE,
    CONF_HEATER_VOLUME,
    CONF_INTEGRATION_MODE,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_SECOND_HOME_API_KEY,
    CONF_SECOND_HOME_AVG_POWER,
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_MODE,
    CONF_SECOND_HOME_SERVER,
    CONF_WEATHER_FORECAST,
    CUSTOM_INTEGRATION_UNIQUE_ID,
    DOMAIN,
    INTEGRATION_MODE_MANAGE,
    INTEGRATION_MODE_OBSERVE,
    INVERTER_POWER,
    REAL_PV_PRODUCTION,
    SECOND_HOME_MODE_FULL,
    SECOND_HOME_MODE_VIEW,
)
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryNotReady

# Test data constants
VALID_PRICE_ARRAY = "[0.1, 0.2, 0.15, 0.18, 0.22, 0.25, 0.28, 0.3, 0.32, 0.3, 0.28, 0.25, 0.23, 0.2, 0.18, 0.15, 0.12, 0.1, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02]"
INVALID_PRICE_ARRAY_SHORT = "[0.1, 0.2, 0.15]"
INVALID_PRICE_ARRAY_WITH_STRING = '[0.1, 0.2, "invalid", 0.18, 0.22, 0.25, 0.28, 0.3, 0.32, 0.3, 0.28, 0.25, 0.23, 0.2, 0.18, 0.15, 0.12, 0.1, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02]'

TEST_USER_INPUT = {
    CONF_INTEGRATION_MODE: INTEGRATION_MODE_OBSERVE,
    CONF_BUY_PRICE_MODE: BUY_PRICE_MODE_FIXED,
    CONF_BUY_DISTRIBUTION_COST: VALID_PRICE_ARRAY,
    CONF_ELECTRICITY_PRICE: VALID_PRICE_ARRAY,
    CONF_MIN_SOC: 20,
    CONF_MAX_SOC: 80,
    CONF_BATTERY_CAPACITY: 10.0,
}

TEST_USER_OUTPUT = {
    CONF_INTEGRATION_MODE: INTEGRATION_MODE_OBSERVE,
    CONF_BUY_PRICE_MODE: BUY_PRICE_MODE_FIXED,
    CONF_BUY_DISTRIBUTION_COST: VALID_PRICE_ARRAY,
    CONF_ELECTRICITY_PRICE: VALID_PRICE_ARRAY,
    CONF_MIN_SOC: 20,
    CONF_MAX_SOC: 80,
    CONF_BATTERY_CAPACITY: 10.0,
    CONF_HEATER_ENTITY: "",
    CONF_AIR_CONDITIONING: "",
}


@pytest.fixture
async def setup_solax_state(hass: HomeAssistant) -> None:
    """Set up Solax state for testing."""
    hass.states.async_set(REAL_PV_PRODUCTION, "100")


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_user_flow_observe_mode(hass: HomeAssistant) -> None:
    """Test successful user flow in observe mode."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "user"

    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=TEST_USER_INPUT
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert result.get("title") == CUSTOM_INTEGRATION_UNIQUE_ID
    assert result.get("data") == TEST_USER_OUTPUT


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_user_flow_manage_mode(hass: HomeAssistant) -> None:
    """Test successful user flow in manage mode."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_INTEGRATION_MODE] = INTEGRATION_MODE_MANAGE

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_battery_settings_min_greater_than_max(
    hass: HomeAssistant,
) -> None:
    """Test invalid battery settings when min SOC is greater than max SOC."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_MIN_SOC] = 90
    user_input[CONF_MAX_SOC] = 20

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_battery_settings"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_battery_settings_min_negative(
    hass: HomeAssistant,
) -> None:
    """Test invalid battery settings when min SOC is negative."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_MIN_SOC] = -10

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_battery_settings"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_battery_settings_max_over_100(
    hass: HomeAssistant,
) -> None:
    """Test invalid battery settings when max SOC is over 100."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_MAX_SOC] = 150

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_battery_settings"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_battery_settings_zero_capacity(
    hass: HomeAssistant,
) -> None:
    """Test invalid battery settings when battery capacity is zero."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_BATTERY_CAPACITY] = 0

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_battery_settings"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_price_array_short(hass: HomeAssistant) -> None:
    """Test invalid price array with insufficient values."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_ELECTRICITY_PRICE] = INVALID_PRICE_ARRAY_SHORT

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_price_array"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_price_array_with_string(hass: HomeAssistant) -> None:
    """Test invalid price array with string values."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_ELECTRICITY_PRICE] = INVALID_PRICE_ARRAY_WITH_STRING

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_price_array"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_distribution_cost_array(hass: HomeAssistant) -> None:
    """Test invalid distribution cost array."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_BUY_DISTRIBUTION_COST] = INVALID_PRICE_ARRAY_SHORT

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_price_array"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_solax_invalid_state_unknown(hass: HomeAssistant) -> None:
    """Test error when Solax state is unknown."""
    hass.states.async_set(REAL_PV_PRODUCTION, "unknown")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=TEST_USER_INPUT
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "solax_invalid_state"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_solax_invalid_state_unavailable(hass: HomeAssistant) -> None:
    """Test error when Solax state is unavailable."""
    hass.states.async_set(REAL_PV_PRODUCTION, "unavailable")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=TEST_USER_INPUT
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "solax_invalid_state"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_solax_reload_unknown(hass: HomeAssistant) -> None:
    """Test error when Solax entity is missing."""
    hass.states.async_set(INVERTER_POWER, "unknown")
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_INTEGRATION_MODE] = INTEGRATION_MODE_MANAGE

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )

    assert result.get("type") == FlowResultType.CREATE_ENTRY

    entry = result.get("result")

    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_valid_heater_configuration(hass: HomeAssistant) -> None:
    """Test valid heater configuration."""
    hass.services.async_register("switch", "turn_off", lambda call: None, schema=None)
    hass.states.async_set("switch.heater", "off")

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_HEATER_ENTITY] = "switch.heater"
    user_input[CONF_HEATER_POWER] = 3000.0
    user_input[CONF_HEATER_VOLUME] = 200
    user_input[CONF_HEATER_TYPE] = COMBI_HEATER

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_heater_incomplete_fields(hass: HomeAssistant) -> None:
    """Test invalid heater configuration with incomplete fields."""
    hass.states.async_set("switch.heater", "off")

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_HEATER_ENTITY] = "switch.heater"
    user_input[CONF_HEATER_POWER] = 3000.0
    # Missing CONF_HEATER_VOLUME and CONF_HEATER_TYPE

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_heater_settings"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_heater_entity_noncontrollable(hass: HomeAssistant) -> None:
    """Test error when heater entity is non-controllable."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_HEATER_ENTITY] = "switch.heater"
    user_input[CONF_HEATER_POWER] = 3000.0
    user_input[CONF_HEATER_VOLUME] = 200
    user_input[CONF_HEATER_TYPE] = COMBI_HEATER

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "appliance_noncontrollable"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_valid_air_conditioning_configuration(hass: HomeAssistant) -> None:
    """Test valid air conditioning configuration."""
    hass.services.async_register(
        "climate", "set_hvac_mode", lambda call: None, schema=None
    )
    hass.states.async_set("weather.forecast", "cloudy", {"temperature": 25})
    hass.states.async_set("climate.ac", "cool")

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_AIR_CONDITIONING] = "climate.ac"
    user_input[CONF_WEATHER_FORECAST] = "weather.forecast"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_air_conditioning_noncontrollable(hass: HomeAssistant) -> None:
    """Test error when AC entity is non-controllable."""
    hass.states.async_set("weather.forecast", "cloudy")

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_AIR_CONDITIONING] = "climate.ac"
    user_input[CONF_WEATHER_FORECAST] = "weather.forecast"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "appliance_noncontrollable"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_weather_entity_unknown_state(hass: HomeAssistant) -> None:
    """Test error when weather entity is in unknown state."""
    hass.states.async_set("climate.ac", "cool")
    hass.services.async_register(
        "climate", "set_hvac_mode", lambda call: None, schema=None
    )

    hass.states.async_set("weather.forecast", "unknown")

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_AIR_CONDITIONING] = "climate.ac"
    user_input[CONF_WEATHER_FORECAST] = "weather.forecast"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "weather_invalid_state"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_weather_entity_missing(hass: HomeAssistant) -> None:
    """Test error when weather entity is missing."""
    hass.states.async_set("climate.ac", "cool")
    hass.services.async_register(
        "climate", "set_hvac_mode", lambda call: None, schema=None
    )

    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_AIR_CONDITIONING] = "climate.ac"
    user_input[CONF_WEATHER_FORECAST] = "weather.missing"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "weather_invalid_state"


@pytest.fixture
def mock_api_test():
    """Mock API test endpoint."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"success": True}
        yield mock_post


@pytest.fixture
def mock_recorder(hass: HomeAssistant):
    """Mock recorder instance."""
    with patch("homeassistant.helpers.recorder.get_instance") as mock_recorder:
        mock_recorder.return_value = hass
        yield mock_recorder


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
@pytest.mark.usefixtures("mock_api_test")
@pytest.mark.usefixtures("mock_recorder")
async def test_valid_second_home_view_mode(hass: HomeAssistant) -> None:
    """Test valid second home in view mode."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_SECOND_HOME_SERVER] = "http://shelly.local"
    user_input[CONF_SECOND_HOME_API_KEY] = "test_key"
    user_input[CONF_SECOND_HOME_DEVICE_ID] = "device123"
    user_input[CONF_SECOND_HOME_MODE] = SECOND_HOME_MODE_VIEW

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
@pytest.mark.usefixtures("mock_api_test")
@pytest.mark.usefixtures("mock_recorder")
async def test_valid_second_home_full_mode(hass: HomeAssistant) -> None:
    """Test valid second home in full mode with average power."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_SECOND_HOME_SERVER] = "http://shelly.local"
    user_input[CONF_SECOND_HOME_API_KEY] = "test_key"
    user_input[CONF_SECOND_HOME_DEVICE_ID] = "device123"
    user_input[CONF_SECOND_HOME_MODE] = SECOND_HOME_MODE_FULL
    user_input[CONF_SECOND_HOME_AVG_POWER] = 1000.0

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_invalid_second_home_incomplete_fields(
    hass: HomeAssistant,
) -> None:
    """Test invalid second home with incomplete fields."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_SECOND_HOME_SERVER] = "http://shelly.local"
    user_input[CONF_SECOND_HOME_API_KEY] = "test_key"
    # Missing CONF_SECOND_HOME_DEVICE_ID and CONF_SECOND_HOME_MODE

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "invalid_auth"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_second_home_full_mode_missing_avg_power(
    hass: HomeAssistant,
) -> None:
    """Test error when second home full mode is missing average power."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_SECOND_HOME_SERVER] = "http://shelly.local"
    user_input[CONF_SECOND_HOME_API_KEY] = "test_key"
    user_input[CONF_SECOND_HOME_DEVICE_ID] = "device123"
    user_input[CONF_SECOND_HOME_MODE] = SECOND_HOME_MODE_FULL

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "second_home_mode_invalid"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_second_home_full_mode_negative_avg_power(
    hass: HomeAssistant,
) -> None:
    """Test error when second home full mode has negative average power."""
    user_input = TEST_USER_INPUT.copy()
    user_input[CONF_SECOND_HOME_SERVER] = "http://shelly.local"
    user_input[CONF_SECOND_HOME_API_KEY] = "test_key"
    user_input[CONF_SECOND_HOME_DEVICE_ID] = "device123"
    user_input[CONF_SECOND_HOME_MODE] = SECOND_HOME_MODE_FULL
    user_input[CONF_SECOND_HOME_AVG_POWER] = -1

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=user_input
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors")["base"] == "second_home_mode_invalid"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_duplicate_entry_abort(hass: HomeAssistant) -> None:
    """Test that duplicate entries are prevented."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=TEST_USER_INPUT
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result.get("flow_id"), user_input=TEST_USER_INPUT
    )
    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "already_configured"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("setup_solax_state")
async def test_config_flow_form_initial_state(hass: HomeAssistant) -> None:
    """Test the form is displayed with correct initial state."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "user"
    assert "data_schema" in result
