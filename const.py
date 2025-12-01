"Constants for custom integration."

from homeassistant.const import Platform

DOMAIN = "photovoltaic_manager"

# Platforms (if your integration has multiple platforms like sensor, switch)
PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 14
MIN_SCAN_INTERVAL = 7
DEFAULT_PLAN_INTERVAL = 3600  # 1 hour


# Required configuration keys
CONF_REAL_PV_PRODUCTION = "real_pv_production"  # Statistika reálné výroby PV
CONF_PV_PRODUCTION_FORECAST_TODAY = (
    "pv_production_forecast_today"  # Statistika předpovědi dnešní výroby PV
)
CONF_SPOT_MARKET_PRICE_TODAY = "spot_market_price_today"  # Dnešní spotový trh elektřiny
CONF_HOUSEHOLD_CONSUMPTION = "household_consumption"  # Statistika spotřeby v domácnosti
CONF_INVERTER_EXPORT = "inverter_export"  # Kontrola exportu střídače
CONF_INVERTER_IMPORT = "inverter_import"  # Kontrola importu střídače
CONF_CONSUMPTION_FORECAST_TOMORROW = (
    "consumption_forecast_tomorrow"  # Předpověď spotřeby dalšího dne
)

# Optional configuration key
CONF_SECOND_HOME_SERVER = "second_home_server"
CONF_SECOND_HOME_API_KEY = (
    "second_home_api_key"  # Volitelné: real-time spotřeba druhé domácnosti
)
CONF_SECOND_HOME_DEVICE_ID = "second_home_device_id"
