from __future__ import annotations

from .models import PlayerState


class EconomyError(ValueError):
    pass


def add_item(player: PlayerState, item_id: str, amount: int) -> None:
    if amount <= 0:
        raise EconomyError("物品数量必须为正数")
    player.inventory[item_id] = player.inventory.get(item_id, 0) + amount


def remove_item(player: PlayerState, item_id: str, amount: int) -> None:
    if amount <= 0:
        raise EconomyError("物品数量必须为正数")
    owned = player.inventory.get(item_id, 0)
    if owned < amount:
        raise EconomyError("物品数量不足")
    remaining = owned - amount
    if remaining:
        player.inventory[item_id] = remaining
    else:
        player.inventory.pop(item_id, None)


def spend_coins(player: PlayerState, amount: int) -> None:
    if amount <= 0:
        raise EconomyError("金额必须为正数")
    if player.coins < amount:
        raise EconomyError("金币不足")
    player.coins -= amount


def grant_coins(player: PlayerState, amount: int) -> None:
    if amount <= 0:
        raise EconomyError("金额必须为正数")
    player.coins += amount
