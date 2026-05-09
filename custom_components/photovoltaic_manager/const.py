"Constants for custom integration."

from homeassistant.const import Platform

DOMAIN = "photovoltaic_manager"
CUSTOM_INTEGRATION_UNIQUE_ID = "Energy Management Integration"

# Platforms (if your integration has multiple platforms like sensor, switch)
PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 7
MIN_SCAN_INTERVAL = 14
DEFAULT_PLAN_INTERVAL = 3600  # 1 hour

# Heater types
COMBI_HEATER = "combi_heater"
ELECTRIC_HEATER = "electric_heater"

# Integration modes
INTEGRATION_MODE_OBSERVE = "observe"
INTEGRATION_MODE_MANAGE = "manage"

# Buy price modes
BUY_PRICE_MODE_FIXED = "fixed"
BUY_PRICE_MODE_SPOT = "spot"

# Second home modes
SECOND_HOME_MODE_VIEW = "view"
SECOND_HOME_MODE_FULL = "full"

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
BATTERY_VOLTAGE_CHARGE = "sensor.solax_battery_voltage_charge"
BATTERY_CURRENT_CHARGE = "number.solax_battery_discharge_max_current"
INVERTER_IMPORT_HISTORY = "sensor.solax_grid_import"
INVERTER_EXPORT_HISTORY = "sensor.solax_grid_export"
EXPORT_CONTROL_USER_LIMIT = "number.solax_export_control_user_limit"

# forecast_solar
PV_PRODUCTION_FORECAST_TODAY = "sensor.power_production_now"
PV_PRODUCTION_FORECAST_TOMORROW = "sensor.power_production_next_24hours"

# cz_energy_spot_prices
SPOT_MARKET_TODAY_ORDER = "sensor.current_spot_electricity_hour_order"
HAS_TOMORROW_SPOT_DATA = "binary_sensor.spot_electricity_has_tomorrow_data"
SPOT_MARKET_TOMORROW_ORDER = "sensor.tomorrow_spot_electricity_hour_order"

# Configuration keys
CONF_INTEGRATION_MODE = "integration_mode"  # select field
CONF_BUY_PRICE_MODE = "buy_price_mode"  # select field
CONF_BUY_DISTRIBUTION_COST = "buy_distribution_cost"  # number input field
CONF_ELECTRICITY_PRICE = "electricity_price"
CONF_MIN_SOC = "min_soc"  # number input field
CONF_MAX_SOC = "max_soc"  # number input field
CONF_BATTERY_CAPACITY = "battery_capacity"  # number input field
CONF_WEATHER_FORECAST = "weather_forecast"
CONF_AIR_CONDITIONING = "air_conditioning"  # climate to control
CONF_HEATER_ENTITY = "heater_entity"  # switch to control
CONF_HEATER_TYPE = "heater_type"  # select combi or electric
CONF_HEATER_VOLUME = "heater_volume"  # number input field
CONF_HEATER_POWER = "heater_power"  # number input field

# Optional configuration
CONF_SECOND_HOME_SERVER = "second_home_server"  # input text field
CONF_SECOND_HOME_API_KEY = "second_home_api_key"  # input text field
CONF_SECOND_HOME_DEVICE_ID = "second_home_device_id"  # input text field
CONF_SECOND_HOME_MODE = "second_home_mode"  # select field
CONF_SECOND_HOME_AVG_POWER = "second_home_avg_power"  # number input field

SECOND_HOME_SENSOR = "sensor.second_household_consumption"
