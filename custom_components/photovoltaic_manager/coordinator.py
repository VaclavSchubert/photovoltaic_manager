"""Coordinators responsible for periodic updates."""

from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from typing import Literal
import zoneinfo

import numpy as np
import pulp
import requests

from homeassistant.components.recorder import statistics
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_CURRENT_CHARGE,
    BATTERY_STATUS,
    BATTERY_VOLTAGE_CHARGE,
    COMBI_HEATER,
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
    DEFAULT_PLAN_INTERVAL,
    DOMAIN,
    ELECTRIC_HEATER,
    HAS_TOMORROW_SPOT_DATA,
    HOUSEHOLD_CONSUMPTION,
    INVERTER_EXPORT_IMPORT,
    INVERTER_POWER,
    MIN_SCAN_INTERVAL,
    PV_PRODUCTION_FORECAST_TODAY,
    PV_PRODUCTION_FORECAST_TOMORROW,
    REAL_PV_PRODUCTION,
    REMOTECONTROL_DURATION,
    REMOTECONTROL_MODE,
    REMOTECONTROL_POWER,
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
    "fall",
    "fall",
    "fall",
    "winter",
]


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


class EnergyManagementCoordinator(DataUpdateCoordinator):
    """Coordinator to periodically calculate and correct consumption in household."""

    data: EnergyData
    surplus = 0.0

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        self.hass = hass
        # constant sensors
        self.real_pv_production_entity = REAL_PV_PRODUCTION
        self.today_order_entity = SPOT_MARKET_TODAY_ORDER
        self.has_tomorrow_entity = HAS_TOMORROW_SPOT_DATA
        self.tomorrow_order_entity = SPOT_MARKET_TOMORROW_ORDER
        self.forecast_pv_production_entity = PV_PRODUCTION_FORECAST_TOMORROW
        self.house_load_entity = HOUSEHOLD_CONSUMPTION
        self.initial_soc_entity = BATTERY_STATUS
        self.inverter_power = INVERTER_POWER
        self.battery_voltage = float(self.hass.states.get(BATTERY_VOLTAGE_CHARGE).state)
        self.battery_current = float(self.hass.states.get(BATTERY_CURRENT_CHARGE).state)
        # parameters for optimization
        self.bat_capacity = config_entry.data.get(CONF_BATTERY_CAPACITY, 10.0)  # kWh
        self.min_soc = config_entry.data.get(CONF_MIN_SOC, 10)  # %
        self.max_soc = config_entry.data.get(CONF_MAX_SOC, 90)  # %
        self.weather = config_entry.data.get(CONF_WEATHER_FORECAST, "")
        self.ac = config_entry.data.get(CONF_AIR_CONDITIONING, "")
        self.heater = config_entry.data.get(CONF_HEATER_ENTITY, "")
        self.heater_type = config_entry.data.get(CONF_HEATER_TYPE, "")
        self.heater_power = config_entry.data.get(CONF_HEATER_POWER, 0.0)  # kW
        self.heater_volume = config_entry.data.get(CONF_HEATER_VOLUME, 0)  # liters
        self.buy_price = json.loads(config_entry.data.get(CONF_ELECTRICITY_PRICE, "[]"))
        self.heater_plan = []
        # set variables from options.  You need a default here incase options have not been set
        self.poll_interval = DEFAULT_PLAN_INTERVAL
        self.spot_array = SpotPriceArray()

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

    async def async_initialize(self):
        """Async initialize coordinator attribute."""
        datetime = dt_util.now(zoneinfo.ZoneInfo(self.hass.config.time_zone))
        month = datetime.month - 1
        hour = datetime.hour

        solar_correction = self.hass.data["pv_production_correction"]["data"][
            SEASONS_BY_MONTH[month]
        ]["values"]  # solar forecast W each hour

        solar_prediction = await self.get_hourly_proportional_average(
            self.hass, self.forecast_pv_production_entity
        )
        if None in solar_prediction:
            raise UpdateFailed(
                f"Not enough history data to compute solar prediction for {self.forecast_pv_production_entity}"
            )
        self.solar_now = max(0, solar_prediction[0] - solar_correction[hour])

    async def update_predictions(
        self, hass: HomeAssistant, curve, new_input, season, hour
    ):
        """Update stored predictions."""
        store = hass.data[curve]["store"]
        hass.data[curve]["data"][season]["values"][hour] = (
            hass.data[curve]["data"][season]["values"][hour]
            * hass.data[curve]["data"][season]["counts"][hour]
            + new_input
        ) / (hass.data[curve]["data"][season]["counts"][hour] + 1)
        hass.data[curve]["data"][season]["counts"][hour] += 1
        await store.async_save(hass.data[curve]["data"])

    async def get_hourly_proportional_average(
        self, hass: HomeAssistant, entity_id: str
    ) -> list[float | None]:
        """Return a 24-element list of proportional hourly averages using HA's get_significant_states() to retrieve state change history."""
        hours = 24
        end_time = dt_util.now(zoneinfo.ZoneInfo(self.hass.config.time_zone)).replace(
            minute=0, second=0, microsecond=0
        )
        start_time = end_time - timedelta(hours=hours + 1)

        # Fetch history: dict: {entity_id: [State, State, ...]}
        history = await recorder.get_instance(hass).async_add_executor_job(
            get_significant_states,
            hass,
            start_time,
            end_time,
            [entity_id],
            None,
            True,
            False,
        )

        states = history.get(entity_id, [])

        # No history -> return Nones
        if not states:
            return [None] * hours

        # Convert HA State objects -> (timestamp, float_value)
        timeline = []
        for st in states:
            try:
                v = float(st.state)
                timeline.append((st.last_updated, v))
            except ValueError:
                pass

        # If nothing converted
        if not timeline:
            return [None] * hours

        # Ensure first value exists at start_time
        first_ts, first_val = timeline[0]
        if first_ts > start_time:
            # Insert synthetic starting point
            timeline.insert(0, (start_time, first_val))

        # Add final synthetic endpoint at end_time
        timeline.append((end_time, timeline[-1][1]))

        # Now compute hourly proportional averages
        results = []

        for h in range(hours):
            hour_start = start_time + timedelta(hours=h)
            hour_end = hour_start + timedelta(hours=1)

            weighted_sum = 0.0
            covered_seconds = 0.0

            for i in range(len(timeline) - 1):
                seg_start, value = timeline[i]
                seg_end, _ = timeline[i + 1]

                # No overlap
                if seg_end <= hour_start or seg_start >= hour_end:
                    continue

                # Overlap region
                overlap_start = max(seg_start, hour_start)
                overlap_end = min(seg_end, hour_end)

                duration = (overlap_end - overlap_start).total_seconds()
                if duration > 0:
                    weighted_sum += value * duration
                    covered_seconds += duration

            if covered_seconds > 0:
                results.append(weighted_sum / covered_seconds)
            else:
                results.append(None)

        return results

    async def async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        datetime = dt_util.now(zoneinfo.ZoneInfo(self.hass.config.time_zone))
        month = datetime.month - 1
        hour = datetime.hour

        H = 24  # hours
        types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {
            "mean"
        }

        solar_correction = self.hass.data["pv_production_correction"]["data"][
            SEASONS_BY_MONTH[month]
        ]["values"]  # solar forecast W each hour

        solar_prediction = await self.get_hourly_proportional_average(
            self.hass, self.forecast_pv_production_entity
        )
        if None in solar_prediction:
            raise UpdateFailed(
                f"Not enough history data to compute solar prediction for {self.forecast_pv_production_entity}"
            )

        current_pow = self.hass.states.get(PV_PRODUCTION_FORECAST_TODAY)
        if current_pow is None:
            raise UpdateFailed(f"Entity {PV_PRODUCTION_FORECAST_TODAY} not found")

        solar_prediction[0] = float(current_pow.state)

        solar = list(
            np.clip(
                np.array(solar_prediction) * 0.9
                - np.array(solar_correction[hour:] + solar_correction[:hour]),
                0,
                None,
            )
        )
        load = self.hass.data["house_load_predictor"]["data"][SEASONS_BY_MONTH[month]][
            "values"
        ].copy()  # load forecast W each hour

        last_hour_load = await recorder.get_instance(self.hass).async_add_executor_job(
            statistics.get_last_statistics,
            self.hass,
            1,
            self.house_load_entity,
            False,
            types,
        )
        # DEBUG
        # last_hour_load = {"key": [{"mean": load[hour]}]}

        last_hour_load = list(last_hour_load.values())[0][0].get("mean")
        await self.update_predictions(
            self.hass,
            "house_load_predictor",
            last_hour_load,
            SEASONS_BY_MONTH[month],
            (hour - 1) % 24,
        )

        load_now = load[hour]

        last_hour_production = await recorder.get_instance(
            self.hass
        ).async_add_executor_job(
            statistics.get_last_statistics,
            self.hass,
            1,
            self.real_pv_production_entity,
            False,
            types,
        )

        # DEBUG
        # last_hour_production = {"key": [{"mean": solar[0]}]}
        last_hour_production = self.solar_now - list(last_hour_production.values())[0][
            0
        ].get("mean")
        await self.update_predictions(
            self.hass,
            "pv_production_correction",
            last_hour_production,
            SEASONS_BY_MONTH[month],
            (hour - 1) % 24,
        )

        self.solar_now = solar[0]

        var_solar = solar
        var_load = load[hour:] + load[:hour]  # rotate to start from current hour

        for h in range(H):
            var_solar[h] /= 1000  # convert to kW
            var_load[h] /= 1000  # convert to kW

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
        ]  # price to import from grid
        buy_price = self.buy_price
        buy_price = (
            buy_price[hour:] + buy_price[:hour]
        )  # rotate to start from current hour

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

        today_order = today_order.copy()
        tomorrow_order = tomorrow_order.copy()
        for key in ["icon", "friendly_name"]:
            today_order.pop(key, None)
            tomorrow_order.pop(key, None)

        self.spot_array.build_array(today_order, tomorrow_order, has_tomorrow, hour)
        sell_price = list(self.spot_array.prices)  # price to export to grid

        # begin optimization model
        m = pulp.LpProblem("EnergyManagement", pulp.LpMinimize)

        bat_capacity = self.bat_capacity  # kWh
        bat_power = self.battery_current * self.battery_voltage / 1000  # kW
        inverter_power = 9  # kW
        eff_charge = 0.97
        eff_discharge = 0.95
        soc_initial = 8.65
        soc_final_target = (
            (
                self.min_soc
                + (self.max_soc - self.min_soc) * (1 - np.sin(np.pi * month / 11))
            )
            / 100
            * bat_capacity
        )  # kWh

        # DEBUG
        # Battery parameters
        inverter_power_state = self.hass.states.get(self.inverter_power)
        if inverter_power_state is None:
            raise UpdateFailed(f"Entity {self.inverter_power} not found")
        inverter_power = float(inverter_power_state.state) / 1000
        initial_soc_state = self.hass.states.get(self.initial_soc_entity)
        if initial_soc_state is None:
            raise UpdateFailed(f"Entity {self.initial_soc_entity} not found")
        soc_initial = float(initial_soc_state.state) / 100.0 * bat_capacity  # kWh

        P_EWH = 1000.0
        P_AC_el = 1000.0
        cool_mode = False

        # Decision variables
        battery = pulp.LpVariable.dicts(
            "battery", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )
        charge = pulp.LpVariable.dicts(
            "charge", range(H), lowBound=0, upBound=bat_power
        )
        discharge = pulp.LpVariable.dicts(
            "discharge", range(H), lowBound=0, upBound=inverter_power * 0.6
        )
        soc = pulp.LpVariable.dicts(
            "soc", range(H + 1), lowBound=0, upBound=bat_capacity
        )

        grid = pulp.LpVariable.dicts(
            "grid", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )
        grid_import = pulp.LpVariable.dicts(
            "import", range(H), lowBound=0, upBound=inverter_power
        )
        grid_export = pulp.LpVariable.dicts(
            "export", range(H), lowBound=0, upBound=inverter_power
        )

        pen_low_soc = pulp.LpVariable.dicts(
            "pen_low_soc", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )

        obj_sum = pulp.LpVariable.dicts("obj_sum", range(H), cat=pulp.LpContinuous)

        M = 10000  # big-M constant

        v_AC = pulp.LpVariable.dicts(
            "v_AC", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )  # if AC on
        # Electrical heaters and EWH
        v_E_wh = pulp.LpVariable.dicts(
            "v_E_wh", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )  # if water heater on
        appliances = pulp.LpVariable.dicts(
            "appliances", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )  # if appliances can be on

        if self.heater != "":
            P_EWH = self.heater_power

            if self.heater_type == ELECTRIC_HEATER:
                EWH_hours = (
                    self.heater_volume * 5 / self.heater_power / 100
                )  # hours to heat water
                window_size = 3

                for i in range(H - window_size + 1):
                    m += pulp.lpSum(v_E_wh[t] for t in range(i, i + window_size)) <= 1

                m += pulp.lpSum(v_E_wh[t] for t in range(H)) == EWH_hours
            elif self.heater_type == COMBI_HEATER:
                for t in range(H):
                    m += grid_import[t] <= M * (1 - v_E_wh[t])
                    m += discharge[t] <= M * (1 - v_E_wh[t])

        if self.ac != "":
            P_AC_el = 1.1

            result = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {
                    "entity_id": self.weather,
                    "type": "hourly",
                },
                blocking=True,
                return_response=True,
            )

            if not isinstance(result, dict) or self.weather not in result:
                raise UpdateFailed(
                    f"Invalid forecast response from weather service for {self.weather}"
                )

            forecast_data = result[self.weather]
            if not isinstance(forecast_data, dict) or "forecast" not in forecast_data:
                raise UpdateFailed(
                    f"Missing forecast data in weather service response for {self.weather}"
                )

            forecast = forecast_data["forecast"]
            P_amb = [f["temperature"] for f in forecast]

            avg_temp = sum(P_amb) / len(P_amb)

            if avg_temp - 22 > 0:
                cool_mode = True

            for t in range(H):
                m += grid_import[t] <= M * (1 - v_AC[t])
                m += discharge[t] <= M * (1 - v_AC[t])

        # DEBUG
        # Solar generation in kW, assuming a peak around midday
        # var_solar = [max(0, float(np.sin(np.pi * t / H)) * 2.4) for t in range(H)]
        # Load demand in kW, assuming a base load plus morning/evening peaks
        # var_load = [np.random.normal(loc=0.5, scale=0.1) for t in range(H)]

        m += soc[0] == soc_initial

        for t in range(H):
            m += grid_import[t] <= inverter_power * grid[t]
            m += grid_export[t] <= var_solar[t]
            m += grid_export[t] <= inverter_power * (1 - grid[t])

            m += charge[t] <= var_solar[t] + grid_import[t]
            m += charge[t] <= bat_power * battery[t]  # big-M linearization
            m += discharge[t] <= inverter_power * 0.6 * (1 - battery[t])

            m += (
                soc[t + 1]
                == soc[t] + charge[t] * eff_charge - discharge[t] / eff_discharge
            )

            m += soc[t + 1] <= self.max_soc / 100 * bat_capacity

            m += soc[t] - self.min_soc / 100 * bat_capacity <= bat_capacity * (
                1 - pen_low_soc[t]
            )
            m += (
                soc[t] - self.min_soc / 100 * bat_capacity
                >= -bat_capacity * pen_low_soc[t]
            )

            m += (
                obj_sum[t]
                == grid_import[t] * buy_price[t] - grid_export[t] * sell_price[t]
            )

            m += (
                var_solar[t] + grid_import[t] + discharge[t]
                == var_load[t]
                + P_AC_el * v_AC[t]
                + P_EWH * v_E_wh[t]
                + charge[t]
                + grid_export[t]
            )

            m += var_solar[t] - charge[t] - var_load[t] >= -M * (1 - appliances[t])
            m += v_E_wh[t] * P_EWH + v_AC[t] * P_AC_el <= M * appliances[t]

        m += soc[H] >= soc_final_target

        m += pulp.lpSum(
            [
                obj_sum[t]
                + pen_low_soc[t]
                - v_E_wh[t] * 2 * min(sell_price)
                - v_AC[t] * min(sell_price)
                for t in range(H)
            ]
        )

        await recorder.get_instance(self.hass).async_add_executor_job(
            m.solve, pulp.PULP_CBC_CMD(msg=False)
        )

        schedule = {
            "v_AC": [pulp.value(v_AC[t]) for t in range(H)],
            "v_ewh": [pulp.value(v_E_wh[t]) for t in range(H)],
            "pen_low_soc": [pulp.value(pen_low_soc[t]) for t in range(H)],
            "obj_sum": [
                pulp.value(
                    grid_import[t] * buy_price[t] - grid_export[t] * sell_price[t]
                )
                for t in range(H)
            ],
            "charge": [pulp.value(charge[t]) for t in range(H)],
            "discharge": [pulp.value(discharge[t]) for t in range(H)],
            "grid_import": [pulp.value(grid_import[t]) for t in range(H)],
            "grid_export": [pulp.value(grid_export[t]) for t in range(H)],
            "soc": [pulp.value(soc[t]) for t in range(H + 1)],
        }

        _LOGGER.warning(pulp.LpStatus[m.status])
        _LOGGER.warning(schedule)

        if m.status == pulp.LpStatusOptimal:
            await self.hass.services.async_call(
                "select",
                "select_option",
                {
                    "entity_id": REMOTECONTROL_MODE,
                    "option": "Enabled Grid Control",
                },
                blocking=True,
            )

            self.surplus = pulp.value(grid_export[0]) * 1000

            remotecontrol_power = int(
                (
                    pulp.value(grid_import[0])
                    if pulp.value(grid[0]) == 1
                    else -pulp.value(grid_export[0])
                )
                * 1000
            )

            if remotecontrol_power < 0 and sell_price[0] < 2 * min(buy_price):
                remotecontrol_power = 0

            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": REMOTECONTROL_POWER,
                    "value": remotecontrol_power,
                },
                blocking=True,
            )

            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": REMOTECONTROL_DURATION, "value": 3600},
                blocking=True,
            )

            await self.hass.services.async_call(
                "button",
                "press",
                {"entity_id": INVERTER_EXPORT_IMPORT},
            )

            if self.heater != "":
                if pulp.value(v_E_wh[0]) > 0.5:
                    await self.hass.services.async_call(
                        "switch",
                        "turn_on",
                        {"entity_id": self.heater},
                    )
                else:
                    await self.hass.services.async_call(
                        "switch",
                        "turn_off",
                        {"entity_id": self.heater},
                    )

            if self.ac != "":
                if pulp.value(v_AC[0]) > 0.5:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {
                            "entity_id": self.ac,
                            "hvac_mode": "cool" if cool_mode is True else "heat",
                        },
                    )
                else:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {
                            "entity_id": self.ac,
                            "hvac_mode": "off",
                        },
                    )

        # What is returned here is stored in self.data by the DataUpdateCoordinator
        return EnergyData("Energy Management Coordinator", load_now, self.solar_now)


class SecondHouseholdCoordinator(DataUpdateCoordinator):
    """Coordinator to periodically query the Shelly API about energy consumption in the second household."""

    data: APIData

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        scheduler: EnergyManagementCoordinator,
    ) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_SECOND_HOME_SERVER]
        self.api_key = config_entry.data[CONF_SECOND_HOME_API_KEY]
        self.device_id = config_entry.data[CONF_SECOND_HOME_DEVICE_ID]

        self.url = f"{self.host}/v2/devices/api/get?auth_key={self.api_key}"
        self.payload = {"ids": [self.device_id], "select": ["status"]}
        self.headers = {"Content-Type": "application/json"}
        self.manager = scheduler

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
            response = await recorder.get_instance(self.hass).async_add_executor_job(
                self.send_request, self.url, self.payload, self.headers
            )
        except Exception as err:
            # This will show entities as unavailable by raising UpdateFailed exception
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        # What is returned here is stored in self.data by the DataUpdateCoordinator
        res = response.json()[0]
        device = Device(
            device_id=res["id"],
            name=res["code"],
            state=res["status"]["em:0"]["total_act_power"],
        )

        if self.manager.surplus > float(device.state) / 3600 * MIN_SCAN_INTERVAL:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": REMOTECONTROL_POWER,
                    "value": -int(device.state),
                },
            )
            self.manager.surplus -= float(device.state) / 3600 * MIN_SCAN_INTERVAL
        else:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": REMOTECONTROL_POWER,
                    "value": 0,
                },
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


class SpotPriceArray:
    """Class to hold 24-hour array of spot prices."""

    def __init__(self) -> None:
        """Initialize the array from today's spot prices."""

        self.prices = []

    def build_array(self, today_entity, tomorrow_entity, has_tomorrow, current_hour):
        """Fill the deque with 24 consecutive hours starting from current_index."""
        today_hours = sorted(today_entity.items(), key=lambda x: x[0])
        tomorrow_hours = (
            sorted(tomorrow_entity.items(), key=lambda x: x[0])
            if tomorrow_entity
            else []
        )

        self.prices = []

        # Add remaining hours today
        if has_tomorrow:
            for _, data in today_hours[current_hour:]:
                self.prices.append(data[1])

            # Add hours from tomorrow if needed
            hours_needed = 24 - len(self.prices)
            for _, data in tomorrow_hours[:hours_needed]:
                self.prices.append(data[1])
        else:
            # Just cycle through today's hours
            for i in range(24):
                index = (current_hour + i) % 24
                _, data = today_hours[index]
                self.prices.append(data[1])
