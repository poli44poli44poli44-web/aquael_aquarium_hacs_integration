import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS

from .const import (
    CONF_ADD_TO_PANEL,
    CONF_DEVICE_CHOICE,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    DEFAULT_NAME,
    DEVICE_TYPES,
    DOMAIN,
    TYPE_UNKNOWN,
)
from .coordinator import discover_devices

_LOGGER = logging.getLogger(__name__)

MANUAL = "__manual__"


class AquaelLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            choice = user_input.get(CONF_DEVICE_CHOICE, MANUAL)
            add_to_panel = bool(user_input.get(CONF_ADD_TO_PANEL))
            if choice == MANUAL:
                ip = user_input.get(CONF_IP_ADDRESS)
                if not ip:
                    errors["base"] = "ip_required"
                else:
                    discovered = await self.hass.async_add_executor_job(discover_devices, 1.2, (ip,))
                    device = discovered.get(ip)
                    if device is None and len(discovered) == 1:
                        ip, device = next(iter(discovered.items()))
                    if device is None or device["type"] == TYPE_UNKNOWN:
                        errors["base"] = "cannot_detect_device_type"
                    else:
                        device_type = device["type"]
                        device_name = user_input.get(CONF_DEVICE_NAME) or device["name"] or DEFAULT_NAME
                        return await self._create(ip, device_name, device_type, add_to_panel)
            else:
                ip, device_type, device_name = choice.split("|", 2)
                return await self._create(ip, device_name, device_type, add_to_panel)

        devices = await self.hass.async_add_executor_job(discover_devices)
        options = {MANUAL: "Dodaj ręcznie"}
        for ip, info in devices.items():
            label = DEVICE_TYPES.get(info["type"], info["type"])
            options[f"{ip}|{info['type']}|{info['name']}"] = f"{info['name']} ({ip}, {label})"

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_CHOICE, default=MANUAL): vol.In(options),
                vol.Optional(CONF_IP_ADDRESS): str,
                vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_ADD_TO_PANEL, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _create(self, ip, device_name, device_type, add_to_panel=False):
        _LOGGER.info("Creating Aquael Link entry: %s %s %s", device_type, device_name, ip)
        await self.async_set_unique_id(f"{device_type}_{device_name}_{ip}")
        self._abort_if_unique_id_configured(updates={CONF_IP_ADDRESS: ip})
        return self.async_create_entry(
            title=device_name,
            data={
                CONF_IP_ADDRESS: ip,
                CONF_DEVICE_NAME: device_name,
                CONF_DEVICE_TYPE: device_type,
                CONF_ADD_TO_PANEL: add_to_panel,
            },
        )
