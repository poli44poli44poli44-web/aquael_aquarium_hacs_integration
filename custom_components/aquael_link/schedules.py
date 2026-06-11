from .const import TYPE_LIGHT, TYPE_SOCKET

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

GROUPS = {
    TYPE_SOCKET: {
        "time": ("Czasowy", "ALARMS?", "ALARMS_SET:", "ASETOK", 6, 14, False, False),
        "periodic": ("Okresowy", "ALARMS2", "OKRESO_SET:", "ASETOK2", 10, 8, False, True),
    },
    TYPE_LIGHT: {
        "time": ("Czasowy", "ALARMS?", "TIME_1_SET:", "ASETOK", 9, 9, True, False),
        "storm": ("Burza", "ALARMS2", "TIME_2_SET:", "ASETOK2", 9, 4, False, False),
        "sunrise": ("Wschod", "ALARMS3", "TIME_3_SET:", "ASETOK3", 9, 4, True, False),
        "sunset": ("Zachod", "ALARMS4", "TIME_4_SET:", "ASETOK4", 9, 4, True, False),
    },
}


def decode_schedules(device_type, responses):
    schedules = {}
    for key, spec in GROUPS.get(device_type, {}).items():
        response = responses.get(key)
        if response is not None:
            schedules[key] = decode_group(device_type, key, response)
    return schedules


def decode_group(device_type, key, response):
    name, query, _set_prefix, _expected, record_len, max_count, channels, interval = GROUPS[device_type][key]
    payload = _payload_bytes(query, response)
    if not payload:
        payload = b"\x01"
    count = max(0, min(max_count, payload[0] - 1))
    entries = []
    for index in range(count):
        start = 1 + index * record_len
        record = payload[start : start + record_len]
        if len(record) != record_len:
            break
        entries.append(_decode_record(index + 1, record, channels, interval, key))
    return {
        "key": key,
        "name": name,
        "count": len(entries),
        "max": max_count,
        "raw_hex": payload.hex(),
        "entries": entries,
    }


def encode_command(device_type, key, entries):
    _name, _query, set_prefix, expected, record_len, max_count, channels, interval = GROUPS[device_type][key]
    entries = list(entries or [])[:max_count]
    payload = bytearray([len(entries) + 1])
    for entry in entries:
        payload.extend(_encode_record(entry, record_len, channels, interval, key))
    return set_prefix.encode("latin1") + bytes(payload), expected


def _payload_bytes(query, response):
    data = response if isinstance(response, bytes) else str(response).encode("latin1", errors="ignore")
    prefixes = {
        "ALARMS?": b"ALARMS:",
        "ALARMS2": b"ALARMS2",
        "ALARMS3": b"ALARMS3",
        "ALARMS4": b"ALARMS4",
    }
    prefix = prefixes.get(query, query.encode("latin1"))
    return data[len(prefix) :] if data.startswith(prefix) else data


def _decode_record(index, record, channels, interval, group_key):
    entry = {
        "index": index,
        "enabled": bool(record[3] & 0x80),
        "days": _decode_days(record[0], record[1], record[2]),
        "start": _decode_hms(record[0], record[1], record[2]),
        "raw_hex": record.hex(),
    }
    if interval:
        entry["end"] = _decode_hms(record[3], record[4], record[5])
        entry["interval_on"] = _decode_interval(record[6], record[7])
        entry["interval_off"] = _decode_interval(record[8], record[9])
    else:
        entry["end"] = _decode_hms(record[3], record[4], record[5])
        if group_key in ("sunrise", "sunset"):
            entry["duration_minutes"] = max(1, min(60, record[4] & 0x3F))
    if channels:
        entry["white"] = max(0, record[6] - 1)
        entry["blue"] = max(0, record[7] - 1)
        entry["red"] = max(0, record[8] - 1)
    else:
        entry["extra_hex"] = record[6:].hex() if len(record) > 6 else ""
    if len(record) >= 6:
        entry["output"] = 2 if record[3] & 0x40 else 1
        entry["smart_light"] = {
            "enabled": bool(record[4] & 0x80),
            "white": bool(record[4] & 0x40),
            "blue_white": bool(record[5] & 0x80),
            "blue": bool(record[5] & 0x40),
        }
    return entry


def _encode_record(entry, record_len, channels, interval, group_key):
    record = bytearray(record_len)
    days = set(entry.get("days") or [])
    record[0], record[1], record[2] = _encode_start(_parse_hms(entry.get("start", "00:00:00")), days)
    if group_key in ("sunrise", "sunset"):
        duration = max(1, min(60, int(entry.get("duration_minutes") or 10)))
        record[3], record[4], record[5] = _encode_sun_duration(bool(entry.get("enabled", True)), duration)
    else:
        record[3], record[4], record[5] = _encode_end(
            _parse_hms(entry.get("end", "00:00:00")),
            bool(entry.get("enabled", True)),
            int(entry.get("output", 1)),
        )
    smart = entry.get("smart_light") or {}
    if smart.get("enabled"):
        record[4] |= 0x80
    if smart.get("white"):
        record[4] |= 0x40
    if smart.get("blue_white"):
        record[5] |= 0x80
    if smart.get("blue"):
        record[5] |= 0x40
    if channels:
        record[6] = _channel(entry.get("white", 0))
        record[7] = _channel(entry.get("blue", 0))
        record[8] = _channel(entry.get("red", 0))
    elif interval:
        record[6], record[7] = _encode_interval(entry.get("interval_on") or {})
        record[8], record[9] = _encode_interval(entry.get("interval_off") or {})
    elif len(record) > 6 and entry.get("extra_hex"):
        extra = bytes.fromhex(entry["extra_hex"])[:3]
        record[6 : 6 + len(extra)] = extra
    elif group_key == "storm":
        record[6:9] = b"\xff\xff\xff"
    return bytes(record)


def _decode_days(h, m, s):
    days = []
    if h & 0x80:
        days.append("mon")
    if h & 0x40:
        days.append("tue")
    if h & 0x20:
        days.append("wed")
    if m & 0x80:
        days.append("thu")
    if m & 0x40:
        days.append("fri")
    if s & 0x80:
        days.append("sat")
    if s & 0x40:
        days.append("sun")
    return days


def _decode_hms(h, m, s):
    return f"{max(0, (h & 0x1F) - 1):02d}:{max(0, (m & 0x3F) - 1):02d}:{max(0, (s & 0x3F) - 1):02d}"


def _parse_hms(value):
    parts = [int(part) for part in str(value).split(":") if part != ""]
    while len(parts) < 3:
        parts.append(0)
    return max(0, min(23, parts[0])), max(0, min(59, parts[1])), max(0, min(59, parts[2]))


def _encode_start(hms, days):
    h, m, s = hms
    h += 1
    m += 1
    s += 1
    if "mon" in days:
        h |= 0x80
    if "tue" in days:
        h |= 0x40
    if "wed" in days:
        h |= 0x20
    if "thu" in days:
        m |= 0x80
    if "fri" in days:
        m |= 0x40
    if "sat" in days:
        s |= 0x80
    if "sun" in days:
        s |= 0x40
    return h, m, s


def _encode_end(hms, enabled, output):
    h, m, s = hms
    h += 1
    m += 1
    s += 1
    if enabled:
        h |= 0x80
    if output == 2:
        h |= 0x40
    return h, m, s


def _encode_sun_duration(enabled, duration):
    h = 1
    if enabled:
        h |= 0x80
    return h, duration, 1


def _decode_interval(m, s):
    return {
        "minutes": max(0, (m & 0x3F) - 1),
        "seconds": max(0, (s & 0x3F) - 1),
        "tenths": ((m >> 6) & 0x03) * 4 + ((s >> 6) & 0x03),
    }


def _encode_interval(value):
    minutes = max(0, min(59, int(value.get("minutes", 0)))) + 1
    seconds = max(0, min(59, int(value.get("seconds", 0)))) + 1
    tenths = max(0, min(9, int(value.get("tenths", 0))))
    return minutes | ((tenths // 4) << 6), seconds | ((tenths % 4) << 6)


def _channel(value):
    return max(1, min(101, int(value) + 1))
