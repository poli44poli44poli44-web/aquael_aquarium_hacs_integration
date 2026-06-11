from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)

from .const import DOMAIN, TYPE_HYPERMAX, TYPE_LIGHT, TYPE_SOCKET, TYPE_THERMOMETER
from .entity import AquaelEntity

_D = SensorDeviceClass
_T = UnitOfTemperature

_TEMP_SAMPLE_KEYS = {"water", "ambient"}

_DIAG = [
    ("rssi",    "Sygnal WiFi",      SIGNAL_STRENGTH_DECIBELS_MILLIWATT, _D.SIGNAL_STRENGTH, "mdi:wifi",       True),
    ("ip_address", "Adres IP",      None, None, "mdi:ip-network",  True),
    ("mac",     "Adres MAC",        None, None, "mdi:network",     True),
    ("version", "Wersja firmware",  None, None, "mdi:chip",        True),
]

SENSORS_BY_TYPE = {
    TYPE_THERMOMETER: [
        ("water",   "Temperatura wody",      _T.CELSIUS, _D.TEMPERATURE, "mdi:thermometer-water",        False),
        ("ambient", "Temperatura otoczenia", _T.CELSIUS, _D.TEMPERATURE, "mdi:home-thermometer",         False),
        *_DIAG,
    ],
    TYPE_HYPERMAX: [
        ("filter_current_temperature", "Temperatura filtra",        _T.CELSIUS, _D.TEMPERATURE, "mdi:thermometer-water",  False),
        ("filter_static_temperature",  "Temperatura zadana filtra", _T.CELSIUS, _D.TEMPERATURE, "mdi:thermometer-check",  False),
        ("filter_static_efficiency",   "Wydajnosc filtra",          "%",        None,           "mdi:fan",                False),
        ("top_heater_power",    "Moc grzania - grzalka gorna",  "%", None, "mdi:radiator",          False),
        ("bottom_heater_power", "Moc grzania - grzalka dolna",  "%", None, "mdi:radiator",          False),
        ("heater_mode",         "Tryb grzania",   None, None, "mdi:tune-variant",   True),
        ("mode",               "Tryb",           None, None, "mdi:tune",           True),
        ("protocol",           "Protokol",       None, None, "mdi:lan",            True),
        ("water_sensor_flooded", "Czujnik zalania", None, None, "mdi:waves-arrow-up", False),
        *_DIAG,
    ],
    TYPE_SOCKET: [
        ("output_1_state", "Stan surowy wyjscia 1", None, None, "mdi:numeric", True),
        ("output_2_state", "Stan surowy wyjscia 2", None, None, "mdi:numeric", True),
        *_DIAG,
    ],
    TYPE_LIGHT: _DIAG,
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    definitions = SENSORS_BY_TYPE.get(coordinator.device_type, _DIAG)
    async_add_entities([AquaelLinkSensor(coordinator, *d) for d in definitions])


class AquaelLinkSensor(AquaelEntity, SensorEntity):
    def __init__(self, coordinator, key, name, unit, device_class, icon, diagnostic):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if unit and device_class in (_D.TEMPERATURE, _D.SIGNAL_STRENGTH):
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        value = self._get(self._key)
        if self._key == "water_sensor_flooded" and value is not None:
            return "tak" if bool(value) else "nie"
        return value

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._sync_display_unit()

    def _handle_coordinator_update(self):
        self._sync_display_unit()
        super()._handle_coordinator_update()

    def _sync_display_unit(self):
        if self._key not in _TEMP_SAMPLE_KEYS:
            return
        from homeassistant.helpers import entity_registry as er

        want = _T.FAHRENHEIT if self._get("notification_unit") == 1 else _T.CELSIUS
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return
        current = (entry.options.get("sensor") or {}).get("unit_of_measurement")
        if current != want:
            registry.async_update_entity_options(
                self.entity_id, "sensor", {"unit_of_measurement": want}
            )
