
# ================================= Definitions for config_flow ==========================================================

DOMAIN = "photovoltaic_manager"
# Default values
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""

# Configuration keys (keys used in config flow or entry.data)
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Platforms (if your integration has multiple platforms like sensor, switch)
PLATFORMS = ["sensor", "switch"]

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10