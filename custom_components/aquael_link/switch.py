from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .const import CONF_ADD_TO_PANEL, DOMAIN, TYPE_HYPERMAX, TYPE_LIGHT, TYPE_SOCKET, TYPE_THERMOMETER
from .entity import AquaelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    entities = []
    if coordinator.device_type == TYPE_SOCKET:
        entities.extend([
            AquaelSocketSwitch(coordinator, 1),
            AquaelSocketSwitch(coordinator, 2),
            AquaelAutoModeSwitch(coordinator),
        ])
    if coordinator.device_type == TYPE_LIGHT:
        entities.append(AquaelAutoModeSwitch(coordinator))
    if coordinator.device_type == TYPE_HYPERMAX:
        entities.extend([
            AquaelHypermaxModuleSwitch(coordinator, "pump_enabled", "Pompa", "mdi:pump", "Pump"),
            AquaelHypermaxModuleSwitch(coordinator, "thermostat_enabled", "Termostatowanie", "mdi:thermostat", "Heater"),
            AquaelHypermaxNotifySwitch(coordinator),
            AquaelPanelConsentSwitch(coordinator),
        ])
    if coordinator.device_type == TYPE_THERMOMETER:
        entities.extend([
            AquaelNotificationSwitch(coordinator),
            AquaelPanelConsentSwitch(coordinator),
        ])
    async_add_entities(entities)


class AquaelBaseSwitch(AquaelEntity, SwitchEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = icon

    @property
    def is_on(self):
        return bool(self._get(self._key))


class AquaelSocketSwitch(AquaelBaseSwitch):
    def __init__(self, coordinator, output):
        self.output = output
        super().__init__(coordinator, f"output_{output}", f"Wyjscie {output}", "mdi:power-socket-eu")

    async def async_turn_on(self, **kwargs):
        self.coordinator.assert_manual_mode()
        await self.coordinator.async_set_socket_output(self.output, True)

    async def async_turn_off(self, **kwargs):
        self.coordinator.assert_manual_mode()
        await self.coordinator.async_set_socket_output(self.output, False)


class AquaelAutoModeSwitch(AquaelBaseSwitch):
    def __init__(self, coordinator):
        super().__init__(coordinator, "alarms_enabled", "Tryb automatyczny", "mdi:calendar-clock")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command_expect("A_ON", "AON")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command_expect("A_OFF", "AOFF")


class AquaelHypermaxModuleSwitch(AquaelBaseSwitch):
    def __init__(self, coordinator, key, name, icon, module):
        self.module = module
        super().__init__(coordinator, key, name, icon)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_hypermax_module_state(self.module, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_hypermax_module_state(self.module, False)


class AquaelHypermaxNotifySwitch(AquaelEntity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Powiadomienia Hypermax"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_heater_notify"
        self._attr_icon = "mdi:bell-ring"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return self._get("heater_notify_state") == "On"

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_hypermax_notification(state="On")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_hypermax_notification(state="Off")


class AquaelNotificationSwitch(AquaelBaseSwitch):
    def __init__(self, coordinator):
        super().__init__(coordinator, "notification_enabled", "Powiadomienia", "mdi:bell-ring")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_range_settings(notification_enabled=True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_range_settings(notification_enabled=False)


class AquaelPanelConsentSwitch(AquaelBaseSwitch):
    def __init__(self, coordinator):
        super().__init__(coordinator, CONF_ADD_TO_PANEL, "Panel Aquael Link", "mdi:view-dashboard")
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return bool(self.coordinator.config_entry.data.get(CONF_ADD_TO_PANEL))

    async def async_turn_on(self, **kwargs):
        await self._set_consent(True)
        from . import _async_register_panel, _domain_data

        await _async_register_panel(self.hass, _domain_data(self.hass))

    async def async_turn_off(self, **kwargs):
        await self._set_consent(False)

    async def _set_consent(self, value):
        entry_data = dict(self.coordinator.config_entry.data)
        entry_data[CONF_ADD_TO_PANEL] = bool(value)
        self.hass.config_entries.async_update_entry(self.coordinator.config_entry, data=entry_data)
        self.async_write_ha_state()
