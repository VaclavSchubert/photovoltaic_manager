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
from homeassistant.components.recorder.history import State, get_significant_states
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_CURRENT_CHARGE,
    BATTERY_STATUS,
    BATTERY_VOLTAGE_CHARGE,
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
    CONF_SECOND_HOME_DEVICE_ID,
    CONF_SECOND_HOME_MODE,
    CONF_SECOND_HOME_SERVER,
    CONF_WEATHER_FORECAST,
    DEFAULT_PLAN_INTERVAL,
    DOMAIN,
    ELECTRIC_HEATER,
    EXPORT_CONTROL_USER_LIMIT,
    HAS_TOMORROW_SPOT_DATA,
    HOUSEHOLD_CONSUMPTION,
    INTEGRATION_MODE_MANAGE,
    INTEGRATION_MODE_OBSERVE,
    INVERTER_EXPORT_HISTORY,
    INVERTER_EXPORT_IMPORT,
    INVERTER_IMPORT_HISTORY,
    INVERTER_POWER,
    MIN_SCAN_INTERVAL,
    PV_PRODUCTION_FORECAST_TODAY,
    PV_PRODUCTION_FORECAST_TOMORROW,
    REAL_PV_PRODUCTION,
    REMOTECONTROL_DURATION,
    REMOTECONTROL_MODE,
    REMOTECONTROL_POWER,
    SECOND_HOME_MODE_FULL,
    SECOND_HOME_MODE_VIEW,
    SECOND_HOME_SENSOR,
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
    grid_access = False

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
        battery_voltage_state = self.hass.states.get(BATTERY_VOLTAGE_CHARGE)
        if battery_voltage_state is None:
            raise UpdateFailed(f"Entity {BATTERY_VOLTAGE_CHARGE} not available")
        battery_current_state = self.hass.states.get(BATTERY_CURRENT_CHARGE)
        if battery_current_state is None:
            raise UpdateFailed(f"Entity {BATTERY_CURRENT_CHARGE} not available")
        self.battery_voltage = float(battery_voltage_state.state)
        self.battery_current = float(battery_current_state.state)
        # parameters for optimization
        self.bat_capacity = config_entry.data.get(CONF_BATTERY_CAPACITY, 10.0)  # kWh
        self.bat_power = self.battery_current * self.battery_voltage / 1000 * 0.6
        self.min_soc = config_entry.data.get(CONF_MIN_SOC, 10)  # %
        self.max_soc = config_entry.data.get(CONF_MAX_SOC, 90)  # %
        self.weather = config_entry.data.get(CONF_WEATHER_FORECAST, "")
        self.ac = config_entry.data.get(CONF_AIR_CONDITIONING, "")
        self.heater = config_entry.data.get(CONF_HEATER_ENTITY, "")
        self.heater_type = config_entry.data.get(CONF_HEATER_TYPE, "")
        self.heater_power = config_entry.data.get(CONF_HEATER_POWER, 0.0)  # kW
        self.heater_volume = config_entry.data.get(CONF_HEATER_VOLUME, 0)  # liters

        self.buy_mode = config_entry.data.get(CONF_BUY_PRICE_MODE, BUY_PRICE_MODE_FIXED)
        self.buy_price = json.loads(
            config_entry.data.get(
                CONF_ELECTRICITY_PRICE,
                "[4.11,4.11,4.11,4.11,3.7,3.7,3.7,3.7,4.11,4.11,4.11,4.11,4.11,4.11,4.11,3.7,3.7,3.7,3.7,4.11,4.11,4.11,4.11,4.11]",
            )
        )
        self.buy_distribution_cost = json.loads(
            config_entry.data.get(
                CONF_BUY_DISTRIBUTION_COST,
                "[2.57,2.57,2.57,2.57,0.27,0.27,0.27,0.27,2.57,2.57,2.57,2.57,2.57,2.57,2.57,0.27,0.27,0.27,0.27,2.57,2.57,2.57,2.57,2.57]",
            )
        )

        self.second_home_mode = config_entry.data.get(
            CONF_SECOND_HOME_MODE, SECOND_HOME_MODE_VIEW
        )
        self.integration_mode = config_entry.data.get(
            CONF_INTEGRATION_MODE, INTEGRATION_MODE_OBSERVE
        )
        self.heater_plan = []
        # set variables from options.  You need a default here incase options have not been set
        self.poll_interval = DEFAULT_PLAN_INTERVAL
        self.spot_array = SpotPriceArray()

        if self.integration_mode == INTEGRATION_MODE_OBSERVE:
            initial_soc_state = self.hass.states.get(self.initial_soc_entity)
            if initial_soc_state is None:
                raise UpdateFailed(f"Entity {self.initial_soc_entity} not found")
            self.soc_simulation = (
                float(initial_soc_state.state) / 100.0 * self.bat_capacity
            )
            self.cumulated_cost_saved = 0.0

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
        ]["values"]  # solar correcting array for each hour

        solar_prediction = await self.get_hourly_proportional_average(
            self.hass, self.forecast_pv_production_entity
        )  # solar forecast for each hour

        if None in solar_prediction:
            raise UpdateFailed(
                f"Not enough history data to compute solar prediction for {self.forecast_pv_production_entity}"
            )
        # get hour 0 for initialization of integration
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
                if not isinstance(st, State):
                    continue
                v = float(st.state)
                timeline.append((st.last_updated, v))
            except ValueError:
                pass

        if not timeline:
            return [None] * hours

        # Ensure first value exists at start_time
        first_ts, first_val = timeline[0]
        if first_ts > start_time:
            # Insert synthetic starting point
            timeline.insert(0, (start_time, first_val))

        # Add final endpoint at end_time
        timeline.append((end_time, timeline[-1][1]))

        # compute hourly proportional averages
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
        ]["values"]  # solar correction array for each hour

        solar_prediction = await self.get_hourly_proportional_average(
            self.hass, self.forecast_pv_production_entity
        )  # solar forecast for each hour
        if None in solar_prediction:
            raise UpdateFailed(
                f"Not enough history data to compute solar prediction for {self.forecast_pv_production_entity}"
            )

        # to make forecast more reliable, take the most recent prediction value
        current_pow = self.hass.states.get(PV_PRODUCTION_FORECAST_TODAY)
        if current_pow is None:
            raise UpdateFailed(f"Entity {PV_PRODUCTION_FORECAST_TODAY} not found")

        try:
            solar_prediction[0] = float(current_pow.state)
        except ValueError as e:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": REMOTECONTROL_POWER,
                    "value": 0,
                },
                blocking=True,
            )
            raise UpdateFailed(
                f"Entity {PV_PRODUCTION_FORECAST_TODAY} not available"
            ) from e

        # prediction*0.95 - correction == better prediction (pessimistic prediction is better)
        solar = list(
            np.clip(
                np.array(solar_prediction) * 0.95
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
        )  # load in last hour

        try:
            last_hour_load = list(last_hour_load.values())[0][0].get("mean")
        except (IndexError, KeyError):
            last_hour_load = None

        if last_hour_load is not None:
            await self.update_predictions(
                self.hass,
                "house_load_predictor",
                last_hour_load,
                SEASONS_BY_MONTH[month],
                (hour - 1) % 24,
            )  # update the load prediction array

        load_now = load[hour]  # for sensor

        last_hour_production_dict: dict[
            str, list[statistics.StatisticsRow]
        ] = await recorder.get_instance(self.hass).async_add_executor_job(
            statistics.get_last_statistics,
            self.hass,
            1,
            self.real_pv_production_entity,
            False,
            types,
        )

        try:
            last_hour_production_mean = list(last_hour_production_dict.values())[0][
                0
            ].get("mean")
        except (IndexError, KeyError):
            last_hour_production_mean = None
        if last_hour_production_mean is not None:
            last_hour_production = float(self.solar_now) - last_hour_production_mean
            await self.update_predictions(
                self.hass,
                "pv_production_correction",
                last_hour_production,
                SEASONS_BY_MONTH[month],
                (hour - 1) % 24,
            )  # correction is stored, so (prediction - real) is required

        second_home_load = self.hass.data["second_home_load"]["data"][
            SEASONS_BY_MONTH[month]
        ]["values"].copy()  # load forecast of second home W each hour

        # only matters for full second home load coverage
        if self.second_home_mode == SECOND_HOME_MODE_FULL:
            last_hour_second_home_load = await recorder.get_instance(
                self.hass
            ).async_add_executor_job(
                statistics.get_last_statistics,
                self.hass,
                1,
                SECOND_HOME_SENSOR,
                False,
                types,
            )

            try:
                last_hour_second_home_load = list(last_hour_second_home_load.values())[
                    0
                ][0].get("mean")
            except (IndexError, KeyError):
                last_hour_second_home_load = None

            if last_hour_second_home_load is not None:
                await self.update_predictions(
                    self.hass,
                    "second_home_load",
                    last_hour_second_home_load,
                    SEASONS_BY_MONTH[month],
                    (hour - 1) % 24,
                )

        self.solar_now = solar[0]  # for sensor

        var_solar = solar
        var_load = load[hour:] + load[:hour]  # rotate to start from current hour
        var_second_load = (
            second_home_load[hour:] + second_home_load[:hour]
        )  # rotate to start from current hour

        for h in range(H):
            var_solar[h] /= 1000  # convert to kW
            var_load[h] /= 1000  # convert to kW
            var_second_load[h] /= 1000  # convert to kW

        # data for spot price array
        # today price
        today_state = self.hass.states.get(self.today_order_entity)
        if today_state is None:
            raise UpdateFailed(f"Entity {self.today_order_entity} not found")
        today_order = today_state.attributes

        # if it has tomorrow data, retrieve that as well
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
        # remove icon and hass name because it ruins calculation
        for key in ["icon", "friendly_name"]:
            today_order.pop(key, None)
            tomorrow_order.pop(key, None)

        self.spot_array.build_array(today_order, tomorrow_order, has_tomorrow, hour)
        sell_price = list(self.spot_array.prices)  # price to export to grid

        distribution_cost = (
            self.buy_distribution_cost[hour:] + self.buy_distribution_cost[:hour]
        )

        if self.buy_mode == BUY_PRICE_MODE_FIXED:
            buy_price = (
                self.buy_price[hour:] + self.buy_price[:hour]
            )  # rotate to start from current hour
            buy_price = list(np.array(buy_price) + np.array(distribution_cost))
        else:
            buy_price = list(
                np.array(self.spot_array.prices) + np.array(distribution_cost)
            )  # price to import from grid

        # begin optimization model
        m = pulp.LpProblem("EnergyManagement", pulp.LpMinimize)

        # Battery parameters
        bat_capacity = self.bat_capacity  # kWh
        bat_power = self.bat_power  # W
        inverter_power = 9  # kW
        eff_charge = 0.97
        eff_discharge = 0.95
        soc_initial = 8.65
        soc_final_target = (
            (
                self.min_soc
                + (self.max_soc - self.min_soc) * (1 - np.sin(np.pi * month / 11) / 2)
            )
            / 100
            * bat_capacity
        )  # kWh

        inverter_power_state = self.hass.states.get(self.inverter_power)
        if inverter_power_state is None:
            raise UpdateFailed(f"Entity {self.inverter_power} not found")
        inverter_power = float(inverter_power_state.state) / 1000 * 0.6
        initial_soc_state = self.hass.states.get(self.initial_soc_entity)
        if initial_soc_state is None:
            raise UpdateFailed(f"Entity {self.initial_soc_entity} not found")
        soc_initial = float(initial_soc_state.state) / 100.0 * bat_capacity  # kWh

        # high value so that it cannot be achieved by solver
        # must be higher than big-M
        P_EWH = 10000.0
        P_AC_el = 10000.0
        # AC default
        cool_mode = False

        # Decision variables
        battery = pulp.LpVariable.dicts(
            "battery", range(H), lowBound=0, upBound=1, cat=pulp.LpBinary
        )
        charge = pulp.LpVariable.dicts(
            "charge", range(H), lowBound=0, upBound=bat_power
        )
        discharge = pulp.LpVariable.dicts(
            "discharge", range(H), lowBound=0, upBound=bat_power
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

        M = 1000  # big-M constant

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

            # heater is charged just from integration
            if self.heater_type == ELECTRIC_HEATER:
                EWH_hours = round(
                    self.heater_volume * 5 / self.heater_power / 100
                )  # hours to heat water
                window_size = 3 if EWH_hours <= 8 else 1

                for i in range(H - window_size + 1):
                    m += pulp.lpSum(v_E_wh[t] for t in range(i, i + window_size)) <= 1

                m += pulp.lpSum(v_E_wh[t] for t in range(H)) == EWH_hours

            # turn heater on only from surplus energy
            elif self.heater_type == COMBI_HEATER:
                for t in range(H):
                    m += grid_import[t] <= M * (1 - v_E_wh[t])
                    m += discharge[t] <= M * (1 - v_E_wh[t])

        if self.ac != "":
            # AC electrical power doesnt matter too much, just rough estimate suffices
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
            if not isinstance(forecast, list):
                raise UpdateFailed(
                    f"Invalid forecast data type in weather service response for {self.weather}"
                )
            P_amb = [
                f["temperature"]
                for f in forecast
                if isinstance(f, dict)
                and "temperature" in f
                and isinstance(f["temperature"], (int, float))
            ]

            # if its hot outside - cool mode
            # if its cold outside - heat mode
            if len(P_amb) == 0:
                raise UpdateFailed(
                    f"No valid temperature data in weather forecast for {self.weather}"
                )
            peak_temp = max(P_amb)

            if peak_temp - 22 > 0:
                cool_mode = True

            # turn AC on only for surplus energy
            for t in range(H):
                m += grid_import[t] <= M * (1 - v_AC[t])
                m += discharge[t] <= M * (1 - v_AC[t])

        # init battery SoC
        if self.integration_mode == INTEGRATION_MODE_MANAGE:
            m += soc[0] == soc_initial
        else:
            m += soc[0] == self.soc_simulation

        for t in range(H):
            m += grid_import[t] <= inverter_power * grid[t]
            m += grid_export[t] <= inverter_power * (1 - grid[t])

            # charge from solar and grid
            m += charge[t] <= var_solar[t] + grid_import[t]
            m += charge[t] <= bat_power * battery[t]  # big-M linearization
            m += discharge[t] <= bat_power * (1 - battery[t])

            # charging and discharging equation
            m += (
                soc[t + 1]
                == soc[t] + charge[t] * eff_charge - discharge[t] / eff_discharge
            )

            # penalty for low SoC
            m += soc[t] - self.min_soc / 100 * bat_capacity <= bat_capacity * (
                1 - pen_low_soc[t]
            )
            m += (
                soc[t] - self.min_soc / 100 * bat_capacity
                >= -bat_capacity * pen_low_soc[t]
            )

            # objective function
            # buy_price + 1.2 is to compensate for the reward for charging battery
            m += obj_sum[t] == grid_import[t] * (buy_price[t] + 1.2) - grid_export[
                t
            ] * (sell_price[t] - min(buy_price))

            # energy conservation equation
            m += (
                var_solar[t] + grid_import[t] + discharge[t]
                == var_load[t]
                + var_second_load[t]
                + P_AC_el * v_AC[t]
                + P_EWH * v_E_wh[t]
                + charge[t]
                + grid_export[t]
            )

            # turn on appliance only after charging battery and convering load
            m += var_solar[t] - charge[t] - var_load[t] - var_second_load[t] >= -M * (
                1 - appliances[t]
            )
            m += v_E_wh[t] * P_EWH + v_AC[t] * P_AC_el <= M * appliances[t]

        # give solver some soft constraint regarding final SoC
        m += soc[H] >= soc_final_target

        # objective function + penalty - bonus
        m += pulp.lpSum(
            [
                obj_sum[t]
                + pen_low_soc[t] * 5
                - charge[t] * 1.2
                - v_E_wh[t] * 1.1
                - v_AC[t]
                for t in range(H)
            ]
        )

        await recorder.get_instance(self.hass).async_add_executor_job(
            m.solve, pulp.PULP_CBC_CMD(msg=False)
        )

        # manage mode - control energy flow
        if self.integration_mode == INTEGRATION_MODE_MANAGE:
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

            _LOGGER.info(pulp.LpStatus[m.status])
            _LOGGER.info(schedule)

            # only manipulate energy when values make sense
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

                remotecontrol_power = int(
                    (
                        pulp.value(grid_import[0])
                        if pulp.value(grid[0]) == 1
                        else -pulp.value(grid_export[0])
                    )
                    * 1000
                )

                if remotecontrol_power < 0:
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": EXPORT_CONTROL_USER_LIMIT,
                            "value": int(self.hass.data["export_limit"]),
                        },
                        blocking=True,
                    )

                # prevent overcharging battery early when forecast is unreliable and battery is already quite full
                if (
                    soc_initial > bat_capacity * 0.85
                    and remotecontrol_power > 0
                    and buy_price[0] > 0
                ):
                    remotecontrol_power = 0

                # prevent export when it is past peak PV production and battery is quite low
                if (
                    soc_initial < bat_capacity * 0.6
                    and remotecontrol_power < 0
                    and hour > 11
                ):
                    remotecontrol_power = 0

                if sell_price[0] < 0 and remotecontrol_power <= 0:
                    remotecontrol_power = 0
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": EXPORT_CONTROL_USER_LIMIT,
                            "value": 0,
                        },
                        blocking=True,
                    )

                if soc_initial < bat_capacity * 0.4 and remotecontrol_power < 0:
                    remotecontrol_power = 0

                self.grid_access = False
                if remotecontrol_power != 0:
                    self.grid_access = True

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

                # prevent remotecontrol bottlenecking the power of PV
                if remotecontrol_power > 0 or (
                    soc_initial < bat_capacity * 0.97 and remotecontrol_power != 0
                ):
                    # enable remotecontrol of inverter
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
        else:
            # observe mode - see how much money this integration can possibly save
            last_hour_import = await recorder.get_instance(
                self.hass
            ).async_add_executor_job(
                statistics.get_last_statistics,
                self.hass,
                1,
                INVERTER_IMPORT_HISTORY,
                False,
                types,
            )

            try:
                last_hour_import = list(last_hour_import.values())[0][0].get("mean")
            except (IndexError, KeyError):
                last_hour_import = None

            if last_hour_import is not None:
                self.cumulated_cost_saved += (
                    float(last_hour_import) * buy_price[-1] / 1000
                )

            self.cumulated_cost_saved -= pulp.value(grid_import[0]) * buy_price[0]

            self.soc_simulation += pulp.value(grid_import[0]) / 1000.0
            if last_hour_load is None:
                last_hour_load = 0.0
            self.soc_simulation -= last_hour_load / 1000.0
            self.soc_simulation += last_hour_production / 1000.0

            last_hour_export = await recorder.get_instance(
                self.hass
            ).async_add_executor_job(
                statistics.get_last_statistics,
                self.hass,
                1,
                INVERTER_EXPORT_HISTORY,
                False,
                types,
            )
            try:
                last_hour_export = list(last_hour_export.values())[0][0].get("mean")
            except (IndexError, KeyError):
                last_hour_export = None
            if last_hour_export is not None:
                self.cumulated_cost_saved -= (
                    float(last_hour_export) * sell_price[0] / 1000
                )

            self.cumulated_cost_saved += pulp.value(grid_export[0]) * sell_price[0]
            _LOGGER.info(
                "Possible cumulative saved cost: %f CZK", self.cumulated_cost_saved
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
        self.mode = config_entry.data[CONF_SECOND_HOME_MODE]

        self.url = f"{self.host}/v2/devices/api/get?auth_key={self.api_key}"
        self.payload = {"ids": [self.device_id], "select": ["status"]}
        self.headers = {"Content-Type": "application/json"}
        self.manager = scheduler
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
        res = response
        try:
            device = Device(
                device_id=res["id"],
                name=res["code"],
                state=res["status"]["em:0"]["total_act_power"],
            )
        except KeyError as err:
            raise UpdateFailed(
                f"Unexpected API response structure: missing key {err}"
            ) from err

        if self.mode == SECOND_HOME_MODE_FULL and self.manager.grid_access is False:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": REMOTECONTROL_POWER,
                    "value": -int(device.state),
                },
                blocking=True,
            )

        return APIData("Second household Coordinator", device)

    def send_request(self, url, payload, headers):
        """Send request."""

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=3,
        )

        try:
            response.raise_for_status()  # Raise an exception for HTTP errors
        except requests.RequestException:
            raise UpdateFailed(
                f"API request failed with status code {response.status_code}: {response.text}"
            ) from None

        if not response.content:
            raise UpdateFailed("API response is empty")

        return response.json()[0]


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
