from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN, TYPE_SOCKET, TYPE_THERMOMETER
from .entity import AquaelEntity

LANGUAGE_OPTIONS = {
    1: "Polski",
    2: "Deutsch",
    3: "English",
    4: "Espanol",
}

UNIT_OPTIONS = {
    0: "Celsius",
    1: "Fahrenheit",
}

SOCKET_MODE_KEY_TO_LABEL = {
    "off":     "Wylaczone",
    "on":      "Wlaczone",
    "sunny":   "Dzien",
    "sunrise": "Swit",
    "lunar":   "Noc",
}

SOCKET_MODE_LABEL_TO_KEY = {v: k for k, v in SOCKET_MODE_KEY_TO_LABEL.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    entities = []
    if coordinator.device_type == TYPE_THERMOMETER:
        entities.extend([
            AquaelRangeSelect(coordinator, "notification_language", "Powiadomienia: jezyk", "mdi:translate", LANGUAGE_OPTIONS),
            AquaelRangeSelect(coordinator, "notification_unit", "Powiadomienia: jednostka", "mdi:temperature-celsius", UNIT_OPTIONS),
        ])
    if coordinator.device_type == TYPE_SOCKET:
        entities.extend([
            AquaelSocketModeSelect(coordinator, 1),
            AquaelSocketModeSelect(coordinator, 2),
        ])
    async_add_entities(entities)


class AquaelRangeSelect(AquaelEntity, SelectEntity):
    def __init__(self, coordinator, key, name, icon, options):
        super().__init__(coordinator)
        self._key = key
        self._option_map = options
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_options = list(options.values())

    @property
    def current_option(self):
        return self._option_map.get(self._get(self._key))

    async def async_select_option(self, option):
        reverse_map = {label: value for value, label in self._option_map.items()}
        await self.coordinator.async_set_range_settings(**{self._key: reverse_map[option]})


class AquaelSocketModeSelect(AquaelEntity, SelectEntity):
    _attr_options = list(SOCKET_MODE_KEY_TO_LABEL.values())

    def __init__(self, coordinator, output):
        super().__init__(coordinator)
        self._output = output
        self._attr_name = f"Tryb wyjscia {output}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_output_{output}_mode_select"
        self._attr_icon = "mdi:tune"

    @property
    def current_option(self):
        return SOCKET_MODE_KEY_TO_LABEL.get(self._get(f"output_{self._output}_mode"))

    async def async_select_option(self, option):
        self.coordinator.assert_manual_mode()
        mode_key = SOCKET_MODE_LABEL_TO_KEY.get(option)
        if mode_key is not None:
            await self.coordinator.async_set_socket_manual_mode(self._output, mode_key)
