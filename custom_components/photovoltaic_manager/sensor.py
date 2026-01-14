"""Interfaces with the Integration 101 Template api sensors."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MyConfigEntry
from .const import CONF_SECOND_HOME_DEVICE_ID, DOMAIN
from .coordinator import Device, EnergyManagementCoordinator, SecondHouseholdCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MyConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Sensors."""
    # This gets the data update coordinator from the config entry runtime data as specified in your __init__.py
    coordinator: SecondHouseholdCoordinator | None = (
        config_entry.runtime_data.coordinator
    )
    scheduler: EnergyManagementCoordinator = config_entry.runtime_data.scheduler

    if (
        config_entry.data.get(CONF_SECOND_HOME_DEVICE_ID) is not None
        and coordinator is not None
    ):
        async_add_entities(
            [
                SecondHouseholdConsumption(coordinator, coordinator.data.device),
            ]
        )

    # Create the sensors.
    async_add_entities(
        [
            CorrectedForecast(scheduler),
            HouseloadPrediction(scheduler),
        ]
    )


class SecondHouseholdConsumption(CoordinatorEntity, SensorEntity):
    """Representation of a Shelly device energy consumption in the second household."""

    def __init__(
        self,
        coordinator: SecondHouseholdCoordinator,
        device: Device,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.device = device
        self.device_id = device.device_id

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with latest data from coordinator."""
        # This method is called by your DataUpdateCoordinator when a successful update runs.
        self.device = self.coordinator.data.device
        self.async_write_ha_state()

    @property
    def device_class(self) -> str:
        """Return device class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes
        return SensorDeviceClass.POWER

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        # Identifiers are what group entities into the same device.
        # If your device is created elsewhere, you can just specify the indentifiers parameter.
        # If your device connects via another device, add via_device parameter with the indentifiers of that device.
        return DeviceInfo(
            name=f"{self.device.name}",
            manufacturer="Shelly",
            sw_version="1.0",
            identifiers={
                (
                    DOMAIN,
                    f"{self.coordinator.data.controller_name}-{self.device.device_id}",
                )
            },
        )

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Second Household Consumption"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        return float(self.device.state)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of temperature."""
        return UnitOfPower.WATT

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes
        return SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        # All entities must have a unique id.  Think carefully what you want this to be as
        # changing it later will cause HA to create new entities.
        return f"{DOMAIN}_{self.coordinator.data.controller_name.lower().replace(' ', '_')}"


class CorrectedForecast(CoordinatorEntity, SensorEntity):
    """Representation of a corrected forecast from Forecast.Solar integration."""

    def __init__(
        self,
        coordinator: EnergyManagementCoordinator,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._state: float = self.coordinator.data.corrected_forecast

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with latest data from coordinator."""
        # This method is called by your DataUpdateCoordinator when a successful update runs.
        self._state = self.coordinator.data.corrected_forecast
        self.async_write_ha_state()

    @property
    def device_class(self) -> str:
        """Return device class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes
        return SensorDeviceClass.POWER

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Corrected PV Production Forecast"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        return float(self._state)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of temperature."""
        return UnitOfPower.WATT

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes
        return SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        # All entities must have a unique id.  Think carefully what you want this to be as
        # changing it later will cause HA to create new entities.
        return f"{DOMAIN}-{self.name.lower().replace(' ', '_')}"


class HouseloadPrediction(CoordinatorEntity, SensorEntity):
    """Representation of a corrected forecast from Forecast.Solar integration."""

    def __init__(
        self,
        coordinator: EnergyManagementCoordinator,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._state: float = self.coordinator.data.houseload_prediction

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with latest data from coordinator."""
        # This method is called by your DataUpdateCoordinator when a successful update runs.
        self._state = self.coordinator.data.houseload_prediction
        self.async_write_ha_state()

    @property
    def device_class(self) -> str:
        """Return device class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes
        return SensorDeviceClass.POWER

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "House Load Prediction"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        return float(self._state)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of temperature."""
        return UnitOfPower.WATT

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes
        return SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        # All entities must have a unique id.  Think carefully what you want this to be as
        # changing it later will cause HA to create new entities.
        return f"{DOMAIN}-{self.name.lower().replace(' ', '_')}"
