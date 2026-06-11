from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN, TYPE_HYPERMAX, TYPE_LIGHT, TYPE_SOCKET, TYPE_THERMOMETER
from .entity import AquaelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    entities = []
    if coordinator.device_type in (TYPE_HYPERMAX, TYPE_LIGHT, TYPE_SOCKET, TYPE_THERMOMETER):
        entities.append(AquaelIdentifyButton(coordinator))
    if coordinator.device_type == TYPE_LIGHT:
        entities.extend([
            AquaelLightPresetButton(coordinator, "plant", "Plant", "mdi:leaf"),
            AquaelLightPresetButton(coordinator, "sunny", "Sunny", "mdi:white-balance-sunny"),
            AquaelLightPresetButton(coordinator, "marine", "Marine", "mdi:waves"),
        ])
    if coordinator.device_type == TYPE_THERMOMETER:
        entities.append(AquaelResetButton(coordinator))
    async_add_entities(entities)


class AquaelBaseButton(AquaelEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, icon, entity_category=EntityCategory.CONFIG):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = icon
        if entity_category is not None:
            self._attr_entity_category = entity_category


class AquaelIdentifyButton(AquaelBaseButton):
    def __init__(self, coordinator):
        super().__init__(coordinator, "identify", "Identyfikuj", "mdi:crosshairs-question")

    async def async_press(self):
        await self.coordinator.async_identify()


class AquaelResetButton(AquaelBaseButton):
    def __init__(self, coordinator):
        super().__init__(coordinator, "reset", "Reset ustawien urzadzenia", "mdi:restore-alert")

    async def async_press(self):
        await self.coordinator.async_reset_device()


class AquaelLightPresetButton(AquaelBaseButton):
    def __init__(self, coordinator, preset, name, icon):
        super().__init__(coordinator, f"preset_{preset}", name, icon, entity_category=None)
        self._preset = preset

    async def async_press(self):
        await self.coordinator.async_set_light_preset(self._preset)
