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
    INVERTER_POWER,
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


async def async_load_predictor(hass: HomeAssistant):
    """Load predictor data."""

    types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {"mean"}

    load_statistics = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        HOUSEHOLD_CONSUMPTION,
        False,
        types,
    )

    data = {
        "summer": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "fall": {"values": [0.0 for _ in range(24)], "counts": [0 for _ in range(24)]},
        "winter": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "spring": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
    }

    latitude = hass.config.latitude
    hemisphere = "northern" if latitude >= 0 else "southern"

    task = iter(load_statistics.values())
    iterable = iter(next(task, []))

    while True:
        try:
            item = next(iterable)
            if item["mean"] < 0 or item["mean"] > 10000:
                continue  # Ignore invalid data
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)

            data[season]["values"][hour] += item["mean"]
            data[season]["counts"][hour] += 1
        except StopIteration:
            break

    for hour in data.values():
        for hr in range(24):
            if hour["counts"][hr] > 0:
                hour["values"][hr] /= hour["counts"][hr]

    return data


async def async_load_pv_predictor(hass: HomeAssistant):
    """Load PV predictor data."""

    types: set[Literal["last_reset", "max", "mean", "min", "state", "sum"]] = {"mean"}

    power_real = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        REAL_PV_PRODUCTION,
        False,
        types,
    )

    power_data = {
        "summer": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "fall": {"values": [0.0 for _ in range(24)], "counts": [0 for _ in range(24)]},
        "winter": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "spring": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
    }

    latitude = hass.config.latitude
    hemisphere = "northern" if latitude >= 0 else "southern"

    task = iter(power_real.values())
    iterable = iter(next(task, []))
    last_value = 0.0

    while True:
        try:
            item = next(iterable)
            if item["mean"] < 0 or item["mean"] > 15000:
                continue  # Ignore invalid data
            if item["mean"] == last_value and last_value != 0.0:
                continue  # Ignore invalid data
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)

            power_data[season]["values"][hour] += item["mean"]
            power_data[season]["counts"][hour] += 1
        except StopIteration:
            break

    for hour in power_data.values():
        for hr in range(24):
            if hour["counts"][hr] > 0:
                hour["values"][hr] /= hour["counts"][hr]

    power_predicted = await recorder.get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics,
        hass,
        sys.maxsize,
        PV_PRODUCTION_FORECAST_TODAY,
        False,
        types,
    )

    predict_power_data = {
        "summer": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "fall": {"values": [0.0 for _ in range(24)], "counts": [0 for _ in range(24)]},
        "winter": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
        "spring": {
            "values": [0.0 for _ in range(24)],
            "counts": [0 for _ in range(24)],
        },
    }

    task = iter(power_predicted.values())
    iterable = iter(next(task, []))
    last_value = 0.0

    while True:
        try:
            item = next(iterable)
            if item["mean"] < 0 or item["mean"] > 15000:
                continue  # Ignore invalid data
            if item["mean"] == last_value and last_value != 0.0:
                continue  # Ignore invalid data
            epoch_seconds = item["start"]
            hour = datetime.fromtimestamp(
                epoch_seconds, zoneinfo.ZoneInfo(hass.config.time_zone)
            ).hour
            season = await get_season_from_epoch(epoch_seconds, hemisphere)

            predict_power_data[season]["values"][hour] += item["mean"]
            predict_power_data[season]["counts"][hour] += 1
            last_value = item["mean"]
        except StopIteration:
            break

    for hour in predict_power_data.values():
        for hr in range(24):
            if hour["counts"][hr] > 0:
                hour["values"][hr] /= hour["counts"][hr]

    for season, data in predict_power_data.items():
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
    """Set up Custom Integration from a config entry."""

    inverter_power_state = hass.states.get(INVERTER_POWER)
    if inverter_power_state is None:
        raise ConfigEntryNotReady("Solax not loaded yet, cannot start integration")
    elif inverter_power_state.state in {"unavailable", "unknown"}:
        raise ConfigEntryNotReady("Solax inverter power sensor is unavailable")

    hass.data.setdefault("house_load_predictor", {})
    load_store = Store(hass, 1, "house_load_predictor")

    saved = await load_store.async_load() or {}

    hass.data["house_load_predictor"]["store"] = load_store

    if saved == {}:
        saved = await async_load_predictor(hass)

    hass.data["house_load_predictor"]["data"] = saved
    await load_store.async_save(saved)

    hass.data.setdefault("pv_production_correction", {})
    pv_store = Store(hass, 1, "pv_production_correction")

    saved = await pv_store.async_load() or {}

    hass.data["pv_production_correction"]["store"] = pv_store

    if saved == {}:
        saved = await async_load_pv_predictor(hass)

    hass.data["pv_production_correction"]["data"] = saved
    await pv_store.async_save(saved)

    # Initialise the coordinator that manages data updates from your api.
    # This is defined in coordinator.py
    if config_entry.data.get(CONF_SECOND_HOME_DEVICE_ID) is not None:
        coordinator = SecondHouseholdCoordinator(hass, config_entry)
        await coordinator.async_config_entry_first_refresh()
    else:
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
