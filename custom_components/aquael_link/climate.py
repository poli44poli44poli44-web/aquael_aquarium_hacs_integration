from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import DOMAIN, TYPE_HYPERMAX
from .entity import AquaelEntity

HEATER_MIN_TEMP = 20.0
HEATER_MAX_TEMP = 33.0
HEATER_TEMP_STEP = 0.1


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    if coordinator.device_type == TYPE_HYPERMAX:
        async_add_entities([AquaelHypermaxThermostat(coordinator)])


class AquaelHypermaxThermostat(AquaelEntity, ClimateEntity):
    """HyperMAX heater exposed as a native HA thermostat (climate) entity.

    Uses the ``_attr_*`` push pattern (updated in ``_handle_coordinator_update``)
    rather than property overrides — in recent HA the climate value properties are
    cached_property and overriding them with a plain @property does not take effect.
    """

    _attr_name = "Termostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_min_temp = HEATER_MIN_TEMP
    _attr_max_temp = HEATER_MAX_TEMP
    _attr_target_temperature_step = HEATER_TEMP_STEP
    _attr_current_temperature = None
    _attr_target_temperature = None
    _attr_hvac_mode = HVACMode.OFF
    _attr_hvac_action = HVACAction.OFF
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_thermostat"
        self._apply_state()

    def _apply_state(self):
        self._attr_current_temperature = self._get("filter_current_temperature")
        self._attr_target_temperature = self._get("filter_static_temperature")
        enabled = self._get("thermostat_enabled")
        self._attr_hvac_mode = HVACMode.HEAT if enabled else HVACMode.OFF
        if not enabled:
            self._attr_hvac_action = HVACAction.OFF
        else:
            power = (self._get("top_heater_power") or 0) + (self._get("bottom_heater_power") or 0)
            self._attr_hvac_action = HVACAction.HEATING if power > 0 else HVACAction.IDLE

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._apply_state()

    def _handle_coordinator_update(self):
        self._apply_state()
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self):
        return {
            "top_heater_power": self._get("top_heater_power"),
            "bottom_heater_power": self._get("bottom_heater_power"),
            "heater_mode": self._get("heater_mode"),
            "pump_enabled": self._get("pump_enabled"),
            "water_sensor_flooded": self._get("water_sensor_flooded"),
        }

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._attr_target_temperature = max(
            HEATER_MIN_TEMP,
            min(HEATER_MAX_TEMP, round(float(temperature), 1)),
        )
        self.async_write_ha_state()
        success = await self.coordinator.async_set_hypermax_value(
            "FilterStaticTemperature", temperature
        )
        if not success:
            self._apply_state()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        enabled = hvac_mode == HVACMode.HEAT
        self._attr_hvac_mode = HVACMode.HEAT if enabled else HVACMode.OFF
        self._attr_hvac_action = HVACAction.IDLE if enabled else HVACAction.OFF
        self.async_write_ha_state()
        success = await self.coordinator.async_set_hypermax_module_state(
            "Heater", hvac_mode == HVACMode.HEAT
        )
        if not success:
            self._apply_state()
            self.async_write_ha_state()

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
