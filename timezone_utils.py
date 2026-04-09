from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from typing import Tuple

COMMON_TIMEZONES = [
    "UTC", "America/New_York", "America/Los_Angeles", "America/Chicago",
    "America/Denver", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Australia/Sydney",
    "Africa/Johannesburg", "Pacific/Auckland"
]


def validate_timezone(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


def local_to_utc(local_time: str, local_day: int, tz_name: str) -> Tuple[str, str]:
    """
    Convert local time (HH:MM) and day (1=Monday) to UTC time and UTC day.
    Returns (utc_day, utc_time)
    """
    tz = ZoneInfo(tz_name)
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_local = now_utc.astimezone(tz)
    
    hour, minute = map(int, local_time.split(":"))
    target_weekday = local_day - 1
    days_ahead = (target_weekday - now_local.weekday()) % 7
    target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if target_local <= now_local:
        target_local += timedelta(days=7)
    
    target_utc = target_local.astimezone(ZoneInfo("UTC"))
    utc_day = target_utc.isoweekday()
    utc_time = target_utc.strftime("%H:%M")
    return str(utc_day), utc_time


def utc_to_local(utc_day: str, utc_time: str, tz_name: str) -> Tuple[int, str]:
    """
    Convert UTC day and time to local day and time.
    Returns (local_day, local_time)
    """
    tz = ZoneInfo(tz_name)
    now_utc = datetime.now(ZoneInfo("UTC"))
    hour, minute = map(int, utc_time.split(":"))
    
    target_weekday = int(utc_day) - 1
    days_ahead = (target_weekday - now_utc.weekday()) % 7
    target_utc = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if target_utc <= now_utc:
        target_utc += timedelta(days=7)
    
    target_local = target_utc.astimezone(tz)
    local_day = target_local.isoweekday()
    local_time = target_local.strftime("%H:%M")
    return local_day, local_time


def get_current_local_time(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def get_current_local_weekday(tz_name: str) -> int:
    return get_current_local_time(tz_name).isoweekday()


def get_current_local_time_str(tz_name: str) -> str:
    return get_current_local_time(tz_name).strftime("%H:%M")