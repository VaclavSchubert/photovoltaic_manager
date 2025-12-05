"""Coordinators responsible for periodic updates."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Literal
import zoneinfo

import numpy as np
import pulp
import requests

from homeassistant.components.recorder import statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt

from .const import (
    CONF_SECOND_HOME_API_KEY,
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_SERVER,
    DEFAULT_PLAN_INTERVAL,
    DOMAIN,
    HAS_TOMORROW_SPOT_DATA,
    HOUSEHOLD_CONSUMPTION,
    MIN_SCAN_INTERVAL,
    PV_PRODUCTION_FORECAST_TOMORROW,
    SPOT_MARKET_TODAY_ORDER,
    SPOT_MARKET_TOMORROW_ORDER,
)

_LOGGER = logging.getLogger(__name__)

SEASONS_BY_MONTH = [
    "winter",
    "winter",
    "spring",
    "spring",
    "spring",
    "summer",
    "summer",
    "summer",
    "autumn",
    "autumn",
    "autumn",
    "winter",
]


# TODO: change the Device class below to match the data structure returned by api
@dataclass
class Device:
    """API device."""

    device_id: int
    name: str
    state: float


@dataclass
class APIData:
    """Class to hold api data."""

    controller_name: str
    device: Device


@dataclass
class EnergyData:
    """Class to hold energy data."""

    controller_name: str
    houseload_prediction: float
    corrected_forecast: float


class SecondHouseholdCoordinator(DataUpdateCoordinator):
    """Coordinator to periodically query the Shelly API about energy consumption in the second household."""

    data: APIData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_SECOND_HOME_SERVER]
        self.api_key = config_entry.data[CONF_SECOND_HOME_API_KEY]
        self.device_id = config_entry.data[CONF_SECOND_HOME_DEVICE_ID]

        self.url = f"{self.host}/v2/devices/api/get?auth_key={self.api_key}"
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
        except Exception as err:
            # This will show entities as unavailable by raising UpdateFailed exception
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        # TODO: process response to match your Device structure
        # What is returned here is stored in self.data by the DataUpdateCoordinator
        res = response.json()[0]
        device = Device(
            device_id=res["id"],
            name=res["code"],
            state=res["status"]["em:0"]["total_act_power"],
        )
        return APIData("Second household Coordinator", device)

    def send_request(self, url, payload, headers):
        """Send request."""
        return requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=3,
        )


class EnergyManagementCoordinator(DataUpdateCoordinator):
    """Coordinator to periodically calculate and correct consumption in household."""

    data: EnergyData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        self.hass = hass
        self.today_order_entity = SPOT_MARKET_TODAY_ORDER
        self.has_tomorrow_entity = HAS_TOMORROW_SPOT_DATA
        self.tomorrow_order_entity = SPOT_MARKET_TOMORROW_ORDER
        self.forecast_pv_production_entity = PV_PRODUCTION_FORECAST_TOMORROW
        self.house_load_entity = HOUSEHOLD_CONSUMPTION

        # set variables from options.  You need a default here incase options have not been set
        self.poll_interval = DEFAULT_PLAN_INTERVAL

        today_state = self.hass.states.get(self.today_order_entity)
        if today_state is None:
            raise UpdateFailed(f"Entity {self.today_order_entity} not found")
        today_order = today_state.attributes

        has_tomorrow_state = self.hass.states.get(self.has_tomorrow_entity)
        if has_tomorrow_state is None:
            raise UpdateFailed(f"Entity {self.has_tomorrow_entity} not found")
        has_tomorrow = has_tomorrow_state.state == "on"

        tomorrow_state = self.hass.states.get(self.tomorrow_order_entity)
        if tomorrow_state is None:
            raise UpdateFailed(f"Entity {self.tomorrow_order_entity} not found")
        tomorrow_order = tomorrow_state.attributes
        self.spot_array = SpotPriceArray(
            today_order,
            tomorrow_order,
            has_tomorrow,
            dt.now(zoneinfo.ZoneInfo(self.hass.config.time_zone)).hour,
        )

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

    async def update_predictions(
        self, hass: HomeAssistant, curve, new_input, season, hour
    ):
        """Update stored predictions."""
        store = hass.data[curve]["store"]
        hass.data[curve]["data"][season]["values"][hour] = (
            hass.data[curve]["data"][season]["values"][hour]
            * hass.data[curve]["data"][season]["count"]
            + new_input
        ) / (hass.data[curve]["data"][season]["count"] + 1)
        hass.data[curve]["data"][season]["hours"] += 1
        if hass.data[curve]["data"][season]["hours"] >= 24:
            hass.data[curve]["data"][season]["count"] += 1
            hass.data[curve]["data"][season]["hours"] = 0
        await store.async_save(hass.data[curve]["data"])

    async def async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        datetime = dt.now(zoneinfo.ZoneInfo(self.hass.config.time_zone))
        month = datetime.month - 1
        hour = datetime.hour - 1

        H = 24  # hours
        solar_correction = self.hass.data["pv_production_correction"]["data"][
            SEASONS_BY_MONTH[month]
        ]["values"]  # solar forecast W each hour

        # TODO: get from significant states? self.forecast_pv_production_entity, need 24 len array from forecast
        solar = list(
            np.array([]) - np.array(solar_correction[hour:] + solar_correction[:hour])
        )  # rotate to start from current hour
        load = self.hass.data["house_load_predictor"]["data"][SEASONS_BY_MONTH[month]][
            "values"
        ]  # load forecast W each hour

        types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {
            "mean"
        }

        last_hour_load = await recorder.get_instance(self.hass).async_add_executor_job(
            statistics.get_last_statistics,
            self.hass,
            1,
            self.house_load_entity,
            False,
            types,
        )
        last_hour_load = list(last_hour_load.values())[0][0].get("mean")
        await self.update_predictions(
            self.hass,
            "house_load_predictor",
            last_hour_load,
            SEASONS_BY_MONTH[month],
            hour - 1 % 24,
        )

        diff = last_hour_load - load[hour - 1 % 24]
        load[hour] += diff

        last_hour_production = await recorder.get_instance(
            self.hass
        ).async_add_executor_job(
            statistics.get_last_statistics,
            self.hass,
            1,
            self.forecast_pv_production_entity,
            False,
            types,
        )
        last_hour_production = solar[-1] - list(last_hour_production.values())[0][
            0
        ].get("mean")
        await self.update_predictions(
            self.hass,
            "pv_production_correction",
            last_hour_load,
            SEASONS_BY_MONTH[month],
            hour - 1 % 24,
        )

        diff = last_hour_production - solar[hour - 1 % 24]
        solar[0] += diff

        var_solar = solar  # rotate to start from current hour
        var_load = load[hour:] + load[:hour]  # rotate to start from current hour

        buy_price = [
            6.7,
            6.7,
            6.7,
            6.7,
            4.0,
            4.0,
            4.0,
            4.0,
            6.7,
            6.7,
            6.7,
            6.7,
            6.7,
            6.7,
            4.0,
            4.0,
            4.0,
            4.0,
            6.7,
            6.7,
            6.7,
            6.7,
            6.7,
            6.7,
            6.7,
        ]  # price to import from grid

        today_state = self.hass.states.get(self.today_order_entity)
        if today_state is None:
            raise UpdateFailed(f"Entity {self.today_order_entity} not found")
        today_order = today_state.attributes

        has_tomorrow_state = self.hass.states.get(self.has_tomorrow_entity)
        if has_tomorrow_state is None:
            raise UpdateFailed(f"Entity {self.has_tomorrow_entity} not found")
        has_tomorrow = has_tomorrow_state.state == "on"

        tomorrow_state = self.hass.states.get(self.tomorrow_order_entity)
        if tomorrow_state is None:
            raise UpdateFailed(f"Entity {self.tomorrow_order_entity} not found")
        tomorrow_order = tomorrow_state.attributes

        self.spot_array.build_array(today_order, tomorrow_order, has_tomorrow, hour)
        sell_price = list(self.spot_array.prices)  # price to export to grid

        # Battery parameters
        bat_capacity = 10.0  # kWh
        bat_power = 3.0  # max charge/discharge kW
        eff_charge = 0.95
        eff_discharge = 0.95
        soc_initial = 5.0  # kWh
        soc_final_target = 5.0  # optional

        # TODO: replace template with actual optimisation model
        m = pulp.LpProblem("EnergyManagement", pulp.LpMinimize)

        # Decision variables
        charge = pulp.LpVariable.dicts(
            "charge", range(H), lowBound=0, upBound=bat_power
        )
        discharge = pulp.LpVariable.dicts(
            "discharge", range(H), lowBound=0, upBound=bat_power
        )
        soc = pulp.LpVariable.dicts(
            "soc", range(H + 1), lowBound=0, upBound=bat_capacity
        )

        grid_import = pulp.LpVariable.dicts("import", range(H), lowBound=0)
        grid_export = pulp.LpVariable.dicts("export", range(H), lowBound=0)

        m += soc[0] == soc_initial

        for t in range(H):
            m += (
                soc[t + 1]
                == soc[t] + charge[t] * eff_charge - discharge[t] / eff_discharge
            )

            m += (
                var_solar[t] + grid_import[t] + discharge[t]
                == var_load[t] + charge[t] + grid_export[t]
            )

        m += soc[H] >= soc_final_target

        m += pulp.lpSum(
            [
                grid_import[t] * buy_price[t] - grid_export[t] * sell_price[t]
                for t in range(H)
            ]
        )

        m.solve(pulp.PULP_CBC_CMD(msg=False))

        _LOGGER.warning(pulp.LpStatus[m.status])

        schedule = {
            "charge": [pulp.value(charge[t]) for t in range(H)],
            "discharge": [pulp.value(discharge[t]) for t in range(H)],
            "grid_import": [pulp.value(grid_import[t]) for t in range(H)],
            "grid_export": [pulp.value(grid_export[t]) for t in range(H)],
            "soc": [pulp.value(soc[t]) for t in range(H + 1)],
        }

        _LOGGER.warning(schedule)
        # What is returned here is stored in self.data by the DataUpdateCoordinator
        #         return "Energy Management Coordinator", load[0], solar[0]
        return EnergyData("Energy Management Coordinator", 10.0, 12.0)


class SpotPriceArray:
    """Class to hold 24-hour array of spot prices."""

    def __init__(
        self, today_entity, tomorrow_entity=None, has_tomorrow=False, current_hour=None
    ) -> None:
        """Initialize the array from today's spot prices.

        today_entity / tomorrow_entity: dicts from HA entities
        has_tomorrow: binary_sensor.spot_electricity_has_tomorrow_data.
        """
        self.today_entity = today_entity
        self.tomorrow_entity = tomorrow_entity or {}
        self.has_tomorrow = has_tomorrow

        # Build initial 24h deque from current hour to next day
        self.prices = []
        self.build_array(today_entity, tomorrow_entity, has_tomorrow, current_hour)

    def build_array(self, today_entity, tomorrow_entity, has_tomorrow, current_hour):
        """Fill the deque with 24 consecutive hours starting from current_index."""
        today_hours = sorted(today_entity.items(), key=lambda x: x[0])
        tomorrow_hours = (
            sorted(tomorrow_entity.items(), key=lambda x: x[0])
            if tomorrow_entity
            else []
        )

        # Add remaining hours today
        if has_tomorrow:
            for _, data in today_hours[current_hour:]:
                self.prices.append(data)

            # Add hours from tomorrow if needed
            hours_needed = 24 - len(self.prices)
            for _, data in tomorrow_hours[:hours_needed]:
                self.prices.append(data)
        else:
            # Just cycle through today's hours
            for i in range(24):
                index = (current_hour + i) % 24
                _, data = today_hours[index]
                self.prices.append(data)
