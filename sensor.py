"""Interfaces with the Integration 101 Template api sensors."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    dataclass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MyConfigEntry
from .const import DOMAIN
from .coordinator import EnergyManagementCoordinator, SecondHouseholdCoordinator

_LOGGER = logging.getLogger(__name__)


# TODO: change the Device class below to match the data structure returned by api
@dataclass
class Device:
    """API device."""

    device_id: int
    device_unique_id: str
    device_type: str
    name: str
    state: int | bool


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MyConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Sensors."""
    # This gets the data update coordinator from the config entry runtime data as specified in your __init__.py
    coordinator: SecondHouseholdCoordinator = config_entry.runtime_data.coordinator
    scheduler: EnergyManagementCoordinator = config_entry.runtime_data.scheduler

    # Create the sensors.
    async_add_entities(
        [
            SecondHouseholdConsumption(coordinator, coordinator.data.device),
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
        _LOGGER.debug("Device: %s", self.device)
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
            name=f"SecondHouseholdConsumption{self.device.device_id}",
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
        return self.device.name

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
        return f"{DOMAIN}-{self.device.device_unique_id}"


class CorrectedForecast(CoordinatorEntity, SensorEntity):
    """Representation of a corrected forecast from Forecast.Solar integration."""

    def __init__(
        self,
        coordinator: EnergyManagementCoordinator,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.state: float = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with latest data from coordinator."""
        # This method is called by your DataUpdateCoordinator when a successful update runs.
        self.state = self.coordinator.data.corrected_forecast
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
        return float(self.state)

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
        self.state: float = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update sensor with latest data from coordinator."""
        # This method is called by your DataUpdateCoordinator when a successful update runs.
        self.state = self.coordinator.data.houseload_prediction
        self.async_write_ha_state()

    @property
    def device_class(self) -> str:
        """Return device class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes
        return SensorDeviceClass.POWER

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Houseload Prediction"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        return float(self.state)

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
