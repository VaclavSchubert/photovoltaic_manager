"Constants for custom integration."

from homeassistant.const import Platform

DOMAIN = "photovoltaic_manager"

# Platforms (if your integration has multiple platforms like sensor, switch)
PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 14
MIN_SCAN_INTERVAL = 7
DEFAULT_PLAN_INTERVAL = 3600  # 1 hour


# Required configuration keys
# solax
REAL_PV_PRODUCTION = "sensor.solax_pv_power_total"
HOUSEHOLD_CONSUMPTION = "sensor.solax_house_load"
BATTERY_STATUS = "sensor.solax_battery_capacity"
INVERTER_POWER = "number.solax_export_control_user_limit"
INVERTER_EXPORT_IMPORT = "button.solax_remotecontrol_trigger"
REMOTECONTROL_POWER = "number.solax_remotecontrol_active_power"
REMOTECONTROL_MODE = "select.solax_remotecontrol_power_control"
REMOTECONTROL_DURATION = "number.solax_remotecontrol_autorepeat_duration"

# forecast_solar
PV_PRODUCTION_FORECAST_TODAY = "sensor.power_production_now"
PV_PRODUCTION_FORECAST_TOMORROW = "sensor.power_production_next_24hours"

# cz_energy_spot_prices
SPOT_MARKET_TODAY_ORDER = "sensor.current_spot_electricity_hour_order"
HAS_TOMORROW_SPOT_DATA = "binary_sensor.spot_electricity_has_tomorrow_data"
SPOT_MARKET_TOMORROW_ORDER = "sensor.tomorrow_spot_electricity_hour_order"


CONF_MIN_SOC = "min_soc"  # number input field
CONF_MAX_SOC = "max_soc"  # number input field
CONF_BATTERY_CAPACITY = "battery_capacity"  # number input field
CONF_WEATHER_FORECAST = "weather_forecast"
CONF_AIR_CONDITIONING = "air_conditioning"  # climate to control
CONF_BOILER_HEATING = "boiler_heating"  # switch to control

# Optional configuration
CONF_SECOND_HOME_SERVER = "second_home_server"  # input text field
CONF_SECOND_HOME_API_KEY = "second_home_api_key"  # input text field
CONF_SECOND_HOME_DEVICE_ID = "second_home_device_id"  # input text field
