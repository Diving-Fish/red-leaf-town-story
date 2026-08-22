from __future__ import annotations

import random
import time
from collections.abc import Callable
from math import ceil, floor

from red_leaf_town.content import GameContent
from red_leaf_town.domain import (
    OwnedPartnerState,
    PlayerState,
    ProductionResultSnapshot,
    ProductionTaskSnapshot,
    QQIdentity,
    TaskPartnerSnapshot,
    TaskQualitySnapshot,
)
from red_leaf_town.domain.economy import EconomyError, add_item, grant_coins, remove_item, spend_coins
from red_leaf_town.domain.progression import consume_stamina, grant_experience, normalize_plot_slots, settle_stamina
from red_leaf_town.domain.quality import QUALITY_NAMES, quality_probabilities, roll_quality
from red_leaf_town.partner_content import (
    GROWTH_CURVE_NAMES,
    INDUSTRY_NAMES,
    PartnerCatalog,
    level_cap_for_breakthrough,
    load_partner_catalog,
)
from red_leaf_town.partner_traits import partner_trait_catalog

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
        partner_catalog_loader: Callable[[], PartnerCatalog] = load_partner_catalog,
    ):
        self.content = content
        self.repository = repository
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.partner_catalog_loader = partner_catalog_loader

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
            task_snapshot = self._build_farming_task_snapshot(player, plot, crop, now)
            try:
                remove_item(player, crop.seed_item_id, 1)
                consume_stamina(player, crop.stamina_cost, self.content, now)
            except (EconomyError, ValueError) as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            plot.crop_id = crop.id
            plot.planted_at = now
            plot.ready_at = task_snapshot.ready_at
            plot.task_snapshot = task_snapshot
            plot.task_result = None
            levels = grant_experience(player, crop.plant_xp, self.content)
            return {
                "slot": slot,
                "crop_id": crop.id,
                "ready_at": plot.ready_at,
                "levels": levels,
                "base_duration": task_snapshot.base_duration,
                "final_duration": task_snapshot.final_duration,
                "time_saved": task_snapshot.base_duration - task_snapshot.final_duration,
                "total_ability": task_snapshot.total_ability,
                "time_efficiency": task_snapshot.time_efficiency,
                "quality_ability": task_snapshot.quality_parameters.ability,
                "quality_probabilities": task_snapshot.quality_parameters.probabilities,
            }

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
            task_result = plot.task_result
            if task_result is None:
                raise GameError("task_content_missing", "进行中的作物配置缺失，请联系管理员", 409)
            task = plot.task_snapshot
            crop = self.content.crop_map.get(plot.crop_id)
            harvest_xp = task.harvest_xp if task else crop.harvest_xp if crop else 0
            add_item(player, task_result.item_id, task_result.quantity, task_result.quality)
            levels = grant_experience(player, harvest_xp, self.content)
            plot.crop_id = ""
            plot.planted_at = 0
            plot.ready_at = 0
            plot.task_snapshot = None
            plot.task_result = None
            return {
                "slot": slot,
                "item_id": task_result.item_id,
                "quantity": task_result.quantity,
                "quality": task_result.quality,
                "quality_name": QUALITY_NAMES[task_result.quality],
                "experience": harvest_xp,
                "levels": levels,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def assign_partner(self, oauth_sub: str, slot: int, partner_id: str = "") -> dict:
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()
        farming_rules = self.content.industries["farming"]

        def mutation(player: PlayerState):
            self._settle(player, now)
            plot = self._plot(player, slot)
            desired_ids = [partner_id] if partner_id else []
            if plot.assigned_partner_ids == desired_ids:
                return {"slot": slot, "partner_id": partner_id or None, "changed": False}
            if not plot.empty and plot.ready_at > now:
                raise GameError("partner_assignment_locked", "任务进行中，不能调整这块土地的伙伴", 409)

            locked_until = self._partner_lock_deadlines(player, now)
            affected_ids = set(plot.assigned_partner_ids)
            if partner_id:
                affected_ids.add(partner_id)
            locked_id = next((entry for entry in affected_ids if locked_until.get(entry, 0) > now), None)
            if locked_id:
                raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能移动", 409)

            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                definition = catalog.partner_map.get(partner_id)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "farming" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有农作倾向", 409)

            for candidate in player.plots:
                if partner_id and partner_id in candidate.assigned_partner_ids:
                    candidate.assigned_partner_ids = []
            plot.assigned_partner_ids = desired_ids
            assigned_count = sum(len(candidate.assigned_partner_ids) for candidate in player.plots)
            if assigned_count > farming_rules.partner_capacity:
                raise GameError("partner_capacity_reached", "当前农作伙伴编制已满", 409)
            return {"slot": slot, "partner_id": partner_id or None, "changed": True}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def sell(self, oauth_sub: str, item_id: str, quantity: int, quality: int = 0) -> dict:
        if quantity < 1:
            raise GameError("invalid_quantity", "出售数量必须为正数")
        item = self.content.item_map.get(item_id)
        if not item or item.sell_price <= 0:
            raise GameError("item_not_sellable", "该物品不能出售")
        if item.kind not in {"produce", "product"} and quality != 0:
            raise GameError("invalid_quality", "该物品不使用品质")
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            selected_quality = quality
            if item.kind in {"produce", "product"} and selected_quality == 0:
                available = [
                    candidate
                    for candidate, amount in player.inventory.get(item_id, {}).items()
                    if candidate in self.content.quality.grade_map and amount > 0
                ]
                if len(available) != 1:
                    raise GameError("invalid_quality", "请选择要出售的物品品质")
                selected_quality = available[0]
            if item.kind in {"produce", "product"} and selected_quality not in self.content.quality.grade_map:
                raise GameError("invalid_quality", "请选择要出售的物品品质")
            unit_price = self._quality_unit_price(item.sell_price, selected_quality)
            try:
                remove_item(player, item_id, quantity, selected_quality)
                coins = unit_price * quantity
                grant_coins(player, coins)
            except EconomyError as exc:
                raise GameError("economy_error", str(exc)) from exc
            return {
                "item_id": item_id,
                "quantity": quantity,
                "quality": selected_quality or None,
                "quality_name": QUALITY_NAMES.get(selected_quality),
                "unit_price": unit_price,
                "coins": coins,
            }

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

    def admin_search_players(self, query: str = "", limit: int = 50) -> list[dict]:
        bounded_limit = max(1, min(int(limit), 100))
        return [self._admin_player_summary(player) for player in self.repository.search(query, bounded_limit)]

    def admin_grant_partner(self, player_id: str, partner_id: str) -> dict:
        partner = self.partner_catalog_loader().partner_map.get(partner_id)
        if partner is None:
            raise GameError("partner_not_found", "伙伴不存在", 404)
        now = self._now()

        def mutation(player: PlayerState):
            if any(owned.partner_id == partner_id for owned in player.owned_partners):
                raise GameError("partner_already_owned", "玩家已经持有这个伙伴", 409)
            owned = OwnedPartnerState(partner_id=partner_id, acquired_at=now)
            player.owned_partners.append(owned)
            return owned

        try:
            player, owned = self.repository.update(player_id, mutation)
        except KeyError as exc:
            raise GameError("player_not_found", "玩家不存在", 404) from exc
        return {
            "owned_partner": owned.model_dump(),
            "player": self._admin_player_summary(player),
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
        self._normalize_inventory_quality(player)
        level = self.content.level_for_xp(player.experience)
        player.level = level.level
        normalize_plot_slots(player, self.content)
        settle_stamina(player, self.content, now)
        for plot in player.plots:
            if not plot.empty and plot.ready_at <= now and plot.task_result is None:
                self._resolve_farming_output(plot, now)

    def _plot(self, player: PlayerState, slot: int):
        if slot < 0 or slot >= len(player.plots):
            raise GameError("plot_locked", "这块土地尚未解锁")
        return player.plots[slot]

    def _build_farming_task_snapshot(self, player, plot, crop, now: int) -> ProductionTaskSnapshot:
        rules = self.content.industries["farming"]
        if len(plot.assigned_partner_ids) > rules.collaborator_slots:
            raise GameError("collaborator_slots_exceeded", "这块土地的伙伴位置超过当前上限", 409)
        if sum(len(candidate.assigned_partner_ids) for candidate in player.plots) > rules.partner_capacity:
            raise GameError("partner_capacity_reached", "当前农作伙伴编制已满", 409)

        catalog = self.partner_catalog_loader()
        owned_map = {entry.partner_id: entry for entry in player.owned_partners}
        partner_snapshots: list[TaskPartnerSnapshot] = []
        for partner_id in plot.assigned_partner_ids:
            owned = owned_map.get(partner_id)
            definition = catalog.partner_map.get(partner_id)
            if owned is None or definition is None:
                raise GameError("partner_assignment_invalid", "驻场伙伴数据无效，请重新安排", 409)
            tendency = next(
                (entry for entry in definition.tendencies if entry.industry == "farming"),
                None,
            )
            if tendency is None:
                raise GameError("partner_tendency_mismatch", "驻场伙伴没有农作倾向，请重新安排", 409)
            effective_level = min(
                owned.level,
                rules.partner_level_cap,
                level_cap_for_breakthrough(owned.breakthrough),
            )
            partner_snapshots.append(TaskPartnerSnapshot(
                partner_id=partner_id,
                level=owned.level,
                effective_level=effective_level,
                breakthrough=owned.breakthrough,
                ability=definition.ability_at("farming", effective_level),
            ))

        character_ability = rules.character_base_ability
        total_ability = character_ability + sum(entry.ability for entry in partner_snapshots)
        time_efficiency = 1 + 2 * total_ability / (total_ability + crop.time_difficulty)
        final_duration = max(1, ceil(crop.growth_seconds / time_efficiency))
        quality = crop.quality
        probabilities = quality_probabilities(
            total_ability,
            quality.thresholds,
            quality.width,
            quality.miracle_probability_cap,
            quality.miracle_eligible,
        )
        return ProductionTaskSnapshot(
            industry="farming",
            content_id=crop.id,
            production_slot_id=f"farm:plot:{plot.slot}",
            started_at=now,
            ready_at=now + final_duration,
            assigned_partner_ids=list(plot.assigned_partner_ids),
            support_partner_ids=[],
            partner_snapshots=partner_snapshots,
            applied_effects=[],
            character_ability=character_ability,
            total_ability=total_ability,
            time_efficiency=time_efficiency,
            base_duration=crop.growth_seconds,
            final_duration=final_duration,
            produce_item_id=crop.produce_item_id,
            yield_min=crop.yield_min,
            yield_max=crop.yield_max,
            harvest_xp=crop.harvest_xp,
            quality_parameters=TaskQualitySnapshot(
                ability=total_ability,
                thresholds=quality.thresholds,
                width=quality.width,
                miracle_probability_cap=quality.miracle_probability_cap,
                miracle_eligible=quality.miracle_eligible,
                probabilities=probabilities,
            ),
        )

    @staticmethod
    def _partner_lock_deadlines(player: PlayerState, now: int) -> dict[str, int]:
        deadlines: dict[str, int] = {}
        for plot in player.plots:
            task = plot.task_snapshot
            if task is None or plot.ready_at <= now:
                continue
            for partner_id in {*task.assigned_partner_ids, *task.support_partner_ids}:
                deadlines[partner_id] = max(deadlines.get(partner_id, 0), plot.ready_at)
        return deadlines

    def _snapshot(self, player: PlayerState, now: int | None = None) -> dict:
        now = self._now() if now is None else now
        level = self.content.level_definition(player.level)
        next_level = next((entry for entry in self.content.levels if entry.level > player.level), None)
        items = self.content.item_map
        crops = self.content.crop_map
        inventory = []
        for item_id, qualities in sorted(player.inventory.items()):
            item = items.get(item_id)
            for quality, quantity in sorted(qualities.items()):
                if quantity <= 0:
                    continue
                base_sell_price = item.sell_price if item else 0
                grade = self.content.quality.grade_map.get(quality)
                inventory.append({
                    "item_id": item_id,
                    "inventory_key": f"{item_id}:{quality}",
                    "name": item.name if item else item_id,
                    "icon": item.icon if item else "package",
                    "kind": item.kind if item else "material",
                    "quantity": quantity,
                    "quality": quality or None,
                    "quality_name": grade.name if grade else None,
                    "quality_sale_multiplier": grade.sale_multiplier if grade else 1,
                    "base_sell_price": base_sell_price,
                    "sell_price": self._quality_unit_price(base_sell_price, quality),
                })
        partner_records = self._partner_snapshots(player, now)
        partner_map = {entry["partner_id"]: entry for entry in partner_records}
        lock_deadlines = self._partner_lock_deadlines(player, now)
        plots = []
        for plot in player.plots:
            crop = crops.get(plot.crop_id)
            assigned_partners = [
                partner_map[partner_id]
                for partner_id in plot.assigned_partner_ids
                if partner_id in partner_map
            ]
            assignment_locked_until = max(
                (lock_deadlines.get(partner_id, 0) for partner_id in plot.assigned_partner_ids),
                default=0,
            )
            plots.append({
                **plot.model_dump(),
                "empty": plot.empty,
                "ready": bool(not plot.empty and plot.ready_at <= now),
                "remaining_seconds": max(0, plot.ready_at - now) if not plot.empty else 0,
                "crop": crop.model_dump() if crop else None,
                "assigned_partners": assigned_partners,
                "assignment_locked": assignment_locked_until > now,
                "assignment_locked_until": assignment_locked_until or None,
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
            "partners": partner_records,
            "partner_count": len(partner_records),
            "industry_rules": {
                industry: rules.model_dump()
                for industry, rules in self.content.industries.items()
            },
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

    def _partner_snapshots(self, player: PlayerState, now: int | None = None) -> list[dict]:
        now = self._now() if now is None else now
        catalog = self.partner_catalog_loader()
        definitions = catalog.partner_map
        trait_definitions = {trait.code: trait for trait in partner_trait_catalog()}
        assigned_slots = {
            partner_id: plot.slot
            for plot in player.plots
            for partner_id in plot.assigned_partner_ids
        }
        lock_deadlines = self._partner_lock_deadlines(player, now)
        records: list[dict] = []
        for owned in sorted(player.owned_partners, key=lambda entry: (entry.acquired_at, entry.partner_id)):
            definition = definitions.get(owned.partner_id)
            if definition is None:
                records.append({
                    **owned.model_dump(),
                    "missing": True,
                    "name": owned.partner_id,
                    "rarity": None,
                    "assigned_plot_slot": assigned_slots.get(owned.partner_id),
                    "locked": lock_deadlines.get(owned.partner_id, 0) > now,
                    "locked_until": lock_deadlines.get(owned.partner_id) or None,
                })
                continue
            artwork = definition.artwork_for(owned.breakthrough)
            avatar_crop = next(
                (crop for crop in definition.avatar_crops if crop.breakthrough == owned.breakthrough),
                None,
            )
            records.append({
                **owned.model_dump(),
                "missing": False,
                "name": definition.name,
                "rarity": definition.rarity,
                "description": definition.description,
                "growth_curve": definition.growth_curve,
                "growth_curve_name": GROWTH_CURVE_NAMES[definition.growth_curve],
                "level_cap": level_cap_for_breakthrough(owned.breakthrough),
                "artwork": artwork.model_dump() if artwork else None,
                "avatar_crop": avatar_crop.model_dump() if avatar_crop else None,
                "tendencies": [
                    self._partner_tendency_snapshot(definition, tendency, owned)
                    for tendency in definition.tendencies
                ],
                "traits": [
                    {
                        "code": code,
                        "name": trait_definitions[code].name if code in trait_definitions else code,
                        "description": trait_definitions[code].description if code in trait_definitions else "",
                        "implemented": trait_definitions[code].implemented if code in trait_definitions else False,
                    }
                    for code in definition.trait_codes
                ],
                "upgrade_available": False,
                "breakthrough_available": False,
                "assigned_plot_slot": assigned_slots.get(owned.partner_id),
                "locked": lock_deadlines.get(owned.partner_id, 0) > now,
                "locked_until": lock_deadlines.get(owned.partner_id) or None,
            })
        return records

    def _partner_tendency_snapshot(self, definition, tendency, owned: OwnedPartnerState) -> dict:
        breakthrough_cap = level_cap_for_breakthrough(owned.breakthrough)
        rules = self.content.industries.get(tendency.industry)
        effective_level = min(
            owned.level,
            breakthrough_cap,
            rules.partner_level_cap if rules else breakthrough_cap,
        )
        return {
            **tendency.model_dump(),
            "name": INDUSTRY_NAMES[tendency.industry],
            "current_ability": definition.ability_at(tendency.industry, owned.level),
            "effective_level": effective_level,
            "effective_ability": definition.ability_at(tendency.industry, effective_level),
        }

    def _normalize_inventory_quality(self, player: PlayerState) -> None:
        for item_id, qualities in list(player.inventory.items()):
            item = self.content.item_map.get(item_id)
            if item and item.kind in {"produce", "product"} and qualities.get(0, 0) > 0:
                qualities[1] = qualities.get(1, 0) + qualities.pop(0)
            for quality, quantity in list(qualities.items()):
                if quantity == 0:
                    qualities.pop(quality)
            if not qualities:
                player.inventory.pop(item_id)

    def _resolve_farming_output(self, plot, now: int) -> None:
        task = plot.task_snapshot
        crop = self.content.crop_map.get(plot.crop_id)
        if task:
            item_id = task.produce_item_id
            yield_min = task.yield_min
            yield_max = task.yield_max
            probabilities = task.quality_parameters.probabilities
        elif crop:
            item_id = crop.produce_item_id
            yield_min = crop.yield_min
            yield_max = crop.yield_max
            probabilities = [1, 0, 0, 0, 0]
        else:
            return
        plot.task_result = ProductionResultSnapshot(
            item_id=item_id,
            quantity=self.rng.randint(yield_min, yield_max),
            quality=roll_quality(self.rng, probabilities),
            resolved_at=now,
        )

    def _quality_unit_price(self, base_price: int, quality: int) -> int:
        grade = self.content.quality.grade_map.get(quality)
        multiplier = grade.sale_multiplier if grade else 1
        return floor(base_price * multiplier + 0.5)

    @staticmethod
    def _admin_player_summary(player: PlayerState) -> dict:
        return {
            "player_id": player.player_id,
            "display_name": player.display_name,
            "level": player.level,
            "owned_partner_ids": [entry.partner_id for entry in player.owned_partners],
            "updated_at": player.updated_at,
        }

    def _now(self) -> int:
        return int(self.clock())
