"""Photovoltaic manager init."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
from typing import Literal
import zoneinfo

import numpy as np

from homeassistant.components.recorder import statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import recorder
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_SECOND_HOME_DEVICE_ID,
    HOUSEHOLD_CONSUMPTION,
    PLATFORMS,
    PV_PRODUCTION_FORECAST_TODAY,
    REAL_PV_PRODUCTION,
)
from .coordinator import EnergyManagementCoordinator, SecondHouseholdCoordinator

_LOGGER = logging.getLogger(__name__)


type MyConfigEntry = ConfigEntry[RuntimeData]


@dataclass
class RuntimeData:
    """Class to hold your data."""

    coordinator: SecondHouseholdCoordinator | None
    scheduler: EnergyManagementCoordinator


async def async_load_predictor(hass: HomeAssistant, config_entry: MyConfigEntry):
    """Load predictor data."""

    types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {"mean"}

    load_statistics = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        config_entry.data[HOUSEHOLD_CONSUMPTION],
        False,
        types,
    )

    data = {
        "summer": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "fall": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "winter": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "spring": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
    }

    latitude = hass.config.latitude
    hemisphere = "northern" if latitude >= 0 else "southern"

    task = iter(load_statistics.values())
    iterable = iter(next(task, []))
    last_record = 0

    while True:
        try:
            item = next(iterable)
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)
            if last_record - epoch_seconds > 3600:
                diff_hours = int((last_record - epoch_seconds) / 3600) % 24
                if diff_hours == 0:
                    last_record = item["start"]
                    continue

                for hr in range(diff_hours):
                    fill_hour = hour + hr + 1 % 24
                    data[season]["values"][fill_hour] += data[season]["values"][
                        fill_hour
                    ] / (data[season]["count"] // 24)
                    data[season]["count"] += 1

            data[season]["values"][hour] += item["mean"]
            last_record = item["start"]
        except StopIteration:
            break
        data[season]["count"] += 1

    for info in data.values():
        info["count"] = info["count"] // 24  # each hour counted separately

    for info in data.values():
        count = info["count"]
        if count > 0:
            info["values"] = [v / count for v in info["values"]]
    return data


async def async_load_pv_predictor(hass: HomeAssistant, config_entry: MyConfigEntry):
    """Load PV predictor data."""

    types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {"mean"}

    power_real = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        config_entry.data[REAL_PV_PRODUCTION],
        False,
        types,
    )

    power_data = {
        "summer": {"values": [0.0 for _ in range(24)], "count": 0},
        "fall": {"values": [0.0 for _ in range(24)], "count": 0},
        "winter": {"values": [0.0 for _ in range(24)], "count": 0},
        "spring": {"values": [0.0 for _ in range(24)], "count": 0},
    }

    latitude = hass.config.latitude
    hemisphere = "northern" if latitude >= 0 else "southern"

    task = iter(power_real.values())
    iterable = iter(next(task, []))
    last_record = 0

    while True:
        try:
            item = next(iterable)
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)
            if last_record - epoch_seconds > 3600:
                diff_hours = int((last_record - epoch_seconds) / 3600) % 24
                if diff_hours == 0:
                    last_record = item["start"]
                    continue

                for hr in range(diff_hours):
                    fill_hour = hour + hr + 1 % 24
                    power_data[season]["values"][fill_hour] += power_data[season][
                        "values"
                    ][fill_hour] / (power_data[season]["count"] // 24)
                    power_data[season]["count"] += 1

            power_data[season]["values"][hour] += item["mean"]
            last_record = item["start"]
        except StopIteration:
            break
        power_data[season]["count"] += 1

    for info in power_data.values():
        info["count"] = info["count"] // 24  # each hour counted separately

    for info in power_data.values():
        count = info["count"]
        if count > 0:
            info["values"] = [v / count for v in info["values"]]

    power_predicted = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        config_entry.data[PV_PRODUCTION_FORECAST_TODAY],
        False,
        types,
    )

    predict_power_data = {
        "summer": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "fall": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "winter": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
        "spring": {"values": [0.0 for _ in range(24)], "count": 0, "hours": 0},
    }

    latitude = hass.config.latitude
    hemisphere = "northern" if latitude >= 0 else "southern"

    task = iter(power_predicted.values())
    iterable = iter(next(task, []))
    last_record = 0

    while True:
        try:
            item = next(iterable)
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)
            if last_record - epoch_seconds > 3600:
                diff_hours = int((last_record - epoch_seconds) / 3600) % 24
                if diff_hours == 0:
                    last_record = item["start"]
                    continue

                for hr in range(diff_hours):
                    fill_hour = hour + hr + 1 % 24
                    predict_power_data[season]["values"][fill_hour] += (
                        predict_power_data[season]["values"][fill_hour]
                        / (predict_power_data[season]["count"] // 24)
                    )
                    predict_power_data[season]["count"] += 1

            predict_power_data[season]["values"][hour] += item["mean"]
            last_record = item["start"]
        except StopIteration:
            break
        predict_power_data[season]["count"] += 1

    for info in predict_power_data.values():
        info["count"] = info["count"] // 24  # each hour counted separately

    for info in predict_power_data.values():
        count = info["count"]
        if count > 0:
            info["values"] = [v / count for v in info["values"]]

    for season, data in predict_power_data.items():
        data["count"] = max(data["count"], power_data[season]["count"])
        data["values"] = list(
            np.array(data["values"]) - np.array(power_data[season]["values"])
        )

    return predict_power_data


async def get_season_from_epoch(seconds, hemisphere="northern"):
    """Get season from epoch time."""
    month = datetime.fromtimestamp(seconds).month

    if hemisphere == "southern":
        # Southern seasons are opposite
        if month in (12, 1, 2):
            return "summer"
        elif month in (3, 4, 5):
            return "fall"
        elif month in (6, 7, 8):
            return "winter"
        else:
            return "spring"
    else:
        # Northern hemisphere
        if month in (12, 1, 2):
            return "winter"
        elif month in (3, 4, 5):
            return "spring"
        elif month in (6, 7, 8):
            return "summer"
        else:
            return "fall"


async def async_setup_entry(hass: HomeAssistant, config_entry: MyConfigEntry) -> bool:
    """Set up Example Integration from a config entry."""

    # Test to see if api initialised correctly, else raise ConfigNotReady to make HA retry setup
    # TODO: Change this to match how your api will know if connected or successful update
    # if not coordinator.api.connected:
    #    raise ConfigEntryNotReady

    hass.data.setdefault("house_load_predictor", {})
    load_store = Store(hass, 1, "house_load_predictor")

    saved = await load_store.async_load() or {}

    hass.data["house_load_predictor"]["store"] = load_store

    if saved == {}:
        saved = await async_load_predictor(hass, config_entry)

    hass.data["house_load_predictor"]["data"] = saved
    await load_store.async_save(saved)

    hass.data.setdefault("pv_production_correction", {})
    pv_store = Store(hass, 1, "pv_production_correction")

    saved = await pv_store.async_load() or {}

    hass.data["pv_production_correction"]["store"] = pv_store

    if saved == {}:
        saved = await async_load_pv_predictor(hass, config_entry)

    hass.data["pv_production_correction"]["data"] = saved
    await pv_store.async_save(saved)

    # Initialise the coordinator that manages data updates from your api.
    # This is defined in coordinator.py
    try:
        config_entry.data[CONF_SECOND_HOME_DEVICE_ID]
        coordinator = SecondHouseholdCoordinator(hass, config_entry)
        await coordinator.async_config_entry_first_refresh()
    except KeyError:
        coordinator = None
    scheduler = EnergyManagementCoordinator(hass, config_entry)

    # Perform an initial data load from api.
    # async_config_entry_first_refresh() is special in that it does not log errors if it fails
    await scheduler.async_config_entry_first_refresh()

    # Add the coordinator and update listener to config runtime data to make
    # accessible throughout your integration
    config_entry.runtime_data = RuntimeData(coordinator, scheduler)

    # Setup platforms (based on the list of entity types in PLATFORMS defined above)
    # This calls the async_setup method in each of your entity type files.
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Return true to denote a successful setup.
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Delete device if selected from UI."""
    # Adding this function shows the delete device option in the UI.
    # Remove this function if you do not want that option.
    # You may need to do some checks here before allowing devices to be removed.
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: MyConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when you remove your integration or shutdown HA.
    # If you have created any custom services, they need to be removed here too.

    # Unload platforms and return result
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
