"""Number entities for Energy Management."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergyManagementCoordinator


class EnergyManagementNumber(
    CoordinatorEntity[EnergyManagementCoordinator],
    NumberEntity,
):
    """Configurable Energy Management parameter."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: EnergyManagementCoordinator,
        entry_id: str,
        parameter: str,
        name: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)

        self._parameter = parameter

        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{parameter}"

    @property
    def native_value(self) -> float:
        """Return the current value as a percentage."""
        return getattr(self.coordinator, self._parameter) * 100

    async def async_set_native_value(self, value: float) -> None:
        """Update the coordinator parameter."""
        setattr(
            self.coordinator,
            self._parameter,
            value / 100,
        )

        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Energy Management number entities."""

    async_add_entities(
        [
            EnergyManagementNumber(
                entry.runtime_data.scheduler,
                entry.entry_id,
                "min_soc",
                "Minimum SOC after export",
            ),
            EnergyManagementNumber(
                entry.runtime_data.scheduler,
                entry.entry_id,
                "export_tendency",
                "Export tendency",
            ),
            EnergyManagementNumber(
                entry.runtime_data.scheduler,
                entry.entry_id,
                "import_tendency",
                "Import tendency",
            ),
        ]
    )