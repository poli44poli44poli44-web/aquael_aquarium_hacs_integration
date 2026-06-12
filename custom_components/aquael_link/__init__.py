import logging
import threading
from pathlib import Path

import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_ADD_TO_PANEL, CONF_DEVICE_TYPE, DOMAIN, TYPE_HYPERMAX, TYPE_THERMOMETER
from .coordinator import AquaelLinkCoordinator, discover_devices

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "aquael-link"
PANEL_STATIC_URL = f"/{DOMAIN}_panel"


PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.LIGHT,
    Platform.TEXT,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.CLIMATE,
]


def _domain_data(hass):
    return hass.data.setdefault(
        DOMAIN,
        {
            "coordinators": {},
            "lock": threading.Lock(),
            "ws_registered": False,
            "panel_registered": False,
        },
    )


async def async_setup_entry(hass: HomeAssistant, entry):
    data = _domain_data(hass)
    _async_register_websocket(hass, data)

    coordinator = AquaelLinkCoordinator(hass, entry, data["lock"])
    data["coordinators"][entry.entry_id] = coordinator
    if entry.data.get(CONF_ADD_TO_PANEL) and entry.data.get(CONF_DEVICE_TYPE) in (TYPE_THERMOMETER, TYPE_HYPERMAX):
        await _async_register_panel(hass, data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()
    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        _domain_data(hass)["coordinators"].pop(entry.entry_id, None)
    return unloaded


def _async_register_websocket(hass: HomeAssistant, data: dict):
    if data["ws_registered"]:
        return
    websocket_api.async_register_command(hass, websocket_get_schedules)
    websocket_api.async_register_command(hass, websocket_set_schedule_group)
    websocket_api.async_register_command(hass, websocket_discover_devices)
    websocket_api.async_register_command(hass, websocket_get_panel_devices)
    websocket_api.async_register_command(hass, websocket_set_pin)
    data["ws_registered"] = True


async def _async_register_panel(hass: HomeAssistant, data: dict):
    if data["panel_registered"]:
        return
    data["panel_registered"] = True
    frontend_path = Path(__file__).parent / "frontend"
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(PANEL_STATIC_URL, str(frontend_path), False)
        ])
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="aquael-link-panel-v6",
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title="Aquael Link",
            sidebar_icon="mdi:fishbowl-outline",
            module_url=f"{PANEL_STATIC_URL}/aquael-link-panel.js?v=20260612-thermometer-assets-017-v1",
            embed_iframe=False,
            require_admin=False,
        )
    except ValueError as err:
        if f"Overwriting panel {PANEL_URL_PATH}" not in str(err):
            data["panel_registered"] = False
            raise
        _LOGGER.debug("Aquael Link panel is already registered")


@websocket_api.websocket_command({vol.Required("type"): "aquael_link/discover"})
@websocket_api.async_response
async def websocket_discover_devices(hass, connection, msg):
    discovered = await hass.async_add_executor_job(discover_devices)
    devices = [
        {
            "ip": ip,
            "name": info.get("name"),
            "type": info.get("type"),
        }
        for ip, info in sorted(discovered.items())
    ]
    connection.send_result(msg["id"], {"devices": devices})


@websocket_api.websocket_command({vol.Required("type"): "aquael_link/panel_devices"})
@websocket_api.async_response
async def websocket_get_panel_devices(hass, connection, msg):
    devices = []
    coordinators = hass.data.get(DOMAIN, {}).get("coordinators", {})
    registry = er.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not entry.data.get(CONF_ADD_TO_PANEL):
            continue
        device_type = entry.data.get(CONF_DEVICE_TYPE)
        if device_type not in (TYPE_THERMOMETER, TYPE_HYPERMAX):
            continue
        coordinator = coordinators.get(entry.entry_id)
        ip = coordinator.ip if coordinator else entry.data.get(CONF_IP_ADDRESS)
        name, original_identifier = _panel_names_for_entry(entry, coordinator)
        device = {
            "entry_id": entry.entry_id,
            "name": name,
            "original_identifier": original_identifier,
            "type": device_type,
            "ip": ip,
        }
        if device_type == TYPE_THERMOMETER:
            device["chart_url"] = (
                f"{PANEL_STATIC_URL}/aquael_thermometer/index.html"
                f"?v=20260612-thermometer-assets-017-v1&ip={ip}"
            )
        elif device_type == TYPE_HYPERMAX:
            device["chart_url"] = f"{PANEL_STATIC_URL}/aquael_hypermax/chart.html?ip={ip}&v=20260610-chart-nullguard-v1"
            device["entities"] = _panel_entities_for_entry(registry, entry.entry_id)
            if coordinator and coordinator.data:
                device["pin_state"] = coordinator.data.get("display_pin_state")
                device["pin_code"] = coordinator.data.get("display_pin_code")
        devices.append(device)
    devices.sort(
        key=lambda device: (
            {TYPE_HYPERMAX: 0, TYPE_THERMOMETER: 1}.get(device["type"], 99),
            device.get("original_identifier") or device.get("name") or "",
        )
    )
    connection.send_result(msg["id"], {"devices": devices})


def _panel_names_for_entry(entry, coordinator):
    data = (coordinator and coordinator.data) or {}
    candidates = [
        data.get("device_identifier"),
        data.get("device_name"),
        coordinator.device_name if coordinator else None,
        entry.title,
    ]
    original = next((value for value in candidates if _looks_like_aquael_identifier(value)), None)
    if not original:
        original = entry.title

    custom_candidates = [
        data.get("user_device_name"),
        coordinator.device_name if coordinator else None,
        entry.title,
    ]
    custom = next(
        (
            value
            for value in custom_candidates
            if value and value != "nic" and value != original and not _looks_like_aquael_identifier(value)
        ),
        None,
    )
    return custom or original, original


def _looks_like_aquael_identifier(value):
    if not value:
        return False
    return str(value).startswith(("HYPERMAX_", "THERMOMETER_", "LIGHT_", "SOCKET_DUO_"))


def _panel_entities_for_entry(registry, entry_id):
    wanted = {
        "climate": {
            "thermostat": "_thermostat",
        },
        "switch": {
            "pump": "_pump_enabled",
            "thermostat_switch": "_thermostat_enabled",
            "notify": "_heater_notify",
        },
        "text": {
            "name": "_device_name_text",
        },
        "number": {
            "target_temperature": "_filter_static_temperature_number",
            "filter_efficiency": "_filter_static_efficiency_number",
            "temp_offset": "_heater_temperature_offset_number",
            "notify_min": "_heater_notify_min_number",
            "notify_max": "_heater_notify_max_number",
        },
        "button": {
            "identify": "_identify",  # unique_id: {entry_id}_identify
        },
        "sensor": {
            "current_temperature": "_filter_current_temperature",
            "target_temperature": "_filter_static_temperature",
            "filter_efficiency": "_filter_static_efficiency",
            "water_sensor_flooded": "_water_sensor_flooded",
            "top_heater_power": "_top_heater_power",
            "bottom_heater_power": "_bottom_heater_power",
            "heater_mode": "_heater_mode",
            "rssi": "_rssi",
            "ip_address": "_ip_address",
            "mac": "_mac",
            "version": "_version",
        },
    }
    entities = {}
    for entity in registry.entities.values():
        if entity.config_entry_id != entry_id:
            continue
        domain = entity.entity_id.split(".", 1)[0]
        by_domain = wanted.get(domain)
        if not by_domain:
            continue
        for key, suffix in by_domain.items():
            if entity.unique_id.endswith(suffix):
                entities[key] = entity.entity_id
    return entities


@websocket_api.websocket_command(
    {
        vol.Required("type"): "aquael_link/set_pin",
        vol.Required("entry_id"): str,
        vol.Required("enabled"): bool,
        vol.Optional("code"): str,
    }
)
@websocket_api.async_response
async def websocket_set_pin(hass, connection, msg):
    coordinator = hass.data.get(DOMAIN, {}).get("coordinators", {}).get(msg["entry_id"])
    if coordinator is None or not hasattr(coordinator, "async_set_hypermax_pin"):
        connection.send_error(msg["id"], "not_found", "Aquael Link device not found")
        return
    code = msg.get("code")
    if msg["enabled"] and (code is None or not (code.isdigit() and len(code) == 6)):
        connection.send_error(msg["id"], "invalid_pin", "PIN must be exactly 6 digits")
        return
    success = await coordinator.async_set_hypermax_pin(msg["enabled"], code)
    connection.send_result(msg["id"], {"success": bool(success)})


@websocket_api.websocket_command({vol.Required("type"): "aquael_link/schedules"})
@websocket_api.async_response
async def websocket_get_schedules(hass, connection, msg):
    devices = []
    for entry_id, coordinator in hass.data.get(DOMAIN, {}).get("coordinators", {}).items():
        schedules = await coordinator.async_fetch_schedules()
        devices.append(
            {
                "entry_id": entry_id,
                "name": coordinator.device_name,
                "type": coordinator.device_type,
                "ip": coordinator.ip,
                "schedules": schedules,
            }
        )
    connection.send_result(msg["id"], {"devices": devices})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "aquael_link/set_schedule_group",
        vol.Required("entry_id"): str,
        vol.Required("group"): str,
        vol.Required("entries"): list,
    }
)
@websocket_api.async_response
async def websocket_set_schedule_group(hass, connection, msg):
    coordinator = hass.data.get(DOMAIN, {}).get("coordinators", {}).get(msg["entry_id"])
    if coordinator is None or not hasattr(coordinator, "async_set_schedule_group"):
        connection.send_error(msg["id"], "not_found", "Aquael Link device not found")
        return
    success = await coordinator.async_set_schedule_group(msg["group"], msg["entries"])
    if not success:
        connection.send_error(msg["id"], "write_failed", "Schedule write failed")
        return
    schedules = await coordinator.async_fetch_schedules()
    connection.send_result(msg["id"], {"schedules": schedules})
