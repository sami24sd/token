"""کمک‌تابع‌های تقویم و روزهای هفته (هفتهٔ ایرانی: شنبه تا جمعه)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# ایندکس ۰ یعنی شنبه؛ با date.weekday() پایتون (دوشنبه=۰) هم‌تراز می‌شود.
WEEKDAYS_FA = ("شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه")

_WEEKDAY_ALIASES = {
    "saturday": 0, "sat": 0, "شنبه": 0,
    "sunday": 1, "sun": 1, "یکشنبه": 1, "یک‌شنبه": 1,
    "monday": 2, "mon": 2, "دوشنبه": 2,
    "tuesday": 3, "tue": 3, "سه‌شنبه": 3, "سه شنبه": 3,
    "wednesday": 4, "wed": 4, "چهارشنبه": 4,
    "thursday": 5, "thu": 5, "پنجشنبه": 5, "پنج‌شنبه": 5,
    "friday": 6, "fri": 6, "جمعه": 6,
}

# روزهای تعطیل آموزشی مدرسه (پنج‌شنبه و جمعه)
HOLIDAY_WEEKDAYS = frozenset({5, 6})


def persian_weekday_index(day: date) -> int:
    """ایندکس روز هفتهٔ ایرانی: شنبه=۰ … جمعه=۶."""
    return (day.weekday() + 2) % 7


def weekday_name(day: date) -> str:
    return WEEKDAYS_FA[persian_weekday_index(day)]


def parse_weekday(value: str) -> int:
    """نام روز هفته (فارسی یا انگلیسی) را به ایندکس ۰..۶ تبدیل می‌کند."""
    key = str(value).strip().lower()
    if key in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[key]
    if key.isdigit() and 0 <= int(key) <= 6:
        return int(key)
    raise ValueError(f"روز هفته ناشناخته: {value!r}")


def is_holiday(day: date) -> bool:
    return persian_weekday_index(day) in HOLIDAY_WEEKDAYS


def now_in(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def is_valid_hhmm(value: str) -> bool:
    try:
        hour, minute = str(value).split(":")
        return 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except (ValueError, AttributeError):
        return False


def parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = str(value).split(":")
    return int(hour), int(minute)
