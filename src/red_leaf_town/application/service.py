from __future__ import annotations

import random
import time
from collections.abc import Callable

from red_leaf_town.content import GameContent
from red_leaf_town.domain import PlayerState, QQIdentity
from red_leaf_town.domain.economy import EconomyError, add_item, grant_coins, remove_item, spend_coins
from red_leaf_town.domain.progression import consume_stamina, grant_experience, normalize_plot_slots, settle_stamina

from .ports import PlayerRepository


class GameError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class GameService:
    def __init__(
        self,
        content: GameContent,
        repository: PlayerRepository,
        *,
        clock: Callable[[], float] = time.time,
        rng: random.Random | random.SystemRandom | None = None,
    ):
        self.content = content
        self.repository = repository
        self.clock = clock
        self.rng = rng or random.SystemRandom()

    def ensure_player(self, oauth_sub: str, display_name: str) -> PlayerState:
        return self.repository.ensure_player(oauth_sub, display_name or "红叶镇居民", self._now())

    def snapshot_by_sub(self, oauth_sub: str) -> dict:
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return self._settled_snapshot(player.player_id)

    def snapshot_by_identity(self, identity: QQIdentity) -> dict:
        player_id = self.repository.player_id_for_identity(identity)
        if not player_id:
            raise GameError("identity_not_bound", "这个 QQ 身份尚未绑定红叶镇角色", 404)
        return self._settled_snapshot(player_id)

    def buy(self, oauth_sub: str, shop_id: str, quantity: int) -> dict:
        if quantity < 1 or quantity > 99:
            raise GameError("invalid_quantity", "购买数量需在 1 到 99 之间")
        entry = self.content.shop_map.get(shop_id)
        if not entry:
            raise GameError("shop_item_not_found", "商品不存在", 404)

        def mutation(player: PlayerState):
            if player.level < entry.min_level:
                raise GameError("content_locked", f"达到 {entry.min_level} 级后解锁")
            try:
                spend_coins(player, entry.price * quantity)
                add_item(player, entry.item_id, quantity)
            except EconomyError as exc:
                raise GameError("economy_error", str(exc)) from exc
            return {"item_id": entry.item_id, "quantity": quantity}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def plant(self, oauth_sub: str, slot: int, crop_id: str) -> dict:
        crop = self.content.crop_map.get(crop_id)
        if not crop:
            raise GameError("crop_not_found", "作物不存在", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if player.level < crop.min_level:
                raise GameError("content_locked", f"达到 {crop.min_level} 级后解锁")
            plot = self._plot(player, slot)
            if not plot.empty:
                raise GameError("plot_occupied", "这块土地已经种有作物")
            try:
                remove_item(player, crop.seed_item_id, 1)
                consume_stamina(player, crop.stamina_cost, self.content, now)
            except (EconomyError, ValueError) as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            plot.crop_id = crop.id
            plot.planted_at = now
            plot.ready_at = now + crop.growth_seconds
            levels = grant_experience(player, crop.plant_xp, self.content)
            return {"slot": slot, "crop_id": crop.id, "ready_at": plot.ready_at, "levels": levels}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def harvest(self, oauth_sub: str, slot: int) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            plot = self._plot(player, slot)
            if plot.empty:
                raise GameError("plot_empty", "这块土地还没有作物")
            if plot.ready_at > now:
                raise GameError("crop_not_ready", "作物还没有成熟")
            crop = self.content.crop_map[plot.crop_id]
            amount = self.rng.randint(crop.yield_min, crop.yield_max)
            add_item(player, crop.produce_item_id, amount)
            levels = grant_experience(player, crop.harvest_xp, self.content)
            plot.crop_id = ""
            plot.planted_at = 0
            plot.ready_at = 0
            return {
                "slot": slot,
                "item_id": crop.produce_item_id,
                "quantity": amount,
                "experience": crop.harvest_xp,
                "levels": levels,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def sell(self, oauth_sub: str, item_id: str, quantity: int) -> dict:
        if quantity < 1:
            raise GameError("invalid_quantity", "出售数量必须为正数")
        item = self.content.item_map.get(item_id)
        if not item or item.sell_price <= 0:
            raise GameError("item_not_sellable", "该物品不能出售")

        def mutation(player: PlayerState):
            try:
                remove_item(player, item_id, quantity)
                coins = item.sell_price * quantity
                grant_coins(player, coins)
            except EconomyError as exc:
                raise GameError("economy_error", str(exc)) from exc
            return {"item_id": item_id, "quantity": quantity, "coins": coins}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def create_binding_code(self, oauth_sub: str) -> str:
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return self.repository.create_binding_code(player.player_id)

    def bind_identity(self, code: str, identity: QQIdentity) -> PlayerState:
        player_id = self.repository.consume_binding_code(code.strip().upper(), identity)
        if not player_id:
            raise GameError("binding_code_invalid", "绑定码无效或已过期", 404)
        player = self.repository.get(player_id)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return player

    def account(self, oauth_sub: str) -> dict:
        state = self.snapshot_by_sub(oauth_sub)
        player = self.repository.get_by_sub(oauth_sub)
        return {
            "player_id": state["player"]["player_id"],
            "display_name": state["player"]["display_name"],
            "bindings": self.repository.binding_labels(player.player_id) if player else [],
            "state": state,
        }

    def _settled_snapshot(self, player_id: str) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)

        player, _ = self.repository.update(player_id, mutation)
        return self._snapshot(player, now)

    def _update_by_sub(self, oauth_sub: str, mutation):
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return self.repository.update(player.player_id, mutation)

    def _settle(self, player: PlayerState, now: int) -> None:
        level = self.content.level_for_xp(player.experience)
        player.level = level.level
        normalize_plot_slots(player, self.content)
        settle_stamina(player, self.content, now)

    def _plot(self, player: PlayerState, slot: int):
        if slot < 0 or slot >= len(player.plots):
            raise GameError("plot_locked", "这块土地尚未解锁")
        return player.plots[slot]

    def _snapshot(self, player: PlayerState, now: int | None = None) -> dict:
        now = self._now() if now is None else now
        level = self.content.level_definition(player.level)
        next_level = next((entry for entry in self.content.levels if entry.level > player.level), None)
        items = self.content.item_map
        crops = self.content.crop_map
        inventory = [
            {
                "item_id": item_id,
                "name": items[item_id].name if item_id in items else item_id,
                "icon": items[item_id].icon if item_id in items else "package",
                "kind": items[item_id].kind if item_id in items else "material",
                "quantity": quantity,
                "sell_price": items[item_id].sell_price if item_id in items else 0,
            }
            for item_id, quantity in sorted(player.inventory.items())
            if quantity > 0
        ]
        plots = []
        for plot in player.plots:
            crop = crops.get(plot.crop_id)
            plots.append({
                **plot.model_dump(),
                "empty": plot.empty,
                "ready": bool(crop and plot.ready_at <= now),
                "remaining_seconds": max(0, plot.ready_at - now) if crop else 0,
                "crop": crop.model_dump() if crop else None,
            })
        next_plot_level = next(
            (entry.level for entry in self.content.levels if entry.plot_slots > len(player.plots)),
            None,
        )
        return {
            "server_time": now,
            "player": {
                "player_id": player.player_id,
                "display_name": player.display_name,
                "level": player.level,
                "experience": player.experience,
                "current_level_xp": level.total_xp,
                "next_level_xp": next_level.total_xp if next_level else None,
                "coins": player.coins,
                "stamina": player.stamina,
                "stamina_cap": level.stamina_cap,
                "stamina_restore_seconds": self.content.stamina.restore_seconds,
                "stamina_updated_at": player.stamina_updated_at,
                "unlocks": sorted({unlock for entry in self.content.levels if entry.level <= player.level for unlock in entry.unlocks}),
            },
            "plots": plots,
            "next_plot_level": next_plot_level,
            "inventory": inventory,
            "shop": [
                {
                    **entry.model_dump(),
                    "item": items[entry.item_id].model_dump(),
                    "crop": next(
                        (crop.model_dump() for crop in self.content.crops if crop.seed_item_id == entry.item_id),
                        None,
                    ),
                    "locked": player.level < entry.min_level,
                }
                for entry in self.content.shop
            ],
        }

    def _now(self) -> int:
        return int(self.clock())
