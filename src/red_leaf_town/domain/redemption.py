from __future__ import annotations

import secrets
from typing import Literal

from pydantic import BaseModel, Field

RedemptionKind = Literal["monthly_card"]

# 去掉了 0/O/1/I/L，玩家照着截图手敲也不会打错。
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_GROUPS = 4
CODE_GROUP_SIZE = 4


class RedemptionCode(BaseModel):
    """一张激活码。兑换过的码不删，留着好回答「我这码是不是被人用了」。"""

    code: str = Field(min_length=4, max_length=64)
    kind: RedemptionKind = "monthly_card"
    batch: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=120)
    created_at: int = Field(ge=0)
    redeemed_by: str = ""
    redeemed_at: int = Field(default=0, ge=0)

    @property
    def redeemed(self) -> bool:
        return bool(self.redeemed_by)


def normalize_code(value: str) -> str:
    """玩家会连着横杠一起粘贴，也会用小写，统一成规范形式再查。"""
    cleaned = "".join(char for char in str(value or "").upper() if char.isalnum())
    if not cleaned:
        return ""
    groups = [cleaned[index:index + CODE_GROUP_SIZE] for index in range(0, len(cleaned), CODE_GROUP_SIZE)]
    return "-".join(groups)


def generate_code() -> str:
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUPS * CODE_GROUP_SIZE))
    return normalize_code(body)
