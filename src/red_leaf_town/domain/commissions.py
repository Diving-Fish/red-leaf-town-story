from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DAY_FORMAT = "%Y-%m-%d"


def commission_day(now: int, reset_hour: int, timezone: str) -> str:
    """委托的自然日按刷新时区计算，刷新点之前仍然算前一天。"""
    local = datetime.fromtimestamp(now, ZoneInfo(timezone)) - timedelta(hours=reset_hour)
    return local.strftime(DAY_FORMAT)


def commission_day_end(day: str, reset_hour: int, timezone: str) -> int:
    """这一天的委托失效的时间点，也就是下一次刷新的时刻。"""
    start = datetime.strptime(day, DAY_FORMAT).replace(tzinfo=ZoneInfo(timezone), hour=reset_hour)
    return int((start + timedelta(days=1)).timestamp())


def _digest(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16)


def lucky_weekday(player_id: str) -> int:
    """幸运日跟随账号永久固定，玩家可以提前囤货。0 是周一。"""
    return _digest(player_id, "lucky-day") % 7


def is_lucky_day(player_id: str, day: str) -> bool:
    return datetime.strptime(day, DAY_FORMAT).weekday() == lucky_weekday(player_id)


def commission_identifier(player_id: str, day: str) -> str:
    """一个玩家一天只有一份委托，ID 由此推导，重发之后仍然是同一份。"""
    return hashlib.sha256(f"{player_id}|{day}|commission".encode()).hexdigest()[:32]


def commission_seed(player_id: str, day: str) -> int:
    """同一天重复结算必须掷出同一个委托，否则 WATCH 重试会把内容换掉。"""
    return _digest(player_id, day, "commission") % (2 ** 63)
