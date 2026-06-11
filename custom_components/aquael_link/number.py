from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TYPE_HYPERMAX, TYPE_LIGHT, TYPE_THERMOMETER
from .entity import AquaelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    entities = []
    if coordinator.device_type == TYPE_LIGHT:
        entities.extend([
            AquaelLightChannelNumber(coordinator, "red",   "Kanal czerwony"),
            AquaelLightChannelNumber(coordinator, "blue",  "Kanal niebieski"),
            AquaelLightChannelNumber(coordinator, "white", "Kanal bialy"),
        ])
    if coordinator.device_type == TYPE_HYPERMAX:
        entities.extend([
            AquaelHypermaxNumber(coordinator, "FilterStaticTemperature", "filter_static_temperature", "Temperatura zadana filtra", UnitOfTemperature.CELSIUS, 20,  33,  0.1),
            AquaelHypermaxNumber(coordinator, "FilterStaticEfficiency",  "filter_static_efficiency",  "Wydajnosc filtra",          "%",                       20,  100, 1),
            AquaelHypermaxTempOffsetNumber(coordinator),
            AquaelHypermaxNotifyNumber(coordinator, "heater_notify_min", "min_temp", "Powiadomienie: prog dolny"),
            AquaelHypermaxNotifyNumber(coordinator, "heater_notify_max", "max_temp", "Powiadomienie: prog gorny"),
        ])
    if coordinator.device_type == TYPE_THERMOMETER:
        entities.extend([
            AquaelThermometerCalibrationNumber(coordinator, "cal_water",   "Kalibracja czujnika wody"),
            AquaelThermometerCalibrationNumber(coordinator, "cal_ambient", "Kalibracja czujnika otoczenia"),
            AquaelThermometerRangeNumber(coordinator, "range_down", "Powiadomienia: prog dolny"),
            AquaelThermometerRangeNumber(coordinator, "range_up",   "Powiadomienia: prog gorny"),
        ])
    async_add_entities(entities)


class AquaelBaseNumber(AquaelEntity, NumberEntity):
    def __init__(self, coordinator, key, name, unit, min_value, max_value, step):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}_number"
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_mode = NumberMode.BOX
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self):
        return self._get(self._key)


class AquaelLightChannelNumber(AquaelBaseNumber):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name, "%", 0, 100, 1)

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_light_channels(**{self._key: value})


class AquaelHypermaxNumber(AquaelBaseNumber):
    def __init__(self, coordinator, command_key, data_key, name, unit, min_value, max_value, step):
        super().__init__(coordinator, data_key, name, unit, min_value, max_value, step)
        self._command_key = command_key

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_hypermax_value(self._command_key, value)


class _AquaelTempUnitNumber(AquaelBaseNumber):
    """Number that follows the device unit selection (°C/°F).

    Device always stores Celsius; these entities convert for display and convert
    user input back to Celsius before writing. No device_class is set, so HA does
    not auto-convert — the conversion here is the single source of truth.
    """

    def _is_fahrenheit(self):
        return self._get("notification_unit") == 1

    def _to_display(self, celsius):
        raise NotImplementedError

    def _from_display(self, value):
        raise NotImplementedError

    @property
    def native_unit_of_measurement(self):
        return UnitOfTemperature.FAHRENHEIT if self._is_fahrenheit() else UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        value = self._get(self._key)
        if value is None:
            return None
        return round(self._to_display(value), 1)


class AquaelThermometerCalibrationNumber(_AquaelTempUnitNumber):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name, UnitOfTemperature.CELSIUS, -5.0, 5.0, 0.1)
        self._attr_entity_category = None

    def _to_display(self, celsius):
        return celsius * 9 / 5 if self._is_fahrenheit() else celsius

    def _from_display(self, value):
        return value * 5 / 9 if self._is_fahrenheit() else value

    @property
    def native_min_value(self):
        return -9.0 if self._is_fahrenheit() else -5.0

    @property
    def native_max_value(self):
        return 9.0 if self._is_fahrenheit() else 5.0

    async def async_set_native_value(self, value):
        celsius = self._from_display(value)
        if self._key == "cal_water":
            await self.coordinator.async_set_calibration(water=celsius)
        else:
            await self.coordinator.async_set_calibration(ambient=celsius)


class AquaelThermometerRangeNumber(_AquaelTempUnitNumber):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name, UnitOfTemperature.CELSIUS, 0.0, 80.0, 0.1)

    def _to_display(self, celsius):
        return celsius * 9 / 5 + 32 if self._is_fahrenheit() else celsius

    def _from_display(self, value):
        return (value - 32) * 5 / 9 if self._is_fahrenheit() else value

    @property
    def native_min_value(self):
        base = 0.0
        if self._key == "range_up":
            low = self._get("range_down")
            if low is not None:
                base = max(0.0, float(low))
        return round(self._to_display(base), 1)

    @property
    def native_max_value(self):
        base = 80.0
        if self._key == "range_down":
            high = self._get("range_up")
            if high is not None:
                base = min(80.0, float(high))
        return round(self._to_display(base), 1)

    async def async_set_native_value(self, value):
        celsius = self._from_display(value)
        await self.coordinator.async_set_range_settings(**{self._key: celsius})


class AquaelHypermaxTempOffsetNumber(AquaelBaseNumber):
    def __init__(self, coordinator):
        super().__init__(coordinator, "heater_temperature_offset", "Przesuniecie temperatury", UnitOfTemperature.CELSIUS, -5.0, 5.0, 0.1)
        self._attr_entity_category = None

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_hypermax_temp_offset(value)


class AquaelHypermaxNotifyNumber(AquaelBaseNumber):
    def __init__(self, coordinator, data_key, cmd_key, name):
        super().__init__(coordinator, data_key, name, UnitOfTemperature.CELSIUS, 15.0, 35.0, 0.1)
        self._cmd_key = cmd_key

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_hypermax_notification(**{self._cmd_key: value})
