from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGBW_COLOR, ColorMode, LightEntity

from .const import DOMAIN, TYPE_LIGHT
from .entity import AquaelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    if coordinator.device_type == TYPE_LIGHT:
        async_add_entities([AquaelSlimLight(coordinator)])


class AquaelSlimLight(AquaelEntity, LightEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Światło"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_light"
        self._attr_supported_color_modes = {ColorMode.RGBW}
        self._attr_color_mode = ColorMode.RGBW

    @property
    def is_on(self):
        return any((self._get("red", 0), self._get("blue", 0), self._get("white", 0)))

    @property
    def brightness(self):
        level = max(self._get("red", 0) or 0, self._get("blue", 0) or 0, self._get("white", 0) or 0)
        return round(level * 255 / 100)

    @property
    def rgbw_color(self):
        return (
            round((self._get("red",   0) or 0) * 255 / 100),
            0,
            round((self._get("blue",  0) or 0) * 255 / 100),
            round((self._get("white", 0) or 0) * 255 / 100),
        )

    async def async_turn_on(self, **kwargs):
        red   = self._get("red",   100) or 0
        blue  = self._get("blue",  100) or 0
        white = self._get("white", 100) or 0
        if ATTR_RGBW_COLOR in kwargs:
            color = kwargs[ATTR_RGBW_COLOR]
            red   = round(color[0] * 100 / 255)
            blue  = round(color[2] * 100 / 255)
            white = round(color[3] * 100 / 255)
        elif ATTR_BRIGHTNESS in kwargs:
            level = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            if not any((red, blue, white)):
                red = blue = white = level
            else:
                scale = level / max(red, blue, white)
                red   = round(red   * scale)
                blue  = round(blue  * scale)
                white = round(white * scale)
        await self.coordinator.async_set_light_channels(red, blue, white)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_light_channels(0, 0, 0)
