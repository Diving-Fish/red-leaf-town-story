from __future__ import annotations

import random
import time
from collections.abc import Callable
from math import ceil, floor

from red_leaf_town.content import GameContent
from red_leaf_town.domain import (
    CraftingStationState,
    GatheringSiteState,
    MiningSiteState,
    OwnedPartnerState,
    PlayerState,
    PortalProgressState,
    PortalTributeProgress,
    ProductionResultSnapshot,
    ProductionTaskSnapshot,
    QQIdentity,
    TaskPartnerSnapshot,
    TaskInputSnapshot,
    TaskQualitySnapshot,
)
from red_leaf_town.domain.economy import EconomyError, add_item, grant_coins, remove_item, spend_coins
from red_leaf_town.domain.progression import (
    consume_stamina,
    grant_experience,
    normalize_crafting_stations,
    normalize_gathering_sites,
    normalize_mining_sites,
    normalize_plot_slots,
    settle_stamina,
)
from red_leaf_town.domain.quality import QUALITY_NAMES, quality_probabilities, roll_quality
from red_leaf_town.recipe_unlocks import describe_recipe_unlock, evaluate_recipe_unlock
from red_leaf_town.partner_content import (
    GROWTH_CURVE_NAMES,
    INDUSTRY_NAMES,
    PartnerCatalog,
    level_cap_for_breakthrough,
    load_partner_catalog,
)
from red_leaf_town.partner_traits import partner_trait_catalog
from red_leaf_town.rewards import serialize_reward
from red_leaf_town.story_assets import StoryAssetCatalog, load_story_asset_catalog
from red_leaf_town.story_content import StoryCatalog, load_story_catalog, serialize_script
from red_leaf_town.story_triggers import StoryContext, validate_story_cue

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
        story_catalog_loader: Callable[[], StoryCatalog] = load_story_catalog,
        story_asset_loader: Callable[[], StoryAssetCatalog] = load_story_asset_catalog,
    ):
        self.content = content
        self.repository = repository
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.partner_catalog_loader = partner_catalog_loader
        self.story_catalog_loader = story_catalog_loader
        self.story_asset_loader = story_asset_loader

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

    def assign_gathering_partner(self, oauth_sub: str, site_id: str, partner_id: str = "") -> dict:
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._gathering_site(player, site_id)
            desired_ids = [partner_id] if partner_id else []
            if site.assigned_partner_ids == desired_ids:
                return {"site_id": site_id, "partner_id": partner_id or None, "changed": False}
            if site.task_snapshot is not None and site.task_snapshot.ready_at > now:
                raise GameError("partner_assignment_locked", "采集进行中，不能调整这个采集点的伙伴", 409)

            locked_until = self._partner_lock_deadlines(player, now)
            affected_ids = set(site.assigned_partner_ids)
            if partner_id:
                affected_ids.add(partner_id)
            if any(locked_until.get(candidate, 0) > now for candidate in affected_ids):
                raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能移动", 409)

            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                definition = catalog.partner_map.get(partner_id)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "gathering" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有采集倾向", 409)

            if partner_id:
                self._clear_partner_assignment(player, partner_id)
            site.assigned_partner_ids = desired_ids
            if self._industry_assigned_count(player, "gathering") > self._industry_partner_capacity(player, "gathering"):
                raise GameError("partner_capacity_reached", "当前采集伙伴编制已满", 409)
            return {"site_id": site_id, "partner_id": partner_id or None, "changed": True}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def start_gathering(self, oauth_sub: str, site_id: str, task_id: str) -> dict:
        task = self.content.gathering_task_map.get(task_id)
        if task is None or task.site_id != site_id:
            raise GameError("gathering_task_not_found", "这个采集点没有该任务", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._gathering_site(player, site_id)
            if player.level < task.min_level:
                raise GameError("content_locked", f"达到 {task.min_level} 级后解锁")
            if not site.empty:
                raise GameError("gathering_site_occupied", "这个采集点已有任务")
            if len(site.assigned_partner_ids) != 1:
                raise GameError("gathering_partner_required", "必须先派一名具有采集倾向的伙伴前往", 409)
            if self._industry_assigned_count(player, "gathering") > self._industry_partner_capacity(player, "gathering"):
                raise GameError("partner_capacity_reached", "当前采集伙伴编制已满", 409)
            snapshot = self._build_production_task_snapshot(
                player=player,
                assigned_partner_ids=site.assigned_partner_ids,
                industry="gathering",
                content_id=task.id,
                production_slot_id=f"gathering:site:{site.site_id}",
                now=now,
                base_duration=task.duration_seconds,
                time_difficulty=task.time_difficulty,
                produce_item_id=task.produce_item_id,
                yield_min=task.yield_min,
                yield_max=task.yield_max,
                harvest_xp=task.collect_xp,
                quality=task.quality,
            )
            try:
                consume_stamina(player, task.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            site.task_snapshot = snapshot
            site.task_result = None
            return {
                "site_id": site_id,
                "task_id": task_id,
                "ready_at": snapshot.ready_at,
                "base_duration": snapshot.base_duration,
                "final_duration": snapshot.final_duration,
                "total_ability": snapshot.total_ability,
                "quality_ability": snapshot.quality_parameters.ability,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def collect_gathering(self, oauth_sub: str, site_id: str) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._gathering_site(player, site_id)
            if site.task_snapshot is None:
                raise GameError("gathering_site_empty", "这个采集点没有进行中的任务")
            if site.task_snapshot.ready_at > now:
                raise GameError("gathering_not_ready", "伙伴还没有完成采集")
            result = site.task_result
            if result is None:
                raise GameError("task_content_missing", "采集任务配置缺失，请联系管理员", 409)
            harvest_xp = site.task_snapshot.harvest_xp
            add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, harvest_xp, self.content)
            site.task_snapshot = None
            site.task_result = None
            return {
                "site_id": site_id,
                "item_id": result.item_id,
                "quantity": result.quantity,
                "quality": result.quality,
                "quality_name": QUALITY_NAMES[result.quality],
                "experience": harvest_xp,
                "levels": levels,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def assign_crafting_partner(self, oauth_sub: str, station_id: str, partner_id: str = "") -> dict:
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            self._settle(player, now)
            station = self._crafting_station(player, station_id)
            desired_ids = [partner_id] if partner_id else []
            if station.assigned_partner_ids == desired_ids:
                return {"station_id": station_id, "partner_id": partner_id or None, "changed": False}
            if station.task_snapshot is not None and station.task_snapshot.ready_at > now:
                raise GameError("partner_assignment_locked", "加工进行中，不能调整这个工位的伙伴", 409)

            locked_until = self._partner_lock_deadlines(player, now)
            affected_ids = set(station.assigned_partner_ids)
            if partner_id:
                affected_ids.add(partner_id)
            if any(locked_until.get(candidate, 0) > now for candidate in affected_ids):
                raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能移动", 409)

            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                definition = catalog.partner_map.get(partner_id)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "crafting" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有加工倾向", 409)

            if partner_id:
                self._clear_partner_assignment(player, partner_id)
            station.assigned_partner_ids = desired_ids
            if self._industry_assigned_count(player, "crafting") > self._industry_partner_capacity(player, "crafting"):
                raise GameError("partner_capacity_reached", "当前加工伙伴编制已满", 409)
            return {"station_id": station_id, "partner_id": partner_id or None, "changed": True}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def start_crafting(self, oauth_sub: str, station_id: str, recipe_id: str) -> dict:
        recipe = self.content.recipe_map.get(recipe_id)
        if recipe is None or recipe.station_id != station_id:
            raise GameError("recipe_not_found", "这个工位没有该配方", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            station = self._crafting_station(player, station_id)
            condition = recipe.unlock_condition
            if not evaluate_recipe_unlock(player, condition.hook, condition.params):
                raise GameError(
                    "recipe_locked",
                    f"配方尚未解锁：{describe_recipe_unlock(condition.hook, condition.params)}",
                    409,
                )
            if not station.empty:
                raise GameError("crafting_station_occupied", "这个工位已有加工任务")
            if self._industry_assigned_count(player, "crafting") > self._industry_partner_capacity(player, "crafting"):
                raise GameError("partner_capacity_reached", "当前加工伙伴编制已满", 409)
            consumed_inputs = self._consume_recipe_inputs(player, recipe)
            snapshot = self._build_production_task_snapshot(
                player=player,
                assigned_partner_ids=station.assigned_partner_ids,
                industry="crafting",
                content_id=recipe.id,
                production_slot_id=f"crafting:station:{station.station_id}",
                now=now,
                base_duration=recipe.duration_seconds,
                time_difficulty=recipe.time_difficulty,
                produce_item_id=recipe.produce_item_id,
                yield_min=recipe.produce_quantity,
                yield_max=recipe.produce_quantity,
                harvest_xp=recipe.collect_xp,
                quality=recipe.quality,
                consumed_inputs=consumed_inputs,
            )
            try:
                consume_stamina(player, recipe.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            station.task_snapshot = snapshot
            station.task_result = None
            return {
                "station_id": station_id,
                "recipe_id": recipe_id,
                "ready_at": snapshot.ready_at,
                "base_duration": snapshot.base_duration,
                "final_duration": snapshot.final_duration,
                "total_ability": snapshot.total_ability,
                "quality_ability": snapshot.quality_parameters.ability,
                "consumed_inputs": [entry.model_dump() for entry in consumed_inputs],
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def collect_crafting(self, oauth_sub: str, station_id: str) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            station = self._crafting_station(player, station_id)
            if station.task_snapshot is None:
                raise GameError("crafting_station_empty", "这个工位没有进行中的任务")
            if station.task_snapshot.ready_at > now:
                raise GameError("crafting_not_ready", "加工还没有完成")
            result = station.task_result
            if result is None:
                raise GameError("task_content_missing", "加工任务配置缺失，请联系管理员", 409)
            collect_xp = station.task_snapshot.harvest_xp
            add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, collect_xp, self.content)
            station.task_snapshot = None
            station.task_result = None
            return {
                "station_id": station_id,
                "item_id": result.item_id,
                "quantity": result.quantity,
                "quality": result.quality,
                "quality_name": QUALITY_NAMES[result.quality],
                "experience": collect_xp,
                "levels": levels,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def assign_mining_partner(self, oauth_sub: str, site_id: str, partner_id: str = "") -> dict:
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._mining_site(player, site_id)
            desired_ids = [partner_id] if partner_id else []
            if site.assigned_partner_ids == desired_ids:
                return {"site_id": site_id, "partner_id": partner_id or None, "changed": False}
            if site.task_snapshot is not None and site.task_snapshot.ready_at > now:
                raise GameError("partner_assignment_locked", "采矿进行中，不能调整这个矿点的伙伴", 409)

            locked_until = self._partner_lock_deadlines(player, now)
            affected_ids = set(site.assigned_partner_ids)
            if partner_id:
                affected_ids.add(partner_id)
            if any(locked_until.get(candidate, 0) > now for candidate in affected_ids):
                raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能移动", 409)

            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                definition = catalog.partner_map.get(partner_id)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "mining" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有矿产倾向", 409)

            if partner_id:
                self._clear_partner_assignment(player, partner_id)
            site.assigned_partner_ids = desired_ids
            if self._industry_assigned_count(player, "mining") > self._industry_partner_capacity(player, "mining"):
                raise GameError("partner_capacity_reached", "当前矿产伙伴编制已满", 409)
            return {"site_id": site_id, "partner_id": partner_id or None, "changed": True}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def start_mining(self, oauth_sub: str, site_id: str, task_id: str) -> dict:
        task = self.content.mining_task_map.get(task_id)
        if task is None or task.site_id != site_id:
            raise GameError("mining_task_not_found", "这个矿点没有该任务", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._mining_site(player, site_id)
            if player.level < task.min_level:
                raise GameError("content_locked", f"达到 {task.min_level} 级后解锁")
            if not site.empty:
                raise GameError("mining_site_occupied", "这个矿点已有任务")
            if self._industry_assigned_count(player, "mining") > self._industry_partner_capacity(player, "mining"):
                raise GameError("partner_capacity_reached", "当前矿产伙伴编制已满", 409)
            snapshot = self._build_production_task_snapshot(
                player=player,
                assigned_partner_ids=site.assigned_partner_ids,
                industry="mining",
                content_id=task.id,
                production_slot_id=f"mining:site:{site.site_id}",
                now=now,
                base_duration=task.duration_seconds,
                time_difficulty=task.time_difficulty,
                produce_item_id=task.produce_item_id,
                yield_min=task.yield_min,
                yield_max=task.yield_max,
                harvest_xp=task.collect_xp,
                quality=task.quality,
            )
            try:
                consume_stamina(player, task.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            site.task_snapshot = snapshot
            site.task_result = None
            return {
                "site_id": site_id,
                "task_id": task_id,
                "ready_at": snapshot.ready_at,
                "base_duration": snapshot.base_duration,
                "final_duration": snapshot.final_duration,
                "total_ability": snapshot.total_ability,
                "quality_ability": snapshot.quality_parameters.ability,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def collect_mining(self, oauth_sub: str, site_id: str) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            site = self._mining_site(player, site_id)
            if site.task_snapshot is None:
                raise GameError("mining_site_empty", "这个矿点没有进行中的任务")
            if site.task_snapshot.ready_at > now:
                raise GameError("mining_not_ready", "采矿还没有完成")
            result = site.task_result
            if result is None:
                raise GameError("task_content_missing", "采矿任务配置缺失，请联系管理员", 409)
            collect_xp = site.task_snapshot.harvest_xp
            add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, collect_xp, self.content)
            site.task_snapshot = None
            site.task_result = None
            return {
                "site_id": site_id,
                "item_id": result.item_id,
                "quantity": result.quantity,
                "quality": result.quality,
                "quality_name": QUALITY_NAMES[result.quality],
                "experience": collect_xp,
                "levels": levels,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def unlock_talent(self, oauth_sub: str, node_id: str) -> dict:
        node = self.content.talent_map.get(node_id)
        if node is None:
            raise GameError("talent_not_found", "天赋节点不存在", 404)

        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if node_id in player.talent_nodes:
                raise GameError("talent_already_unlocked", "这个天赋已经点亮", 409)
            if player.level < node.min_level:
                raise GameError("talent_level_required", f"达到 {node.min_level} 级后才能点亮")
            if any(prerequisite not in player.talent_nodes for prerequisite in node.prerequisites):
                raise GameError("talent_prerequisite_required", "请先点亮前置天赋")
            if self._available_talent_points(player) < node.cost:
                raise GameError("talent_points_insufficient", "天赋点不足")
            player.talent_nodes.append(node_id)
            return {
                "node_id": node_id,
                "industry": node.industry,
                "partner_capacity": self._industry_partner_capacity(player, node.industry),
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

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

            if partner_id:
                self._clear_partner_assignment(player, partner_id)
            plot.assigned_partner_ids = desired_ids
            assigned_count = self._industry_assigned_count(player, "farming")
            if assigned_count > self._industry_partner_capacity(player, "farming"):
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
        if not item.has_quality and quality != 0:
            raise GameError("invalid_quality", "该物品不使用品质")
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            selected_quality = quality
            if item.has_quality and selected_quality == 0:
                available = [
                    candidate
                    for candidate, amount in player.inventory.get(item_id, {}).items()
                    if candidate in self.content.quality.grade_map and amount > 0
                ]
                if len(available) != 1:
                    raise GameError("invalid_quality", "请选择要出售的物品品质")
                selected_quality = available[0]
            if item.has_quality and selected_quality not in self.content.quality.grade_map:
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

    def deliver_tribute(self, oauth_sub: str, portal_id: str, tribute_id: str, quantity: int) -> dict:
        """往传送门交一批贡品。交满这一项就结算它的奖励，全部交满再结算全完成奖励。"""
        portal = self.content.portal_map.get(portal_id)
        tribute = next((entry for entry in portal.tributes if entry.id == tribute_id), None) if portal else None
        if portal is None or tribute is None:
            raise GameError("tribute_not_found", "这个传送门没有该贡品", 404)
        requested = int(quantity)
        if requested <= 0:
            raise GameError("invalid_quantity", "交付数量必须为正数")
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if not self._portal_unlocked(player, portal):
                raise GameError("portal_locked", f"传送门尚未开启：{self._portal_locked_reason(player, portal)}", 409)
            progress = self._portal_progress(player, portal)
            entry = progress.tribute(tribute_id)
            if entry.completed_at:
                raise GameError("tribute_completed", "这项贡品已经交齐了", 409)

            remaining = tribute.quantity - entry.delivered
            accepted = min(requested, remaining)
            available = self._eligible_quantity(player, tribute)
            if available < accepted:
                item = self.content.item_map.get(tribute.item_id)
                name = item.name if item else tribute.item_id
                requirement = f"{QUALITY_NAMES[tribute.min_quality]}以上的" if tribute.min_quality else ""
                raise GameError("resource_insufficient", f"{requirement}{name}数量不足")

            consumed = self._consume_tribute(player, tribute, accepted)
            entry.delivered += accepted
            rewards = []
            if entry.delivered >= tribute.quantity:
                entry.completed_at = now
                rewards.append({"source": "tribute", "label": self._tribute_label(tribute), **self._grant_reward(player, tribute.reward, now)})
            portal_completed = False
            unlocked_portals: list[dict] = []
            if not progress.completed_at and all(item.completed_at for item in progress.tributes):
                progress.completed_at = now
                portal_completed = True
                rewards.append({"source": "portal", "label": portal.name, **self._grant_reward(player, portal.completion_reward, now)})
                unlocked_portals = self._newly_unlocked_portals(player, portal)
            return {
                "portal_id": portal.id,
                "portal_name": portal.name,
                "tribute_id": tribute_id,
                "delivered": accepted,
                "total_delivered": entry.delivered,
                "required": tribute.quantity,
                "tribute_completed": bool(entry.completed_at),
                "portal_completed": portal_completed,
                "consumed": [snapshot.model_dump() for snapshot in consumed],
                "rewards": rewards,
                "unlocked_portals": unlocked_portals,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def _portal_unlocked(self, player: PlayerState, portal) -> bool:
        if player.level < portal.min_level:
            return False
        completed = self._completed_portal_ids(player)
        return all(entry in completed for entry in portal.prerequisites)

    def _portal_locked_reason(self, player: PlayerState, portal) -> str:
        if player.level < portal.min_level:
            return f"居民等级达到 {portal.min_level} 级"
        completed = self._completed_portal_ids(player)
        missing = [
            self.content.portal_map[entry].name
            for entry in portal.prerequisites
            if entry not in completed and entry in self.content.portal_map
        ]
        return f"先完成{'、'.join(missing)}" if missing else "条件未满足"

    @staticmethod
    def _completed_portal_ids(player: PlayerState) -> set[str]:
        return {entry.portal_id for entry in player.portals if entry.completed_at}

    def _portal_progress(self, player: PlayerState, portal) -> PortalProgressState:
        """进度按需建档，并补上内容里新增的贡品条目。"""
        progress = next((entry for entry in player.portals if entry.portal_id == portal.id), None)
        if progress is None:
            progress = PortalProgressState(portal_id=portal.id)
            player.portals.append(progress)
        recorded = {entry.tribute_id for entry in progress.tributes}
        progress.tributes.extend(
            PortalTributeProgress(tribute_id=tribute.id)
            for tribute in portal.tributes
            if tribute.id not in recorded
        )
        return progress

    def _tribute_label(self, tribute) -> str:
        item = self.content.item_map.get(tribute.item_id)
        prefix = f"{QUALITY_NAMES[tribute.min_quality]}以上的" if tribute.min_quality else ""
        return f"{prefix}{item.name if item else tribute.item_id} ×{tribute.quantity}"

    def _eligible_quantity(self, player: PlayerState, tribute) -> int:
        return sum(
            quantity
            for quality, quantity in player.inventory.get(tribute.item_id, {}).items()
            if quality >= tribute.min_quality
        )

    def _consume_tribute(self, player: PlayerState, tribute, amount: int) -> list[TaskInputSnapshot]:
        """够格的品质里优先扣最低的，玩家不会被贡品吃掉臻品。"""
        consumed: list[TaskInputSnapshot] = []
        remaining = amount
        qualities = player.inventory.get(tribute.item_id, {})
        for quality, owned in sorted(qualities.items()):
            if quality < tribute.min_quality or remaining <= 0:
                continue
            taken = min(owned, remaining)
            remove_item(player, tribute.item_id, taken, quality)
            consumed.append(TaskInputSnapshot(item_id=tribute.item_id, quality=quality, quantity=taken))
            remaining -= taken
        return consumed

    def _grant_reward(self, player: PlayerState, reward, now: int) -> dict:
        granted_items = []
        for entry in reward.items:
            add_item(player, entry.item_id, entry.quantity, entry.quality)
            item = self.content.item_map.get(entry.item_id)
            granted_items.append({
                "item_id": entry.item_id,
                "name": item.name if item else entry.item_id,
                "quantity": entry.quantity,
                "quality": entry.quality or None,
                "quality_name": QUALITY_NAMES.get(entry.quality),
            })
        granted_partners = []
        partner_map = self.partner_catalog_loader().partner_map
        for partner_id in reward.partner_ids:
            if partner_id not in partner_map:
                continue
            if any(owned.partner_id == partner_id for owned in player.owned_partners):
                continue
            player.owned_partners.append(OwnedPartnerState(partner_id=partner_id, acquired_at=now))
            granted_partners.append({"partner_id": partner_id, "name": partner_map[partner_id].name})
        if reward.coins:
            grant_coins(player, reward.coins)
        if reward.talent_points:
            player.bonus_talent_points += reward.talent_points
        levels = grant_experience(player, reward.experience, self.content) if reward.experience else []
        return {
            "coins": reward.coins,
            "experience": reward.experience,
            "talent_points": reward.talent_points,
            "items": granted_items,
            "partners": granted_partners,
            "levels": levels,
        }

    def _newly_unlocked_portals(self, player: PlayerState, completed) -> list[dict]:
        return [
            {"portal_id": portal.id, "name": portal.name}
            for portal in self.content.portals
            if completed.id in portal.prerequisites and self._portal_unlocked(player, portal)
        ]

    def story_cue(self, oauth_sub: str, cue: str) -> dict:
        """返回这个信号下应该立即播放的剧情，已经看过的一次性剧本不再返回。"""
        try:
            code = validate_story_cue(cue)
        except ValueError as exc:
            raise GameError("invalid_story_cue", "剧情信号格式不正确") from exc
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        catalog = self.story_catalog_loader()
        context = StoryContext(player=player, cue=code, now=self._now())
        matched = catalog.matching(context, set(player.seen_story_ids))
        assets = self.story_asset_loader()
        partners = self.partner_catalog_loader()
        return {
            "cue": code,
            "stories": [serialize_script(script, assets, partners, self.content) for script in matched],
        }

    def mark_story_seen(self, oauth_sub: str, story_id: str) -> dict:
        script = self.story_catalog_loader().script_map.get(story_id)
        if script is None:
            raise GameError("story_not_found", "剧情不存在", 404)
        now = self._now()

        def mutation(player: PlayerState):
            if script.id in player.seen_story_ids:
                return {"story_id": script.id, "granted": None}
            player.seen_story_ids.append(script.id)
            # 奖励只在第一次播完时结算，重复上报不会再发一次。
            granted = None if script.rewards.empty else self._grant_reward(player, script.rewards, now)
            return {"story_id": script.id, "granted": granted}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def story_scripts(self) -> list[dict]:
        assets = self.story_asset_loader()
        partners = self.partner_catalog_loader()
        return [serialize_script(script, assets, partners, self.content) for script in self.story_catalog_loader().scripts]

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

    def admin_delete_player(self, player_id: str) -> dict:
        """彻底删除一个角色。存档不可恢复，玩家再次登录会当作新居民重新建号。"""
        player = self.repository.get(player_id)
        if not player:
            raise GameError("player_not_found", "玩家不存在", 404)
        summary = self._admin_player_summary(player)
        if not self.repository.delete(player_id):
            raise GameError("player_not_found", "玩家不存在", 404)
        return {"player": summary}

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
        normalize_gathering_sites(player, self.content)
        normalize_crafting_stations(player, self.content)
        normalize_mining_sites(player, self.content)
        settle_stamina(player, self.content, now)
        for plot in player.plots:
            if not plot.empty and plot.ready_at <= now and plot.task_result is None:
                self._resolve_output(plot, now, self.content.crop_map.get(plot.crop_id))
        for site in player.gathering_sites:
            if site.task_snapshot and site.task_snapshot.ready_at <= now and site.task_result is None:
                self._resolve_output(site, now)
        for station in player.crafting_stations:
            if station.task_snapshot and station.task_snapshot.ready_at <= now and station.task_result is None:
                self._resolve_output(station, now)
        for site in player.mining_sites:
            if site.task_snapshot and site.task_snapshot.ready_at <= now and site.task_result is None:
                self._resolve_output(site, now)

    def _plot(self, player: PlayerState, slot: int):
        if slot < 0 or slot >= len(player.plots):
            raise GameError("plot_locked", "这块土地尚未解锁")
        return player.plots[slot]

    def _gathering_site(self, player: PlayerState, site_id: str) -> GatheringSiteState:
        site = next((entry for entry in player.gathering_sites if entry.site_id == site_id), None)
        if site is None:
            raise GameError("gathering_site_locked", "这个采集点尚未解锁", 404)
        return site

    def _crafting_station(self, player: PlayerState, station_id: str) -> CraftingStationState:
        station = next((entry for entry in player.crafting_stations if entry.station_id == station_id), None)
        if station is None:
            raise GameError("crafting_station_locked", "这个加工工位尚未解锁", 404)
        return station

    def _mining_site(self, player: PlayerState, site_id: str) -> MiningSiteState:
        site = next((entry for entry in player.mining_sites if entry.site_id == site_id), None)
        if site is None:
            raise GameError("mining_site_locked", "这个矿点尚未解锁", 404)
        return site

    def _build_farming_task_snapshot(self, player, plot, crop, now: int) -> ProductionTaskSnapshot:
        if self._industry_assigned_count(player, "farming") > self._industry_partner_capacity(player, "farming"):
            raise GameError("partner_capacity_reached", "当前农作伙伴编制已满", 409)
        return self._build_production_task_snapshot(
            player=player,
            assigned_partner_ids=plot.assigned_partner_ids,
            industry="farming",
            content_id=crop.id,
            production_slot_id=f"farm:plot:{plot.slot}",
            now=now,
            base_duration=crop.growth_seconds,
            time_difficulty=crop.time_difficulty,
            produce_item_id=crop.produce_item_id,
            yield_min=crop.yield_min,
            yield_max=crop.yield_max,
            harvest_xp=crop.harvest_xp,
            quality=crop.quality,
        )

    def _build_production_task_snapshot(
        self,
        *,
        player: PlayerState,
        assigned_partner_ids: list[str],
        industry: str,
        content_id: str,
        production_slot_id: str,
        now: int,
        base_duration: int,
        time_difficulty: int,
        produce_item_id: str,
        yield_min: int,
        yield_max: int,
        harvest_xp: int,
        quality,
        consumed_inputs: list[TaskInputSnapshot] | None = None,
    ) -> ProductionTaskSnapshot:
        rules = self.content.industries[industry]
        if len(assigned_partner_ids) > rules.collaborator_slots:
            raise GameError("collaborator_slots_exceeded", "这个生产格的伙伴位置超过当前上限", 409)
        catalog = self.partner_catalog_loader()
        owned_map = {entry.partner_id: entry for entry in player.owned_partners}
        partner_snapshots: list[TaskPartnerSnapshot] = []
        for partner_id in assigned_partner_ids:
            owned = owned_map.get(partner_id)
            definition = catalog.partner_map.get(partner_id)
            if owned is None or definition is None:
                raise GameError("partner_assignment_invalid", "驻场伙伴数据无效，请重新安排", 409)
            tendency = next(
                (entry for entry in definition.tendencies if entry.industry == industry),
                None,
            )
            if tendency is None:
                raise GameError("partner_tendency_mismatch", "驻场伙伴没有对应产业倾向，请重新安排", 409)
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
                ability=definition.ability_at(industry, effective_level),
            ))

        character_ability = rules.character_base_ability
        total_ability = character_ability + sum(entry.ability for entry in partner_snapshots)
        time_efficiency = 1 + 2 * total_ability / (total_ability + time_difficulty)
        final_duration = max(1, ceil(base_duration / time_efficiency))
        probabilities = quality_probabilities(
            total_ability,
            quality.thresholds,
            quality.width,
            quality.miracle_probability_cap,
            quality.miracle_eligible,
        )
        return ProductionTaskSnapshot(
            industry=industry,
            content_id=content_id,
            production_slot_id=production_slot_id,
            started_at=now,
            ready_at=now + final_duration,
            assigned_partner_ids=list(assigned_partner_ids),
            support_partner_ids=[],
            partner_snapshots=partner_snapshots,
            applied_effects=[],
            character_ability=character_ability,
            total_ability=total_ability,
            time_efficiency=time_efficiency,
            base_duration=base_duration,
            final_duration=final_duration,
            produce_item_id=produce_item_id,
            yield_min=yield_min,
            yield_max=yield_max,
            harvest_xp=harvest_xp,
            consumed_inputs=consumed_inputs or [],
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
        for production_slot in [*player.plots, *player.gathering_sites, *player.crafting_stations, *player.mining_sites]:
            task = production_slot.task_snapshot
            if task is None or task.ready_at <= now:
                continue
            for partner_id in {*task.assigned_partner_ids, *task.support_partner_ids}:
                deadlines[partner_id] = max(deadlines.get(partner_id, 0), task.ready_at)
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
        gathering_sites = []
        gathering_task_map = self.content.gathering_task_map
        for site in player.gathering_sites:
            definition = self.content.gathering_site_map.get(site.site_id)
            task_snapshot = site.task_snapshot
            assigned_partners = [
                partner_map[partner_id]
                for partner_id in site.assigned_partner_ids
                if partner_id in partner_map
            ]
            assignment_locked_until = max(
                (lock_deadlines.get(partner_id, 0) for partner_id in site.assigned_partner_ids),
                default=0,
            )
            gathering_sites.append({
                **site.model_dump(),
                "empty": site.empty,
                "ready": bool(task_snapshot and task_snapshot.ready_at <= now),
                "remaining_seconds": max(0, task_snapshot.ready_at - now) if task_snapshot else 0,
                "definition": definition.model_dump() if definition else None,
                "task": {
                    **gathering_task_map[task_snapshot.content_id].model_dump(),
                    "item": items[gathering_task_map[task_snapshot.content_id].produce_item_id].model_dump(),
                } if task_snapshot and task_snapshot.content_id in gathering_task_map else None,
                "available_tasks": [
                    {**entry.model_dump(), "item": items[entry.produce_item_id].model_dump()}
                    for entry in self.content.gathering_tasks
                    if entry.site_id == site.site_id and entry.min_level <= player.level
                ],
                "assigned_partners": assigned_partners,
                "assignment_locked": assignment_locked_until > now,
                "assignment_locked_until": assignment_locked_until or None,
            })
        unlocked_gathering_site_ids = {site.site_id for site in player.gathering_sites}
        next_gathering_site_level = next(
            (
                definition.min_level
                for definition in self.content.gathering_sites
                if definition.id not in unlocked_gathering_site_ids
            ),
            None,
        )
        crafting_stations = []
        recipe_map = self.content.recipe_map
        for station in player.crafting_stations:
            definition = self.content.crafting_station_map.get(station.station_id)
            task_snapshot = station.task_snapshot
            assigned_partners = [
                partner_map[partner_id]
                for partner_id in station.assigned_partner_ids
                if partner_id in partner_map
            ]
            assignment_locked_until = max(
                (lock_deadlines.get(partner_id, 0) for partner_id in station.assigned_partner_ids),
                default=0,
            )
            crafting_stations.append({
                **station.model_dump(),
                "empty": station.empty,
                "ready": bool(task_snapshot and task_snapshot.ready_at <= now),
                "remaining_seconds": max(0, task_snapshot.ready_at - now) if task_snapshot else 0,
                "definition": definition.model_dump() if definition else None,
                "recipe": self._recipe_snapshot(player, recipe_map[task_snapshot.content_id])
                if task_snapshot and task_snapshot.content_id in recipe_map else None,
                "recipes": [
                    self._recipe_snapshot(player, recipe)
                    for recipe in self.content.recipes
                    if recipe.station_id == station.station_id
                ],
                "assigned_partners": assigned_partners,
                "assignment_locked": assignment_locked_until > now,
                "assignment_locked_until": assignment_locked_until or None,
            })
        unlocked_crafting_station_ids = {station.station_id for station in player.crafting_stations}
        next_crafting_station_level = next(
            (
                definition.min_level
                for definition in self.content.crafting_stations
                if definition.id not in unlocked_crafting_station_ids
            ),
            None,
        )
        mining_sites = []
        mining_task_map = self.content.mining_task_map
        for site in player.mining_sites:
            definition = self.content.mining_site_map.get(site.site_id)
            task_snapshot = site.task_snapshot
            assigned_partners = [
                partner_map[partner_id]
                for partner_id in site.assigned_partner_ids
                if partner_id in partner_map
            ]
            assignment_locked_until = max(
                (lock_deadlines.get(partner_id, 0) for partner_id in site.assigned_partner_ids),
                default=0,
            )
            mining_sites.append({
                **site.model_dump(),
                "empty": site.empty,
                "ready": bool(task_snapshot and task_snapshot.ready_at <= now),
                "remaining_seconds": max(0, task_snapshot.ready_at - now) if task_snapshot else 0,
                "definition": definition.model_dump() if definition else None,
                "task": {
                    **mining_task_map[task_snapshot.content_id].model_dump(),
                    "item": items[mining_task_map[task_snapshot.content_id].produce_item_id].model_dump(),
                } if task_snapshot and task_snapshot.content_id in mining_task_map else None,
                "available_tasks": [
                    {**entry.model_dump(), "item": items[entry.produce_item_id].model_dump()}
                    for entry in self.content.mining_tasks
                    if entry.site_id == site.site_id and entry.min_level <= player.level
                ],
                "assigned_partners": assigned_partners,
                "assignment_locked": assignment_locked_until > now,
                "assignment_locked_until": assignment_locked_until or None,
            })
        unlocked_mining_site_ids = {site.site_id for site in player.mining_sites}
        next_mining_site_level = next(
            (
                definition.min_level
                for definition in self.content.mining_sites
                if definition.id not in unlocked_mining_site_ids
            ),
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
            "gathering_sites": gathering_sites,
            "next_gathering_site_level": next_gathering_site_level,
            "crafting_stations": crafting_stations,
            "next_crafting_station_level": next_crafting_station_level,
            "mining_sites": mining_sites,
            "next_mining_site_level": next_mining_site_level,
            "inventory": inventory,
            "partners": partner_records,
            "partner_count": len(partner_records),
            "industry_rules": {
                industry: {
                    **rules.model_dump(),
                    "base_partner_capacity": rules.partner_capacity,
                    "partner_capacity": self._industry_partner_capacity(player, industry),
                }
                for industry, rules in self.content.industries.items()
            },
            "talents": self._talent_snapshot(player),
            "portals": self._portal_snapshot(player),
            "crops": [
                crop.model_dump()
                for crop in self.content.crops
                if player.level >= crop.min_level
            ],
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
        assigned_gathering_sites = {
            partner_id: site.site_id
            for site in player.gathering_sites
            for partner_id in site.assigned_partner_ids
        }
        assigned_crafting_stations = {
            partner_id: station.station_id
            for station in player.crafting_stations
            for partner_id in station.assigned_partner_ids
        }
        assigned_mining_sites = {
            partner_id: site.site_id
            for site in player.mining_sites
            for partner_id in site.assigned_partner_ids
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
                    "assigned_gathering_site_id": assigned_gathering_sites.get(owned.partner_id),
                    "assigned_crafting_station_id": assigned_crafting_stations.get(owned.partner_id),
                    "assigned_mining_site_id": assigned_mining_sites.get(owned.partner_id),
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
                "assigned_gathering_site_id": assigned_gathering_sites.get(owned.partner_id),
                "assigned_crafting_station_id": assigned_crafting_stations.get(owned.partner_id),
                "assigned_mining_site_id": assigned_mining_sites.get(owned.partner_id),
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

    @staticmethod
    def _clear_partner_assignment(player: PlayerState, partner_id: str) -> None:
        for production_slot in [
            *player.plots,
            *player.gathering_sites,
            *player.crafting_stations,
            *player.mining_sites,
        ]:
            if partner_id in production_slot.assigned_partner_ids:
                production_slot.assigned_partner_ids = []

    @staticmethod
    def _industry_assigned_count(player: PlayerState, industry: str) -> int:
        if industry == "farming":
            return sum(len(plot.assigned_partner_ids) for plot in player.plots)
        if industry == "gathering":
            return sum(len(site.assigned_partner_ids) for site in player.gathering_sites)
        if industry == "crafting":
            return sum(len(station.assigned_partner_ids) for station in player.crafting_stations)
        if industry == "mining":
            return sum(len(site.assigned_partner_ids) for site in player.mining_sites)
        return 0

    def _industry_partner_capacity(self, player: PlayerState, industry: str) -> int:
        rules = self.content.industries[industry]
        bonuses = sum(
            node.partner_capacity_bonus
            for node_id in player.talent_nodes
            if (node := self.content.talent_map.get(node_id)) is not None and node.industry == industry
        )
        return rules.partner_capacity + bonuses

    def _available_talent_points(self, player: PlayerState) -> int:
        spent = sum(
            node.cost
            for node_id in player.talent_nodes
            if (node := self.content.talent_map.get(node_id)) is not None
        )
        return max(0, player.level - 1 + player.bonus_talent_points - spent)

    def _reward_snapshot(self, reward) -> dict:
        return serialize_reward(reward, self.content, self.partner_catalog_loader())

    def _portal_snapshot(self, player: PlayerState) -> list[dict]:
        items = self.content.item_map
        progress_map = {entry.portal_id: entry for entry in player.portals}
        completed_ids = self._completed_portal_ids(player)
        portals = []
        for portal in self.content.portals:
            progress = progress_map.get(portal.id)
            unlocked = self._portal_unlocked(player, portal)
            tributes = []
            for tribute in portal.tributes:
                recorded = progress.tribute(tribute.id) if progress else None
                delivered = min(recorded.delivered, tribute.quantity) if recorded else 0
                item = items.get(tribute.item_id)
                owned = self._eligible_quantity(player, tribute)
                remaining = max(0, tribute.quantity - delivered)
                tributes.append({
                    "id": tribute.id,
                    "item_id": tribute.item_id,
                    "name": item.name if item else tribute.item_id,
                    "icon": item.icon if item else "package",
                    "quantity": tribute.quantity,
                    "min_quality": tribute.min_quality or None,
                    "min_quality_name": QUALITY_NAMES.get(tribute.min_quality),
                    "delivered": delivered,
                    "remaining": remaining,
                    # 一次能交多少：手里够格的和还缺的取小。
                    "deliverable": min(owned, remaining),
                    "owned": owned,
                    "completed": bool(recorded and recorded.completed_at),
                    "reward": self._reward_snapshot(tribute.reward),
                })
            completed_count = sum(1 for entry in tributes if entry["completed"])
            portals.append({
                "portal_id": portal.id,
                "name": portal.name,
                "description": portal.description,
                "accent": portal.accent,
                "min_level": portal.min_level,
                "prerequisites": [
                    {
                        "portal_id": entry,
                        "name": self.content.portal_map[entry].name if entry in self.content.portal_map else entry,
                        "completed": entry in completed_ids,
                    }
                    for entry in portal.prerequisites
                ],
                "unlocked": unlocked,
                "locked_reason": None if unlocked else self._portal_locked_reason(player, portal),
                "completed": bool(progress and progress.completed_at),
                "completed_at": progress.completed_at if progress else 0,
                "tributes": tributes,
                "tribute_count": len(tributes),
                "completed_tribute_count": completed_count,
                "completion_reward": self._reward_snapshot(portal.completion_reward),
            })
        return portals

    def _talent_snapshot(self, player: PlayerState) -> dict:
        available_points = self._available_talent_points(player)
        nodes = []
        for node in self.content.talents:
            unlocked = node.id in player.talent_nodes
            prerequisites_met = all(entry in player.talent_nodes for entry in node.prerequisites)
            locked_reason = None
            if not unlocked and player.level < node.min_level:
                locked_reason = f"等级 {node.min_level} 解锁"
            elif not unlocked and not prerequisites_met:
                locked_reason = "需要前置天赋"
            elif not unlocked and available_points < node.cost:
                locked_reason = "天赋点不足"
            nodes.append({
                **node.model_dump(),
                "unlocked": unlocked,
                "can_unlock": not unlocked and locked_reason is None,
                "locked_reason": locked_reason,
            })
        return {
            "earned_points": max(0, player.level - 1),
            "available_points": available_points,
            "unlocked_node_ids": list(player.talent_nodes),
            "nodes": nodes,
        }

    def _consume_recipe_inputs(self, player: PlayerState, recipe) -> list[TaskInputSnapshot]:
        consumed: list[TaskInputSnapshot] = []
        for requirement in recipe.inputs:
            qualities = player.inventory.get(requirement.item_id, {})
            if sum(qualities.values()) < requirement.quantity:
                item = self.content.item_map.get(requirement.item_id)
                raise GameError("resource_insufficient", f"{item.name if item else requirement.item_id}数量不足")
            remaining = requirement.quantity
            for quality, owned in sorted(qualities.items()):
                amount = min(owned, remaining)
                if amount <= 0:
                    continue
                remove_item(player, requirement.item_id, amount, quality)
                consumed.append(TaskInputSnapshot(
                    item_id=requirement.item_id,
                    quality=quality,
                    quantity=amount,
                ))
                remaining -= amount
                if remaining == 0:
                    break
        return consumed

    def _recipe_snapshot(self, player: PlayerState, recipe) -> dict:
        condition = recipe.unlock_condition
        unlocked = evaluate_recipe_unlock(player, condition.hook, condition.params)
        inputs = []
        ingredients_available = True
        for requirement in recipe.inputs:
            item = self.content.item_map[requirement.item_id]
            owned_by_quality = player.inventory.get(requirement.item_id, {})
            owned_quantity = sum(owned_by_quality.values())
            ingredients_available = ingredients_available and owned_quantity >= requirement.quantity
            inputs.append({
                **requirement.model_dump(),
                "item": item.model_dump(),
                "owned_quantity": owned_quantity,
                "owned_by_quality": dict(sorted(owned_by_quality.items())),
            })
        return {
            **recipe.model_dump(),
            "item": self.content.item_map[recipe.produce_item_id].model_dump(),
            "inputs": inputs,
            "unlocked": unlocked,
            "unlock_description": describe_recipe_unlock(condition.hook, condition.params),
            "ingredients_available": ingredients_available,
        }

    def _normalize_inventory_quality(self, player: PlayerState) -> None:
        for item_id, qualities in list(player.inventory.items()):
            item = self.content.item_map.get(item_id)
            if item and item.has_quality and qualities.get(0, 0) > 0:
                qualities[1] = qualities.get(1, 0) + qualities.pop(0)
            for quality, quantity in list(qualities.items()):
                if quantity == 0:
                    qualities.pop(quality)
            if not qualities:
                player.inventory.pop(item_id)

    def _resolve_output(self, production_slot, now: int, fallback_content=None) -> None:
        task = production_slot.task_snapshot
        if task:
            item_id = task.produce_item_id
            yield_min = task.yield_min
            yield_max = task.yield_max
            probabilities = task.quality_parameters.probabilities
        elif fallback_content:
            item_id = fallback_content.produce_item_id
            yield_min = fallback_content.yield_min
            yield_max = fallback_content.yield_max
            probabilities = [1, 0, 0, 0, 0]
        else:
            return
        production_slot.task_result = ProductionResultSnapshot(
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
