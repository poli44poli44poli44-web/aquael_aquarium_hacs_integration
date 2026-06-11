from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TYPE_THERMOMETER


class AquaelEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=coordinator.device_name,
            manufacturer="AQUAEL",
            model=coordinator.model_name,
        )
        if coordinator.device_type == TYPE_THERMOMETER and coordinator.ip:
            device_info["configuration_url"] = f"http://{coordinator.ip}/chart?"
        self._attr_device_info = device_info

    def _get(self, key, default=None):
        return (self.coordinator.data or {}).get(key, default)
