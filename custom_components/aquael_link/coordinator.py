import json
import logging
import re
import socket
import time
from datetime import timedelta
from ipaddress import ip_address

from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    DEVICE_TYPES,
    DOMAIN,
    HYPERMAX_GET_KEYS,
    LEGACY_NAME_COMMANDS,
    TYPE_HYPERMAX,
    TYPE_LIGHT,
    TYPE_SOCKET,
    TYPE_THERMOMETER,
    TYPE_UNKNOWN,
    UDP_PORT,
)
from .schedules import GROUPS as SCHEDULE_GROUPS, decode_schedules, encode_command

_LOGGER = logging.getLogger(__name__)

DISCOVERY_COMMAND = "NAME?"
DISCOVERY_TIMEOUT = 1.2
SOCKET_UPDATE_INTERVAL = 60
DEFAULT_UPDATE_INTERVAL = 5
UDP_COMMAND_ATTEMPTS = 3
UDP_COMMAND_RETRY_DELAY = 0.15
LIGHT_DEFAULT_POWER_LIMIT_W = 36.0
LIGHT_CHANNEL_POWER_W = {
    "white": 37.0,
    "blue": 6.22,
    "red": 8.7,
}
LIGHT_PRESETS = {
    "plant": {"white": 56, "blue": 100, "red": 100},
    "sunny": {"white": 97, "blue": 0, "red": 0},
    "marine": {"white": 80, "blue": 100, "red": 0},
}


def _format_udp_payload(payload):
    if payload is None:
        return "<none>"
    if isinstance(payload, str):
        return repr(payload)
    if isinstance(payload, (bytes, bytearray, memoryview)):
        payload_bytes = bytes(payload)
        text = _decode_packet(payload_bytes)
        hex_payload = payload_bytes.hex(" ")
        if text:
            return f"{text!r} hex={hex_payload}"
        return f"hex={hex_payload}"
    return repr(payload)


def _payload_size(payload):
    try:
        return len(payload)
    except TypeError:
        return "?"


def _decode_packet(data):
    return bytes(data).decode("utf-8", errors="ignore").strip("\x00\r\n ")


def _looks_like_aquael_identifier(value):
    if not value:
        return False
    return str(value).startswith(("HYPERMAX_", "THERMOMETER_", "LIGHT_", "SOCKET_DUO_"))


def _hypermax_identifier(data, fallback=None):
    if _looks_like_aquael_identifier(fallback):
        return fallback
    mac = data.get("MAC_WiFi")
    if mac:
        suffix = str(mac).replace(":", "")[-6:].upper()
        if suffix:
            return f"HYPERMAX_{suffix}"
    return fallback


def _broadcast_targets(seed_ips=None):
    targets = {"255.255.255.255", "<broadcast>"}
    for seed_ip in seed_ips or ():
        try:
            addr = ip_address(seed_ip)
        except ValueError:
            continue
        if addr.version == 4:
            parts = str(addr).split(".")
            targets.add(".".join([parts[0], parts[1], parts[2], "255"]))
    return targets


def classify_device(name):
    raw_value = str(name or "").strip()
    value = raw_value.upper()
    if value.startswith("LIGHT_"):
        return TYPE_LIGHT
    if value.startswith(("SOCKET_", "SOCKET_DUO_")):
        return TYPE_SOCKET
    if value.startswith(("THERMOMETER_", "THERM_", "TERMOMETR_")):
        return TYPE_THERMOMETER
    if value.startswith(("HYPERMAX_", "HYPERMAX")):
        return TYPE_HYPERMAX
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        device_name = str(payload.get("DeviceName") or payload.get("UserDeviceName") or "")
        return classify_device(device_name)

    if "LIGHT" in value:
        return TYPE_LIGHT
    if "SOCKET" in value or "GNIAZD" in value:
        return TYPE_SOCKET
    if "THERM" in value or "TERM" in value or "TEMP" in value:
        return TYPE_THERMOMETER
    if "HYPER" in value or "ECU" in value or "MAX" in value:
        return TYPE_HYPERMAX
    return TYPE_UNKNOWN


def _socket_output_is_on(raw_state):
    value = _parse_int(raw_state)
    if value is None:
        return None
    return value not in (0, 8, 16, 64, 128)



SOCKET_MANUAL_COMMANDS = {
    1: {
        "off":     ("PWM_SET:0", "PWMOK",  16),
        "on":      ("PWM_SET:1", "PWMOK",  32),
        "sunny":   ("MAN:004",   "MANOK",   4),
        "sunrise": ("MAN:002",   "MANOK",   2),
        "lunar":   ("MAN:001",   "MANOK",   1),
    },
    2: {
        "off":     ("PWM_SET2:0", "PWM2OK", 16),
        "on":      ("PWM_SET2:1", "PWM2OK", 32),
        "sunny":   ("MAN:020",    "MANOK",  20),
        "sunrise": ("MAN:018",    "MANOK",  18),
        "lunar":   ("MAN:017",    "MANOK",  17),
    },
}


def _socket_manual_mode(output, raw_state):
    value = _parse_int(raw_state)
    if value is None:
        return None
    if output == 1:
        if value in (1,):
            return "lunar"
        if value in (2,):
            return "sunrise"
        if value in (4,):
            return "sunny"
        return "on" if _socket_output_is_on(value) else "off"
    if value in (17,):
        return "lunar"
    if value in (18,):
        return "sunrise"
    if value in (20,):
        return "sunny"
    return "on" if _socket_output_is_on(value) else "off"


def discover_devices(timeout=DISCOVERY_TIMEOUT, seed_ips=None):
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)
    try:
        sock.bind(("", UDP_PORT))
        for target in _broadcast_targets(seed_ips):
            try:
                payload = DISCOVERY_COMMAND.encode()
                _LOGGER.debug(
                    "Aquael Link UDP discovery TX %s:%s payload=%s bytes=%s timeout=%.2fs",
                    target,
                    UDP_PORT,
                    _format_udp_payload(payload),
                    len(payload),
                    timeout,
                )
                sock.sendto(payload, (target, UDP_PORT))
            except OSError as err:
                _LOGGER.debug("Aquael Link discovery to %s failed: %s", target, err)

        end_time = time.monotonic() + timeout
        while time.monotonic() < end_time:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            _LOGGER.debug(
                "Aquael Link UDP discovery RX %s:%s payload=%s bytes=%s",
                addr[0],
                addr[1],
                _format_udp_payload(data),
                len(data),
            )
            response = _decode_packet(data)
            if not response or response == DISCOVERY_COMMAND:
                continue
            device_type = classify_device(response)
            found[addr[0]] = {"name": response, "type": device_type}
    finally:
        sock.close()
    return found


def _parse_int(value):
    if value is None:
        return None
    match = re.search(r"-?\d+", str(value))
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _light_wire_to_percent(value):
    if value is None:
        return None
    return max(0, min(100, int(round(value / 2))))


def _light_percent_to_wire(value):
    return max(0, min(200, int(round(value * 2))))


def _light_power_limit_w(device_name):
    match = re.search(r"-\s*(32|36)\s*w\b", str(device_name or ""), re.IGNORECASE)
    if match:
        return float(match.group(1))
    return LIGHT_DEFAULT_POWER_LIMIT_W


def _light_power_w(red, blue, white):
    return (
        white * LIGHT_CHANNEL_POWER_W["white"] / 100
        + blue * LIGHT_CHANNEL_POWER_W["blue"] / 100
        + red * LIGHT_CHANNEL_POWER_W["red"] / 100
    )


def _light_safe_preset_values(preset, power_limit):
    values = dict(LIGHT_PRESETS[preset])
    while values["white"] > 0 and _light_power_w(values["red"], values["blue"], values["white"]) > power_limit:
        values["white"] -= 1
    return values


def _hypermax_module_is_on(module_state, module):
    if not isinstance(module_state, dict):
        return None
    value = module_state.get(module)
    if isinstance(value, dict):
        value = value.get("State")
    if value is None:
        return None
    return str(value).strip().lower() == "on"


def _decode_legacy_name_response(response):
    if response and response.startswith("SNA?") and response.endswith("XDX"):
        name = response[4:-3]
        return "" if name == "nic" else name
    return None


class AquaelLinkCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, lock):
        self.config_entry = entry
        self.ip = entry.data[CONF_IP_ADDRESS]
        self.device_name = entry.data.get(CONF_DEVICE_NAME) or self.ip
        self.device_type = entry.data.get(CONF_DEVICE_TYPE, TYPE_UNKNOWN)
        self.lock = lock
        self._fail_streak = 0
        self._poll_attempts = None  # override for UDP retries during polls
        self._got_response = False  # any packet from target during current fetch
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=SOCKET_UPDATE_INTERVAL if self.device_type == TYPE_SOCKET else DEFAULT_UPDATE_INTERVAL
            ),
        )

    @property
    def model_name(self):
        return DEVICE_TYPES.get(self.device_type, DEVICE_TYPES[TYPE_UNKNOWN])

    def _discover_target_ip(self, force=False):
        if not force and self.ip and self.device_type != TYPE_UNKNOWN:
            return self.ip, None

        devices = discover_devices(seed_ips=(self.ip,))
        network_name = self.config_entry.title  # e.g. "SOCKET_DUO_69D401"
        for ip, info in devices.items():
            if info["name"] == network_name:
                return ip, info
        for ip, info in devices.items():
            if info["name"] == self.device_name:
                return ip, info
        if self.ip in devices:
            return self.ip, devices[self.ip]
        if len(devices) == 1:
            ip, info = next(iter(devices.items()))
            if self.device_type in (TYPE_UNKNOWN, info["type"]):
                return ip, info
        return self.ip, None

    def _open_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.5)
        sock.bind(("", UDP_PORT))
        return sock

    def _clean_socket(self, sock):
        sock.settimeout(0.03)
        try:
            while True:
                data, addr = sock.recvfrom(4096)
                _LOGGER.debug(
                    "Aquael Link UDP drain RX %s:%s payload=%s bytes=%s",
                    addr[0],
                    addr[1],
                    _format_udp_payload(data),
                    len(data),
                )
        except (socket.timeout, BlockingIOError):
            pass
        sock.settimeout(1.5)

    def _send_receive(self, sock, command, target_ip, timeout=1.5, expected_prefixes=None):
        self._clean_socket(sock)
        payload = command.encode("utf-8") if isinstance(command, str) else command
        if isinstance(expected_prefixes, str):
            expected_prefixes = (expected_prefixes,)
        started = time.monotonic()
        deadline = started + timeout
        _LOGGER.debug(
            "Aquael Link UDP TX %s:%s payload=%s bytes=%s timeout=%.2fs",
            target_ip,
            UDP_PORT,
            _format_udp_payload(payload),
            _payload_size(payload),
            timeout,
        )
        sock.sendto(payload, (target_ip, UDP_PORT))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("timed out")
            sock.settimeout(remaining)
            data, addr = sock.recvfrom(4096)
            elapsed = time.monotonic() - started
            _LOGGER.debug(
                "Aquael Link UDP RX %s:%s payload=%s bytes=%s elapsed=%.3fs%s",
                addr[0],
                addr[1],
                _format_udp_payload(data),
                len(data),
                elapsed,
                "" if addr[0] == target_ip else " ignored=unexpected_source",
            )
            if addr[0] == target_ip:
                self._got_response = True
                decoded = _decode_packet(data)
                if expected_prefixes:
                    if decoded.startswith(expected_prefixes):
                        return decoded
                    _LOGGER.debug(
                        "Aquael Link UDP RX %s:%s payload=%s ignored=unexpected_response expected=%s",
                        addr[0],
                        addr[1],
                        decoded,
                        expected_prefixes,
                    )
                    continue
                if self._is_discovery_noise(decoded):
                    continue
                return decoded

    def _is_discovery_noise(self, decoded):
        if not decoded:
            return False
        return decoded == "NAME?" or decoded == (self.config_entry.title or "")

    def _send_receive_raw(self, sock, command, target_ip, timeout=1.5):
        self._clean_socket(sock)
        payload = command.encode("latin1") if isinstance(command, str) else command
        started = time.monotonic()
        deadline = started + timeout
        _LOGGER.debug(
            "Aquael Link UDP RAW TX %s:%s payload=%s bytes=%s timeout=%.2fs",
            target_ip,
            UDP_PORT,
            _format_udp_payload(payload),
            _payload_size(payload),
            timeout,
        )
        sock.sendto(payload, (target_ip, UDP_PORT))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("timed out")
            sock.settimeout(remaining)
            data, addr = sock.recvfrom(4096)
            elapsed = time.monotonic() - started
            _LOGGER.debug(
                "Aquael Link UDP RAW RX %s:%s payload=%s bytes=%s elapsed=%.3fs%s",
                addr[0],
                addr[1],
                _format_udp_payload(data),
                len(data),
                elapsed,
                "" if addr[0] == target_ip else " ignored=unexpected_source",
            )
            if addr[0] == target_ip:
                return data.strip(b"\x00\r\n ")

    def _safe_send_receive(self, sock, command, target_ip, timeout=1.5, expected_prefixes=None):
        attempts = self._poll_attempts or UDP_COMMAND_ATTEMPTS
        for attempt in range(1, attempts + 1):
            try:
                return self._send_receive(sock, command, target_ip, timeout, expected_prefixes)
            except socket.timeout as err:
                _LOGGER.debug(
                    "Aquael Link UDP timeout %s:%s command=%s attempt=%s/%s timeout=%.2fs error=%s",
                    target_ip,
                    UDP_PORT,
                    _format_udp_payload(command),
                    attempt,
                    attempts,
                    timeout,
                    err,
                )
            except OSError as err:
                _LOGGER.debug(
                    "Aquael Link UDP error %s:%s command=%s attempt=%s/%s timeout=%.2fs error=%s",
                    target_ip,
                    UDP_PORT,
                    _format_udp_payload(command),
                    attempt,
                    attempts,
                    timeout,
                    err,
                )
                return None
            if attempt < attempts:
                time.sleep(UDP_COMMAND_RETRY_DELAY)
        return None

    def _fetch_hypermax(self, sock, target_ip):
        command = json.dumps({"Get": HYPERMAX_GET_KEYS}, separators=(",", ":"))
        response = self._safe_send_receive(sock, command, target_ip, 2.0, expected_prefixes="{")
        data = {}
        if response:
            try:
                payload = json.loads(response)
            except ValueError:
                payload = {}
            if isinstance(payload, dict):
                response_data = payload.get("GetResponse") or payload.get("Get")
                data.update(response_data if isinstance(response_data, dict) else payload)

        module_state = data.get("ModuleState")
        module_params = data.get("ModuleParameters") or {}
        heater_params = module_params.get("Heater") or {}
        display_params = module_params.get("Display") or {}
        display_pin = display_params.get("Pin") or {}
        module_notification = data.get("ModuleNotification") or {}
        heater_notification = module_notification.get("Heater") or {}
        module_mode = data.get("ModuleMode") or {}
        identifier = _hypermax_identifier(data, self.config_entry.title)
        user_device_name = data.get("UserDeviceName")

        current_temp = data.get("FilterCurrentTemperature")
        if isinstance(current_temp, (int, float)) and current_temp < -200:
            current_temp = None

        return {
            "ip_address": data.get("IP") or target_ip,
            "device_identifier": identifier,
            "device_name": user_device_name or identifier or self.device_name,
            "user_device_name": user_device_name,
            "device_type": TYPE_HYPERMAX,
            "mac": data.get("MAC_WiFi"),
            "rssi": data.get("WiFi_RSSI"),
            "version": data.get("FirmwareVersion"),
            "mode": data.get("Mode"),
            "protocol": data.get("Protocol"),
            "filter_static_temperature": data.get("FilterStaticTemperature"),
            "filter_static_efficiency": data.get("FilterStaticEfficiency"),
            "filter_current_temperature": current_temp,
            "water_sensor_flooded": data.get("WaterSensorFlooded"),
            "top_heater_power": heater_params.get("TopHeaterPower"),
            "bottom_heater_power": heater_params.get("BottomHeaterPower"),
            "heater_temperature_offset": heater_params.get("TemperatureOffset"),
            "display_pin_state": display_pin.get("State"),
            "display_pin_code": display_pin.get("Code"),
            "heater_notify_max": heater_notification.get("TemperatureMax"),
            "heater_notify_min": heater_notification.get("TemperatureMin"),
            "heater_notify_state": heater_notification.get("State"),
            "heater_mode": module_mode.get("Heater"),
            "pump_mode": module_mode.get("Pump"),
            "module_mode": module_mode,
            "module_state": module_state,
            "pump_enabled": _hypermax_module_is_on(module_state, "Pump"),
            "thermostat_enabled": _hypermax_module_is_on(module_state, "Heater"),
            "raw": data,
        }

    def _fetch_light(self, sock, target_ip):
        result = {"ip_address": target_ip, "device_type": TYPE_LIGHT}
        response = self._safe_send_receive(sock, "PWM_READ", target_ip, expected_prefixes="ALL:")
        if response and response.startswith("ALL:"):
            parts = response.split(":")
            if len(parts) >= 4:
                result["red"] = _light_wire_to_percent(_parse_int(parts[1]))
                result["blue"] = _light_wire_to_percent(_parse_int(parts[2]))
                result["white"] = _light_wire_to_percent(_parse_int(parts[3]))

        response = self._safe_send_receive(sock, "A_?", target_ip, expected_prefixes="ASTAT:")
        if response and response.startswith("ASTAT:"):
            result["alarms_enabled"] = response.split(":", 1)[1].strip().startswith("1")

        self._fetch_common_legacy(sock, target_ip, result, TYPE_LIGHT)
        return result

    def _fetch_thermometer(self, sock, target_ip):
        result = {"ip_address": target_ip, "device_type": TYPE_THERMOMETER}
        response = self._safe_send_receive(sock, "TMP_READ", target_ip, expected_prefixes="TMP:")
        if response and response.startswith("TMP:"):
            parts = response.split(":")
            if len(parts) >= 5:
                result["water"] = (_parse_int(parts[1]) or 0) / 10.0
                result["ambient"] = (_parse_int(parts[2]) or 0) / 10.0
                result["cal_water"] = ((_parse_int(parts[3]) or 50) - 50) / 10.0
                result["cal_ambient"] = ((_parse_int(parts[4]) or 50) - 50) / 10.0

        response = self._safe_send_receive(sock, "SOU?", target_ip, expected_prefixes="SOU?")
        if response and response.startswith("SOU?") and response.endswith("XDX"):
            result["water_name"] = response[4:-3]
            if result["water_name"] == "nic":
                result["water_name"] = ""

        response = self._safe_send_receive(sock, "SIN?", target_ip, expected_prefixes="SIN?")
        if response and response.startswith("SIN?") and response.endswith("XDX"):
            result["ambient_name"] = response[4:-3]
            if result["ambient_name"] == "nic":
                result["ambient_name"] = ""

        response = self._safe_send_receive(sock, "?RANGE", target_ip, expected_prefixes="RANGE|")
        if response and response.startswith("RANGE|"):
            self._parse_thermometer_range(response, result)

        self._fetch_common_legacy(sock, target_ip, result, TYPE_THERMOMETER)
        if "water" not in result:
            raise UpdateFailed(f"Brak danych temperatury z {target_ip}")
        return result

    def _fetch_socket(self, sock, target_ip):
        result = {"ip_address": target_ip, "device_type": TYPE_SOCKET}

        response = self._safe_send_receive(sock, "A_?", target_ip, expected_prefixes="ASTAT:")
        if response and response.startswith("ASTAT:"):
            result["alarms_enabled"] = response.split(":", 1)[1].strip().startswith("1")

        response = self._safe_send_receive(sock, "MAN?", target_ip, expected_prefixes="MAN:")
        if response and response.startswith("MAN:"):
            parts = response.split(":")
            if len(parts) >= 3:
                state_1 = _parse_int(parts[1])
                state_2 = _parse_int(parts[2])
                result["output_1_state"] = state_1
                result["output_2_state"] = state_2
                result["output_1"] = _socket_output_is_on(state_1)
                result["output_2"] = _socket_output_is_on(state_2)
                result["output_1_mode"] = _socket_manual_mode(1, state_1)
                result["output_2_mode"] = _socket_manual_mode(2, state_2)

        self._fetch_common_legacy(sock, target_ip, result, TYPE_SOCKET, fetch_id=False)
        return result

    def _fetch_common_legacy(self, sock, target_ip, result, device_type, fetch_id=True):
        if not self._got_response:
            result.setdefault("device_name", self.device_name)
            result["device_type"] = device_type
            return
        if fetch_id:
            response = self._safe_send_receive(
                sock,
                "ID?",
                target_ip,
                expected_prefixes=("THERMOMETER", "LIGHT", "SOCKET", "HYPERMAX"),
            )
            if response:
                result["device_identifier"] = response
                result["device_name"] = response
        response = self._safe_send_receive(sock, "SNA?", target_ip, expected_prefixes="SNA?")
        if response and response.startswith("SNA?") and response.endswith("XDX"):
            result["user_device_name"] = response[4:-3]
            result.setdefault("device_name", result["user_device_name"])
        response = self._safe_send_receive(sock, "RSSI", target_ip, expected_prefixes=("0RSSI:", "RSSI:"))
        if response and "RSSI:" in response:
            value = _parse_int(response.split("RSSI:", 1)[1])
            if value is not None:
                result["rssi"] = -abs(value)
        response = self._safe_send_receive(sock, "MAC?", target_ip, expected_prefixes="MAC:")
        if response and response.startswith("MAC:"):
            result["mac"] = response.split(":", 1)[1]
        response = self._safe_send_receive(sock, "VERSION?", target_ip, expected_prefixes="VER:")
        if response:
            result["version"] = response.replace("VER:", "").strip()
        result.setdefault("device_name", self.device_name)
        result["device_type"] = device_type

    def _parse_thermometer_range(self, response, result):
        try:
            _, payload, enabled, language, unit = response.split("|")
            result["range_down"] = int(payload[0:3]) / 10.0
            result["range_up"] = int(payload[3:6]) / 10.0
            result["notification_enabled"] = enabled == "1"
            result["notification_language"] = int(language)
            result["notification_unit"] = int(unit)
        except (ValueError, IndexError) as err:
            _LOGGER.debug("Cannot parse Aquael range response %s: %s", response, err)

    def _fetch_data(self):
        with self.lock:
            target_ip, discovered = self._discover_target_ip()
            if discovered:
                if self.device_type == TYPE_UNKNOWN and discovered["type"] != TYPE_UNKNOWN:
                    self.device_type = discovered["type"]
                if discovered["name"]:
                    self.device_name = discovered["name"]

            try:
                sock = self._open_socket()
            except OSError as err:
                raise UpdateFailed(f"UDP port {UDP_PORT} is busy: {err}") from err

            self._poll_attempts = 1
            self._got_response = False
            try:
                if self.device_type == TYPE_THERMOMETER:
                    data = self._fetch_thermometer(sock, target_ip)
                elif self.device_type == TYPE_HYPERMAX:
                    data = self._fetch_hypermax(sock, target_ip)
                elif self.device_type == TYPE_LIGHT:
                    data = self._fetch_light(sock, target_ip)
                elif self.device_type == TYPE_SOCKET:
                    data = self._fetch_socket(sock, target_ip)
                else:
                    raise UpdateFailed("Nieznany typ urządzenia. Wybierz typ ręcznie w integracji.")
            finally:
                self._poll_attempts = None
                sock.close()

            if not data or not self._got_response:
                raise UpdateFailed(f"Brak odpowiedzi z {target_ip}")
            return data

    def _default_interval_seconds(self):
        return SOCKET_UPDATE_INTERVAL if self.device_type == TYPE_SOCKET else DEFAULT_UPDATE_INTERVAL

    async def _async_update_data(self):
        try:
            data = await self.hass.async_add_executor_job(self._fetch_data)
        except UpdateFailed:
            self._fail_streak += 1
            backoff = min(300, self._default_interval_seconds() * (2 ** min(self._fail_streak, 6)))
            self.update_interval = timedelta(seconds=max(30, backoff))
            raise
        if self._fail_streak:
            self._fail_streak = 0
            self.update_interval = timedelta(seconds=self._default_interval_seconds())
        new_ip = data.get("ip_address")
        new_identifier = data.get("device_identifier")
        new_name = data.get("user_device_name") or data.get("device_name")
        new_type = data.get("device_type")
        if new_ip or new_name or new_type or new_identifier:
            entry_data = dict(self.config_entry.data)
            changed = False
            title = None
            if new_ip and new_ip != self.ip:
                self.ip = new_ip
                entry_data[CONF_IP_ADDRESS] = new_ip
                changed = True
            if new_name and new_name != self.device_name:
                self.device_name = new_name
                entry_data[CONF_DEVICE_NAME] = new_name
                changed = True
            if new_identifier and new_identifier != self.config_entry.title:
                title = new_identifier
            if new_type and new_type != self.device_type:
                self.device_type = new_type
                entry_data[CONF_DEVICE_TYPE] = new_type
                changed = True
            if changed or title:
                kwargs = {"data": entry_data}
                if title:
                    kwargs["title"] = title
                self.hass.config_entries.async_update_entry(self.config_entry, **kwargs)

        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get_device({(DOMAIN, self.config_entry.entry_id)})
        if device_entry:
            updates = {"sw_version": data.get("version")}
            registry_name = data.get("user_device_name") or data.get("device_name")
            if registry_name and not _looks_like_aquael_identifier(registry_name):
                updates["name"] = registry_name
            if data.get("mac"):
                updates["new_connections"] = {(dr.CONNECTION_NETWORK_MAC, data["mac"])}
            try:
                device_registry.async_update_device(device_entry.id, **updates)
            except dr.DeviceConnectionCollisionError as err:
                _LOGGER.debug("Aquael Link MAC connection is already registered: %s", err)
        return data

    def send_command_expect(self, command, expected=None):
        with self.lock:
            target_ip = self._discover_target_ip()[0]
            sock = self._open_socket()
            try:
                response = self._safe_send_receive(
                    sock,
                    command,
                    target_ip,
                    2.0,
                    expected_prefixes=expected if expected else None,
                )
            finally:
                sock.close()
        if expected is None:
            return response is not None
        return bool(response and expected in response)

    def set_legacy_name(self, value):
        value = str(value or "").strip()
        commands = LEGACY_NAME_COMMANDS.get(self.device_type)
        if not commands:
            return None
        _query, prefix, expected = commands
        with self.lock:
            target_ip = self._discover_target_ip()[0]
            sock = self._open_socket()
            try:
                response = self._safe_send_receive(
                    sock,
                    f"{prefix}{value}\r\n",
                    target_ip,
                    2.0,
                    expected_prefixes=expected,
                )
                if not response or expected not in response:
                    return None
                confirm = self._safe_send_receive(sock, "SNA?", target_ip, 2.0, expected_prefixes="SNA?")
            finally:
                sock.close()
        confirmed_name = _decode_legacy_name_response(confirm)
        return value if confirmed_name is None else confirmed_name

    async def async_send_command_expect(self, command, expected=None):
        success = await self.hass.async_add_executor_job(self.send_command_expect, command, expected)
        if success:
            await self.async_request_refresh()
        return success

    async def async_send_command_expect_fast(self, command, expected=None, data_updates=None):
        success = await self.hass.async_add_executor_job(self.send_command_expect, command, expected)
        if success and data_updates:
            self.async_set_updated_data({**(self.data or {}), **data_updates})
        elif success:
            await self.async_request_refresh()
        return success

    def fetch_schedules(self):
        groups = SCHEDULE_GROUPS.get(self.device_type, {})
        if not groups:
            return {}
        with self.lock:
            target_ip = self._discover_target_ip()[0]
            sock = self._open_socket()
            try:
                responses = {}
                for key, spec in groups.items():
                    _name, query, *_rest = spec
                    try:
                        responses[key] = self._send_receive_raw(sock, query, target_ip, 2.0)
                    except (socket.timeout, OSError) as err:
                        _LOGGER.debug("Aquael Link schedule query %s failed: %s", query, err)
                return decode_schedules(self.device_type, responses)
            finally:
                sock.close()

    async def async_fetch_schedules(self):
        return await self.hass.async_add_executor_job(self.fetch_schedules)

    def set_schedule_group(self, group, entries):
        command, expected = encode_command(self.device_type, group, entries)
        with self.lock:
            target_ip = self._discover_target_ip()[0]
            sock = self._open_socket()
            try:
                response = self._send_receive_raw(sock, command, target_ip, 2.0)
            finally:
                sock.close()
        return bool(response and expected.encode("latin1") in response)

    async def async_set_schedule_group(self, group, entries):
        success = await self.hass.async_add_executor_job(self.set_schedule_group, group, entries)
        if success:
            await self.async_request_refresh()
        return success

    async def async_set_light_channels(self, red=None, blue=None, white=None):
        data = self.data or {}
        values = {
            "red": data.get("red", 0) if red is None else red,
            "blue": data.get("blue", 0) if blue is None else blue,
            "white": data.get("white", 0) if white is None else white,
        }
        values = {
            "red": max(0, min(100, int(round(values["red"])))),
            "blue": max(0, min(100, int(round(values["blue"])))),
            "white": max(0, min(100, int(round(values["white"])))),
        }
        power_limit = _light_power_limit_w(
            data.get("device_name") or data.get("user_device_name") or self.device_name
        )
        power = _light_power_w(values["red"], values["blue"], values["white"])
        if power > power_limit:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(
                "Przekroczono limit mocy lampy "
                f"({power:.1f} W > {power_limit:.0f} W). "
                "Aby zwiekszyc jeden kanal, najpierw zmniejsz inny."
            )
        command = "PWM_SET:{red:03d}{blue:03d}{white:03d}".format(
            red=_light_percent_to_wire(values["red"]),
            blue=_light_percent_to_wire(values["blue"]),
            white=_light_percent_to_wire(values["white"]),
        )
        return await self.async_send_command_expect_fast(command, "PWMOK", values)

    async def async_set_light_preset(self, preset):
        data = self.data or {}
        power_limit = _light_power_limit_w(
            data.get("device_name") or data.get("user_device_name") or self.device_name
        )
        values = _light_safe_preset_values(preset, power_limit)
        return await self.async_set_light_channels(**values)

    def assert_manual_mode(self):
        from homeassistant.exceptions import HomeAssistantError
        if (self.data or {}).get("alarms_enabled"):
            raise HomeAssistantError(
                "Urzadzenie pracuje w trybie automatycznym. Wylacz tryb automatyczny, aby sterowac recznie."
            )

    async def async_set_socket_output(self, output, state):
        return await self.async_set_socket_manual_mode(output, "on" if state else "off")

    async def async_set_socket_manual_mode(self, output, mode):
        command_spec = SOCKET_MANUAL_COMMANDS.get(output, {}).get(mode)
        if not command_spec:
            return False
        command, expected, raw_state = command_spec
        return await self.async_send_command_expect_fast(command, expected, {
            f"output_{output}": mode != "off",
            f"output_{output}_mode": mode,
            f"output_{output}_state": raw_state,
        })

    async def async_set_legacy_name(self, value):
        confirmed_name = await self.hass.async_add_executor_job(self.set_legacy_name, value)
        if confirmed_name is None:
            return False

        self.device_name = confirmed_name or self.device_name
        entry_data = dict(self.config_entry.data)
        entry_data[CONF_DEVICE_NAME] = self.device_name
        self.hass.config_entries.async_update_entry(self.config_entry, data=entry_data)
        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get_device({(DOMAIN, self.config_entry.entry_id)})
        if device_entry:
            device_registry.async_update_device(device_entry.id, name=self.device_name)
        self.async_set_updated_data(
            {
                **(self.data or {}),
                "device_name": self.device_name,
                "user_device_name": confirmed_name,
            }
        )
        return True

    async def async_set_hypermax_value(self, key, value):
        if key == "FilterStaticEfficiency":
            value = max(20, min(100, int(round(value))))
        elif key == "FilterStaticTemperature":
            value = max(20.0, min(33.0, round(float(value), 1)))
        elif key == "UserDeviceName":
            value = str(value)
        command = json.dumps({"Set": {key: value}}, separators=(",", ":"))
        return await self.async_send_command_expect(command, "{")

    async def async_set_hypermax_module_state(self, module, enabled):
        state = "On" if enabled else "Off"
        command = json.dumps(
            {"Set": {"ModuleState": {"Module": module, "State": state}}},
            separators=(",", ":"),
        )
        result = await self.async_send_command_expect(command, "{")
        if result:
            data = {**(self.data or {})}
            module_state = dict(data.get("module_state") or {})
            module_state[module] = state
            data["module_state"] = module_state
            if module == "Pump":
                data["pump_enabled"] = enabled
            elif module == "Heater":
                data["thermostat_enabled"] = enabled
            self.async_set_updated_data(data)
            await self.async_request_refresh()
        return result

    async def async_send_text_command(self, prefix, value, expected):
        return await self.async_send_command_expect(f"{prefix}{value}\r\n", expected)

    async def async_set_calibration(self, water=None, ambient=None):
        data = self.data or {}
        water_value = data.get("cal_water", 0.0) if water is None else water
        ambient_value = data.get("cal_ambient", 0.0) if ambient is None else ambient
        raw_water = max(0, min(255, int(round((water_value * 10) + 50))))
        raw_ambient = max(0, min(255, int(round((ambient_value * 10) + 50))))
        return await self.async_send_command_expect(f"CAL:{raw_water:03d}{raw_ambient:03d}", "CALOK")

    def set_range_settings(self, changes):
        """Read-modify-write the notification range to never wipe unknown fields.

        Reads the authoritative ?RANGE from the device first (in the same socket
        session), applies only the requested changes, and refuses to write if the
        current thresholds cannot be determined (avoids resetting them to 0).
        """
        with self.lock:
            target_ip = self._discover_target_ip()[0]
            sock = self._open_socket()
            try:
                current = {}
                response = self._safe_send_receive(sock, "?RANGE", target_ip, 2.0, expected_prefixes="RANGE|")
                if response and response.startswith("RANGE|"):
                    self._parse_thermometer_range(response, current)
                if "range_down" not in current or "range_up" not in current:
                    cached = self.data or {}
                    for key in ("range_down", "range_up", "notification_enabled",
                                "notification_language", "notification_unit"):
                        current.setdefault(key, cached.get(key))
                if current.get("range_down") is None or current.get("range_up") is None:
                    return "unknown"  # refuse to write — would wipe thresholds

                merged = {**current, **changes}
                raw_down = max(0, min(999, int(round(merged["range_down"] * 10))))
                raw_up = max(0, min(999, int(round(merged["range_up"] * 10))))
                enabled = merged.get("notification_enabled", False)
                language = merged.get("notification_language") or 1
                unit = merged.get("notification_unit") or 0
                command = f"RANGE|{raw_down:03d}{raw_up:03d}|{int(bool(enabled))}|{int(language)}|{int(unit)}"
                confirm = self._safe_send_receive(sock, command, target_ip, 2.0, expected_prefixes="RANGEOK")
                return bool(confirm and "RANGEOK" in confirm)
            finally:
                sock.close()

    async def async_set_range_settings(self, **changes):
        result = await self.hass.async_add_executor_job(self.set_range_settings, changes)
        if result == "unknown":
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(
                "Nie udało się odczytać aktualnych ustawień powiadomień z urządzenia. "
                "Spróbuj ponownie za chwilę."
            )
        if result:
            await self.async_request_refresh()
        return result

    async def async_identify(self):
        if self.device_type == TYPE_HYPERMAX:
            command = json.dumps({"Set": {"Action": "Identify"}}, separators=(",", ":"))
            return await self.async_send_command_expect(command, "{")
        return await self.async_send_command_expect("IDT", "IDT")

    async def async_reset_device(self):
        return await self.async_send_command_expect("RESET", "RESET")

    async def async_set_hypermax_temp_offset(self, value):
        value = max(-5.0, min(5.0, round(float(value), 1)))
        command = json.dumps(
            {"Set": {"ModuleParameters": {"Module": "Heater", "Parameters": {"TemperatureOffset": value}}}},
            separators=(",", ":"),
        )
        result = await self.async_send_command_expect(command, "{")
        if result:
            self.async_set_updated_data({**(self.data or {}), "heater_temperature_offset": value})
            await self.async_request_refresh()
        return result

    async def async_set_hypermax_pin(self, enabled, code=None):
        pin = {"State": "On" if enabled else "Off"}
        if enabled and code is not None:
            pin["Code"] = int(code)
        command = json.dumps(
            {"Set": {"ModuleParameters": {"Module": "Display", "Parameters": {"Pin": pin}}}},
            separators=(",", ":"),
        )
        updates = {
            "display_pin_state": pin["State"],
            "display_pin_code": pin.get("Code", 0),
        }
        return await self.async_send_command_expect_fast(command, "{", updates)

    async def async_set_hypermax_notification(self, **changes):
        data = self.data or {}
        state = changes.get("state", data.get("heater_notify_state") or "On")
        min_temp = changes.get("min_temp", data.get("heater_notify_min") or 20.0)
        max_temp = changes.get("max_temp", data.get("heater_notify_max") or 30.0)
        command = json.dumps(
            {"Set": {"ModuleNotification": {"Module": "Heater", "State": state,
                "Notification": {"TemperatureMin": float(min_temp), "TemperatureMax": float(max_temp)}}}},
            separators=(",", ":"),
        )
        result = await self.async_send_command_expect(command, "{")
        if result:
            self.async_set_updated_data({
                **(self.data or {}),
                "heater_notify_state": state,
                "heater_notify_min": float(min_temp),
                "heater_notify_max": float(max_temp),
            })
            await self.async_request_refresh()
        return result
