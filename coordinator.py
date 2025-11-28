"""Integration 101 Template integration using DataUpdateCoordinator."""

from dataclasses import dataclass
from datetime import timedelta
import logging

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SECOND_HOME_API_KEY,
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_SERVER,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .sensor import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class APIData:
    """Class to hold api data."""

    controller_name: str
    device: Device


class SecondHouseholdCoordinator(DataUpdateCoordinator):
    """Coordinator to periodically query the Shelly API about energy consumption in the second household."""

    data: APIData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_SECOND_HOME_SERVER]
        self.api_key = config_entry.data[CONF_SECOND_HOME_API_KEY]
        self.device_id = config_entry.data[CONF_SECOND_HOME_DEVICE_ID]

        self.url = f"https://{self.host}/v2/devices/api/get?auth_key={self.api_key}"
        self.payload = {"ids": [self.device_id], "select": ["status"]}
        self.headers = {"Content-Type": "application/json"}

        # set variables from options.  You need a default here incase options have not been set
        self.poll_interval = MIN_SCAN_INTERVAL

        # Initialise DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            # Method to call on every update interval.
            update_method=self.async_update_data,
            # Polling interval. Will only be polled if there are subscribers.
            # Using config option here but you can just use a value.
            update_interval=timedelta(seconds=self.poll_interval),
        )

    async def async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            response = await self.hass.async_add_executor_job(
                self.send_request, self.url, self.payload, self.headers
            )
            _LOGGER.warning(response.json())
        except Exception as err:
            # This will show entities as unavailable by raising UpdateFailed exception
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        # What is returned here is stored in self.data by the DataUpdateCoordinator
        return "Second household Coordinator", response.json()

    def send_request(self, url, payload, headers):
        """Send request."""
        return requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=3,
        )
