from homeassistant.const import CONF_IP_ADDRESS

DOMAIN = "aquael_link"
UDP_PORT = 2390

CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_CHOICE = "device_choice"
CONF_ADD_TO_PANEL = "add_to_panel"

TYPE_HYPERMAX = "hypermax"
TYPE_LIGHT = "light"
TYPE_SOCKET = "socket"
TYPE_THERMOMETER = "thermometer"
TYPE_UNKNOWN = "unknown"

DEVICE_TYPES = {
    TYPE_THERMOMETER: "Thermometer Link",
    TYPE_HYPERMAX: "HyperMAX Link ECU",
    TYPE_LIGHT: "Light Link",
    TYPE_SOCKET: "Socket Link Duo",
    TYPE_UNKNOWN: "Nieznane Aquael Link",
}

DEFAULT_NAME = "Aquael Link"

LEGACY_NAME_COMMANDS = {
    TYPE_THERMOMETER: ("SNA?", "SNAME", "SNAMEOK"),
    TYPE_LIGHT: ("SNA?", "SNAME", "SNAMEOK"),
    TYPE_SOCKET: ("SNA?", "SNAME", "SNAMEOK"),
}

HYPERMAX_GET_KEYS = [
    "Timezone",
    "Timestamp",
    "DeviceName",
    "UserDeviceName",
    "BoardRevision",
    "Mode",
    "Protocol",
    "MAC_WiFi",
    "IP",
    "WiFi_RSSI",
    "FilterStaticTemperature",
    "FilterStaticEfficiency",
    "FilterCurrentTemperature",
    "WaterSensorFlooded",
    "ModuleMode",
    "ModuleParameters",
    "ModuleState",
    "ModuleNotification",
    "FirmwareVersion",
]
