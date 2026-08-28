from __future__ import annotations

from datetime import datetime, timedelta

DAY_FORMAT = "%Y-%m-%d"


def shift_day(day: str, days: int) -> str:
    return (datetime.strptime(day, DAY_FORMAT) + timedelta(days=days)).strftime(DAY_FORMAT)


def days_between(start: str, end: str) -> int:
    """end 减 start 的天数，可以是负数。"""
    return (datetime.strptime(end, DAY_FORMAT) - datetime.strptime(start, DAY_FORMAT)).days


def remaining_days(expires_on: str, today: str) -> int:
    """含当天的剩余天数。没卡或已过期都是 0。"""
    if not expires_on:
        return 0
    return max(0, days_between(today, expires_on) + 1)


def extend_expiry(expires_on: str, today: str, duration_days: int) -> str:
    """续期从现有到期日往后接；卡已过期或从没有过，就从今天开始算第一天。"""
    if expires_on and days_between(today, expires_on) >= 0:
        base = expires_on
    else:
        base = shift_day(today, -1)
    return shift_day(base, duration_days)


def is_active(expires_on: str, today: str) -> bool:
    return remaining_days(expires_on, today) > 0
