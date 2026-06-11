from homeassistant.components.text import TextEntity

from .const import DOMAIN, TYPE_HYPERMAX, TYPE_THERMOMETER
from .entity import AquaelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    entities = [AquaelDeviceNameText(coordinator)]
    if coordinator.device_type == TYPE_THERMOMETER:
        entities.extend([
            AquaelThermometerText(coordinator, "water_name",   "Nazwa czujnika wody",     "mdi:water-opacity",   "STOUT", "STOUTOK"),
            AquaelThermometerText(coordinator, "ambient_name", "Nazwa czujnika otoczenia", "mdi:home-thermometer", "STOIN", "STOINOK"),
        ])
    async_add_entities(entities)


class AquaelBaseText(AquaelEntity, TextEntity):
    _attr_mode = "text"
    _attr_native_max = 30

    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}_text"
        self._attr_icon = icon


class AquaelDeviceNameText(AquaelBaseText):
    def __init__(self, coordinator):
        super().__init__(coordinator, "device_name", "Nazwa urzadzenia", "mdi:pencil")

    @property
    def native_value(self):
        return self._get("user_device_name") or self._get("device_name") or self.coordinator.device_name

    async def async_set_value(self, value: str) -> None:
        if self.coordinator.device_type == TYPE_HYPERMAX:
            await self.coordinator.async_set_hypermax_value("UserDeviceName", value)
        else:
            await self.coordinator.async_set_legacy_name(value)


class AquaelThermometerText(AquaelBaseText):
    def __init__(self, coordinator, key, name, icon, command_prefix, expected):
        super().__init__(coordinator, key, name, icon)
        self._command_prefix = command_prefix
        self._expected = expected

    @property
    def native_value(self):
        return self._get(self._key) or ""

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_send_text_command(self._command_prefix, value, self._expected)
