from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CURATED_TIMEZONES = [
    "Asia/Tashkent",
    "Europe/Moscow",
    "Europe/Istanbul",
    "Asia/Dubai",
    "Asia/Almaty",
    "Europe/London",
]


def is_valid_curated_timezone(value: str) -> bool:
    if value not in CURATED_TIMEZONES:
        return False
    try:
        ZoneInfo(value)
        return True
    except ZoneInfoNotFoundError:
        return False
