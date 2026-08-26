from __future__ import annotations

import random
import secrets
import time
from collections.abc import Callable
from math import ceil, floor
from typing import NamedTuple

from red_leaf_town.content import GameContent, GatheringDrawDefinition, RewardDefinition
from red_leaf_town.domain import (
    CommissionBoardEntry,
    CommissionPayout,
    CommissionState,
    CraftingStationState,
    FishCodexEntry,
    GachaDropRecord,
    GachaPoolProgressState,
    GachaRequestRecord,
    GatheringSiteState,
    MailMessage,
    MailReceiptState,
    MiningSiteState,
    OwnedPartnerState,
    PendingBigCatchState,
    PlayerState,
    PondState,
    PortalProgressState,
    PortalTributeProgress,
    ProductionResultSnapshot,
    ProductionTaskSnapshot,
    QQIdentity,
    TakenCommissionRecord,
    TaskPartnerSnapshot,
    TaskInputSnapshot,
    TaskOutputSnapshot,
    TaskQualitySnapshot,
)
from red_leaf_town.domain.aquatic import (
    PondParameters,
    SlotError,
    add_fry,
    decayed_combo,
    deposit_into_slot,
    pond_cycle_seconds,
    settle_ponds,
    slot_runtime_seconds,
)
from red_leaf_town.domain.commissions import (
    commission_day,
    commission_day_end,
    commission_identifier,
    commission_seed,
    is_lucky_day,
    lucky_weekday,
)
from red_leaf_town.domain.economy import EconomyError, add_item, grant_coins, remove_item, spend_coins
from red_leaf_town.domain.progression import (
    consume_stamina,
    grant_experience,
    normalize_crafting_stations,
    normalize_gathering_sites,
    normalize_mining_sites,
    normalize_plot_slots,
    normalize_ponds,
    refund_stamina,
    settle_stamina,
)
from red_leaf_town.domain.production import build_results, draw_count, pick_weighted
from red_leaf_town.domain.quality import QUALITY_NAMES, quality_probabilities, roll_quality
from red_leaf_town.gacha_pools import GachaDefinition, load_gacha_pools
from red_leaf_town.recipe_unlocks import describe_recipe_unlock, evaluate_recipe_unlock
from red_leaf_town.partner_content import (
    GROWTH_CURVE_NAMES,
    INDUSTRY_NAMES,
    PartnerCatalog,
    PartnerDefinition,
    level_cap_for_breakthrough,
    load_partner_catalog,
)
from red_leaf_town.partner_traits import partner_trait_catalog
from red_leaf_town.rewards import serialize_reward, validate_reward_references
from red_leaf_town.story_assets import StoryAssetCatalog, load_story_asset_catalog
from red_leaf_town.story_content import StoryCatalog, load_story_catalog, serialize_script
from red_leaf_town.story_triggers import StoryContext, validate_story_cue

from .ports import CommissionBoardRepository, MailRepository, PlayerRepository


MAIL_LIST_LIMIT = 60
# 钓鱼是高频接口且已知有脚本调用，限一个最小间隔，避免重试造成重复发放。
FISHING_MIN_INTERVAL_SECONDS = 1
FISHING_MAX_DRAWS = 40
_UNSEEN = MailReceiptState(mail_id="placeholder")


class FishingBatch(NamedTuple):
    """一次抽取的结果。size 是这一批里最大的那条鱼的体型，0 表示这一项不记体型。"""

    item_id: str
    quantity: int
    codex: bool
    size: float


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
        commission_board: CommissionBoardRepository | None = None,
        mailbox: MailRepository | None = None,
        clock: Callable[[], float] = time.time,
        rng: random.Random | random.SystemRandom | None = None,
        partner_catalog_loader: Callable[[], PartnerCatalog] = load_partner_catalog,
        story_catalog_loader: Callable[[], StoryCatalog] = load_story_catalog,
        story_asset_loader: Callable[[], StoryAssetCatalog] = load_story_asset_catalog,
        gacha_pool_loader: Callable[[], dict[str, GachaDefinition]] = load_gacha_pools,
    ):
        self.content = content
        self.repository = repository
        # 转发池是唯一的跨玩家状态。不接的话委托照常刷新和提交，只是转发功能不开放。
        self.commission_board = commission_board
        # 信箱同样是玩家存档之外的共享存储。不接就当作小镇还没通邮，收件箱恒为空。
        self.mailbox_repository = mailbox
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.partner_catalog_loader = partner_catalog_loader
        self.story_catalog_loader = story_catalog_loader
        self.story_asset_loader = story_asset_loader
        self.gacha_pool_loader = gacha_pool_loader

    def _gacha_pool(self, pool_id: str) -> GachaDefinition:
        pool = self.gacha_pool_loader().get(pool_id)
        if pool is None:
            raise GameError("gacha_pool_not_found", "招募池不存在", 404)
        return pool

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

    def plant(self, oauth_sub: str, slot: int, crop_id: str, task_item_id: str = "") -> dict:
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
            task_snapshot = self._build_farming_task_snapshot(player, plot, crop, now, task_item_id)
            try:
                remove_item(player, crop.seed_item_id, 1)
                consume_stamina(player, crop.stamina_cost, self.content, now)
            except (EconomyError, ValueError) as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            plot.crop_id = crop.id
            plot.planted_at = now
            plot.ready_at = task_snapshot.ready_at
            plot.task_snapshot = task_snapshot
            plot.task_results = []
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
            results = plot.task_results
            if not results:
                raise GameError("task_content_missing", "进行中的作物配置缺失，请联系管理员", 409)
            task = plot.task_snapshot
            crop = self.content.crop_map.get(plot.crop_id)
            harvest_xp = task.harvest_xp if task else crop.harvest_xp if crop else 0
            for result in results:
                add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, harvest_xp, self.content)
            partner_experience = self._grant_task_partner_experience(player, task)
            plot.crop_id = ""
            plot.planted_at = 0
            plot.ready_at = 0
            plot.task_snapshot = None
            plot.task_results = []
            return {
                "slot": slot,
                "item_id": results[0].item_id,
                "quantity": sum(result.quantity for result in results),
                "drops": [self._result_snapshot(result) for result in results],
                "experience": harvest_xp,
                "levels": levels,
                "partner_experience": partner_experience,
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
            if (
                site.task_snapshot is not None
                and site.task_snapshot.ready_at > now
                and not self._task_releases_partner(site.task_snapshot)
            ):
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

    def start_gathering(self, oauth_sub: str, site_id: str, task_id: str, task_item_id: str = "") -> dict:
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
            headline_output = task.headline_output
            snapshot = self._build_production_task_snapshot(
                player=player,
                assigned_partner_ids=site.assigned_partner_ids,
                industry="gathering",
                content_id=task.id,
                production_slot_id=f"gathering:site:{site.site_id}",
                now=now,
                base_duration=task.duration_seconds,
                minimum_duration=task.minimum_duration_seconds,
                time_difficulty=task.time_difficulty,
                produce_item_id=headline_output.item_id,
                yield_min=headline_output.quantity_min,
                yield_max=headline_output.quantity_max,
                harvest_xp=task.collect_xp,
                stamina_cost=task.stamina_cost,
                quality=task.quality,
                output_pool=[TaskOutputSnapshot.model_validate(output.model_dump()) for output in task.outputs],
                draws=task.draws,
                task_item_id=task_item_id,
            )
            try:
                consume_stamina(player, task.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            site.task_snapshot = snapshot
            site.task_results = []
            return {
                "site_id": site_id,
                "task_id": task_id,
                "ready_at": snapshot.ready_at,
                "base_duration": snapshot.base_duration,
                "final_duration": snapshot.final_duration,
                "total_ability": snapshot.total_ability,
                "quality_ability": snapshot.quality_parameters.ability,
                "draw_count": snapshot.draw_count,
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
            results = site.task_results
            if not results:
                raise GameError("task_content_missing", "采集任务配置缺失，请联系管理员", 409)
            harvest_xp = site.task_snapshot.harvest_xp
            for result in results:
                add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, harvest_xp, self.content)
            partner_experience = self._grant_task_partner_experience(player, site.task_snapshot)
            site.task_snapshot = None
            site.task_results = []
            return {
                "site_id": site_id,
                "drops": [self._result_snapshot(result) for result in results],
                "experience": harvest_xp,
                "levels": levels,
                "partner_experience": partner_experience,
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
            if (
                station.task_snapshot is not None
                and station.task_snapshot.ready_at > now
                and not self._task_releases_partner(station.task_snapshot)
            ):
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

    def start_crafting(self, oauth_sub: str, station_id: str, recipe_id: str, task_item_id: str = "") -> dict:
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
                stamina_cost=recipe.stamina_cost,
                quality=recipe.quality,
                consumed_inputs=consumed_inputs,
                task_item_id=task_item_id,
            )
            try:
                consume_stamina(player, recipe.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            station.task_snapshot = snapshot
            station.task_results = []
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
            results = station.task_results
            if not results:
                raise GameError("task_content_missing", "加工任务配置缺失，请联系管理员", 409)
            collect_xp = station.task_snapshot.harvest_xp
            for result in results:
                add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, collect_xp, self.content)
            partner_experience = self._grant_task_partner_experience(player, station.task_snapshot)
            station.task_snapshot = None
            station.task_results = []
            return {
                "station_id": station_id,
                "item_id": results[0].item_id,
                "quantity": sum(result.quantity for result in results),
                "drops": [self._result_snapshot(result) for result in results],
                "experience": collect_xp,
                "levels": levels,
                "partner_experience": partner_experience,
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
            if (
                site.task_snapshot is not None
                and site.task_snapshot.ready_at > now
                and not self._task_releases_partner(site.task_snapshot)
            ):
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

    def start_mining(self, oauth_sub: str, site_id: str, task_id: str, task_item_id: str = "") -> dict:
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
            total_ability = self._production_ability(player, site.assigned_partner_ids, "mining")[0]
            yield_efficiency = 1 + task.yield_bonus * total_ability / (total_ability + task.yield_difficulty)
            snapshot = self._build_production_task_snapshot(
                player=player,
                assigned_partner_ids=site.assigned_partner_ids,
                industry="mining",
                content_id=task.id,
                production_slot_id=f"mining:site:{site.site_id}",
                now=now,
                base_duration=task.duration_seconds,
                time_difficulty=None,
                produce_item_id=task.produce_item_id,
                yield_min=task.yield_min,
                yield_max=task.yield_max,
                harvest_xp=task.collect_xp,
                stamina_cost=task.stamina_cost,
                quality=task.quality,
                fixed_duration=True,
                yield_efficiency=yield_efficiency,
                task_item_id=task_item_id,
            )
            try:
                consume_stamina(player, task.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            site.task_snapshot = snapshot
            site.task_results = []
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
            results = site.task_results
            if not results:
                raise GameError("task_content_missing", "采矿任务配置缺失，请联系管理员", 409)
            collect_xp = site.task_snapshot.harvest_xp
            for result in results:
                add_item(player, result.item_id, result.quantity, result.quality)
            levels = grant_experience(player, collect_xp, self.content)
            partner_experience = self._grant_task_partner_experience(player, site.task_snapshot)
            site.task_snapshot = None
            site.task_results = []
            return {
                "site_id": site_id,
                "item_id": results[0].item_id,
                "quantity": sum(result.quantity for result in results),
                "drops": [self._result_snapshot(result) for result in results],
                "experience": collect_xp,
                "levels": levels,
                "partner_experience": partner_experience,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    # ------------------------------------------------------------------ 水产

    def assign_fishing_companion(self, oauth_sub: str, partner_id: str = "") -> dict:
        """陪钓伙伴。钓鱼是瞬时的，不写锁定引用，玩家随时可换。"""
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if player.fishing.companion_partner_id == partner_id:
                return {"partner_id": partner_id or None, "changed": False}
            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                definition = catalog.partner_map.get(partner_id)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "aquatic" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有水产倾向", 409)
                if self._partner_lock_deadlines(player, now).get(partner_id, 0) > now:
                    raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能陪钓", 409)
                # 跨产业唯一派驻：驻场在鱼塘或别的生产格的伙伴不能同时陪钓。
                self._clear_partner_assignment(player, partner_id)
            player.fishing.companion_partner_id = partner_id
            return {"partner_id": partner_id or None, "changed": True}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def cast_line(self, oauth_sub: str, spot_id: str, request_id: str = "") -> dict:
        """抛一竿。扣体力、掷结果、入库在同一次原子更新里完成，重复的 request_id 不再发放。"""
        spot = self.content.fishing_spot_map.get(spot_id)
        if spot is None:
            raise GameError("fishing_spot_not_found", "这个钓点不存在", 404)
        combo_rules = self.content.fishing_combo
        request_id = str(request_id or "").strip()[:64]
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if player.level < spot.min_level:
                raise GameError("content_locked", f"达到 {spot.min_level} 级后解锁")
            fishing = player.fishing
            if request_id and request_id in fishing.recent_request_ids:
                return {"spot_id": spot_id, "duplicate": True, "drops": [], "experience": 0}
            if fishing.pending_big_catch is not None:
                raise GameError("big_catch_pending", "线还绷着，先处理咬钩的大物")
            if now - fishing.last_cast_at < FISHING_MIN_INTERVAL_SECONDS and fishing.last_cast_at:
                raise GameError("fishing_too_fast", "刚抛完一竿，缓一口气", 429)

            combo = self._current_combo(player, spot_id, now)
            ability = self._aquatic_ability(player, self._fishing_companion_ids(player))
            draws = self._fishing_draw_count(spot, ability, combo)
            pool = self._fishing_pool(spot, combo)
            try:
                consume_stamina(player, spot.stamina_cost, self.content, now)
            except ValueError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc

            probabilities = quality_probabilities(
                ability,
                spot.quality.thresholds,
                spot.quality.width,
                spot.quality.miracle_probability_cap,
                spot.quality.miracle_eligible,
            )
            batches: list[FishingBatch] = []
            hooked = False
            for _ in range(draws):
                entry, big_catch = self._pick_fishing_entry(pool)
                if big_catch and not hooked:
                    hooked = True
                    continue
                if big_catch:
                    # 一竿只处理一条大物，多抽到的按退回的普通鱼算。
                    fallback = self._fishing_output(spot, spot.big_catch.fallback_item_id)
                    batches.append(self._roll_batch(fallback, 1) if fallback else FishingBatch(spot.big_catch.fallback_item_id, 1, True, 0))
                    continue
                quantity = self.rng.randint(entry.quantity_min, entry.quantity_max)
                batches.append(self._roll_batch(entry, quantity))
            drops = self._grant_fishing_batches(player, batches, probabilities, now)
            codex = self._record_codex(player, batches, now)

            levels = grant_experience(player, spot.cast_xp, self.content)
            milestones = self._claim_codex_milestones(player, now)
            partner_experience = self._grant_companion_experience(player, spot.stamina_cost)
            fishing.spot_id = spot_id
            fishing.combo = min(self._combo_cap(player), combo + 1)
            fishing.combo_updated_at = now
            fishing.last_cast_at = now
            if request_id:
                fishing.recent_request_ids = [*fishing.recent_request_ids, request_id][-8:]
            if hooked:
                fishing.pending_big_catch = PendingBigCatchState(spot_id=spot_id, created_at=now)
            return {
                "spot_id": spot_id,
                "duplicate": False,
                "stamina_cost": spot.stamina_cost,
                "draws": draws,
                "ability": ability,
                "combo": fishing.combo,
                "drops": drops,
                "experience": spot.cast_xp,
                "levels": levels,
                "codex_discoveries": codex,
                "codex_milestones": milestones,
                "partner_experience": partner_experience,
                "big_catch": self._big_catch_snapshot(player, now),
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def resolve_big_catch(self, oauth_sub: str, action: str) -> dict:
        """搏鱼：追加体力搏一把，或者直接放弃拿回一条普通鱼。这是演出和图鉴触发，不是决策点。"""
        action = str(action or "").strip()
        if action not in ("fight", "release"):
            raise GameError("invalid_action", "只能选择搏一把或者放弃")
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            pending = player.fishing.pending_big_catch
            if pending is None:
                raise GameError("big_catch_missing", "现在没有咬钩的大物", 404)
            spot = self.content.fishing_spot_map.get(pending.spot_id)
            if spot is None or spot.big_catch is None:
                player.fishing.pending_big_catch = None
                raise GameError("fishing_spot_not_found", "这个钓点的配置已经不存在", 409)
            big_catch = spot.big_catch
            ability = self._aquatic_ability(player, self._fishing_companion_ids(player))
            probabilities = quality_probabilities(
                ability,
                spot.quality.thresholds,
                spot.quality.width,
                spot.quality.miracle_probability_cap,
                spot.quality.miracle_eligible,
            )
            chance = big_catch.success_chance(ability)
            spent = 0
            success = False
            if action == "fight":
                try:
                    consume_stamina(player, big_catch.stamina_cost, self.content, now)
                except ValueError as exc:
                    raise GameError("resource_insufficient", str(exc)) from exc
                spent = big_catch.stamina_cost
                success = self.rng.random() < chance
            player.fishing.pending_big_catch = None
            partner_experience = self._grant_companion_experience(player, spent)
            if not success:
                quality = roll_quality(self.rng, probabilities)
                fallback = self._fishing_output(spot, big_catch.fallback_item_id)
                fallback_size = self._roll_size(fallback)
                add_item(player, big_catch.fallback_item_id, 1, quality)
                self._record_codex_entry(player, big_catch.fallback_item_id, now, size=fallback_size)
                return {
                    "action": action,
                    "success": False,
                    "chance": chance,
                    "stamina_cost": spent,
                    "drops": [self._fishing_drop(big_catch.fallback_item_id, 1, quality, fallback_size)],
                    "codex_milestones": self._claim_codex_milestones(player, now),
                    "partner_experience": partner_experience,
                }
            quality = max(big_catch.min_quality, roll_quality(self.rng, probabilities))
            size = round(big_catch.size_min + self.rng.random() * (big_catch.size_max - big_catch.size_min), 1)
            add_item(player, big_catch.item_id, 1, quality)
            self._record_codex_entry(player, big_catch.item_id, now, size=size)
            return {
                "action": action,
                "success": True,
                "chance": chance,
                "stamina_cost": spent,
                "size": size,
                "drops": [self._fishing_drop(big_catch.item_id, 1, quality, size)],
                "codex_milestones": self._claim_codex_milestones(player, now),
                "partner_experience": partner_experience,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def assign_pond_partner(self, oauth_sub: str, pond_id: str, partner_id: str = "") -> dict:
        """资产格的伙伴驻场即占编制，但随时可以撤下 —— 因为没有需要保持完整性的进行中任务。"""
        partner_id = str(partner_id or "").strip()
        now = self._now()
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            self._settle(player, now)
            pond = self._pond(player, pond_id)
            desired_ids = [partner_id] if partner_id else []
            if pond.assigned_partner_ids == desired_ids:
                return {"pond_id": pond_id, "partner_id": partner_id or None, "changed": False}
            if partner_id:
                owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
                definition = catalog.partner_map.get(partner_id)
                if owned is None:
                    raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
                if definition is None:
                    raise GameError("partner_not_found", "伙伴配置不存在", 404)
                if not any(tendency.industry == "aquatic" for tendency in definition.tendencies):
                    raise GameError("partner_tendency_mismatch", "这个伙伴没有水产倾向", 409)
                if self._partner_lock_deadlines(player, now).get(partner_id, 0) > now:
                    raise GameError("partner_locked", "伙伴正在参与进行中的任务，暂时不能移动", 409)
                self._clear_partner_assignment(player, partner_id)
                if player.fishing.companion_partner_id == partner_id:
                    player.fishing.companion_partner_id = ""
            pond.assigned_partner_ids = desired_ids
            if self._industry_assigned_count(player, "aquatic") > self._industry_partner_capacity(player, "aquatic"):
                raise GameError("partner_capacity_reached", "当前水产伙伴编制已满", 409)
            # 结算已经在前面用旧能力做完，这里直接写入新的参数快照。
            pond.ability = self._aquatic_ability(player, pond.assigned_partner_ids)
            pond.cycle_seconds = self._pond_cycle_seconds(player, pond)
            return {
                "pond_id": pond_id,
                "partner_id": partner_id or None,
                "changed": True,
                "ability": pond.ability,
                "cycle_seconds": pond.cycle_seconds,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def build_pond(self, oauth_sub: str, pond_id: str) -> dict:
        """挖塘。鱼塘是一次性投入的资产，到等级只是解锁资格，还要付红叶币才动土。"""
        pond_id = str(pond_id or "").strip()
        definition = self.content.pond_map.get(pond_id)
        if definition is None:
            raise GameError("pond_not_found", "没有这口鱼塘", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            if any(pond.pond_id == pond_id for pond in player.ponds):
                raise GameError("pond_exists", "这口塘已经挖好了", 409)
            if player.level < definition.min_level:
                raise GameError("content_locked", f"达到 {definition.min_level} 级之后才能挖这口塘")
            if player.coins < definition.build_cost:
                raise GameError("resource_insufficient", f"挖塘需要 {definition.build_cost} 红叶币")
            player.coins -= definition.build_cost
            player.ponds.append(PondState(pond_id=pond_id, last_settled_at=now))
            normalize_ponds(player, self.content)
            return {
                "pond_id": pond_id,
                "name": definition.name,
                "build_cost": definition.build_cost,
                "coins": player.coins,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def stock_pond(self, oauth_sub: str, pond_id: str, species_id: str, quantity: int) -> dict:
        """投苗。空塘投苗即开塘，已有鱼群只能继续投同一个品种。"""
        quantity = int(quantity)
        if quantity < 1 or quantity > 999:
            raise GameError("invalid_quantity", "投苗数量需在 1 到 999 之间")
        species = self.content.pond_species_map.get(species_id)
        if species is None:
            raise GameError("pond_species_not_found", "这个鱼苗品种不存在", 404)
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            pond = self._pond(player, pond_id)
            if player.level < species.min_level:
                raise GameError("content_locked", f"达到 {species.min_level} 级后可以养这个品种")
            if pond.species_id and pond.species_id != species.id:
                raise GameError("pond_species_mismatch", "塘里已经养着别的鱼，先捞光再换品种", 409)
            capacity = self._pond_capacity(pond)
            if pond.population + quantity > capacity:
                raise GameError("pond_capacity_reached", f"这口塘最多容纳 {capacity} 尾（鱼苗也占位置）")
            try:
                remove_item(player, species.fry_item_id, quantity, 0)
            except EconomyError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            was_empty = pond.empty
            pond.species_id = species.id
            if was_empty:
                pond.settle_remainder = 0
                pond.growth_remainder = 0
            pond.last_settled_at = now
            pond.ability = self._aquatic_ability(player, pond.assigned_partner_ids)
            pond.cycle_seconds = self._pond_cycle_seconds(player, pond)
            # 投苗之后才知道周期，所以入池放在最后：这一批要长满 maturation_cycles 个周期。
            add_fry(pond, quantity, species.maturation_cycles)
            return {
                "pond_id": pond_id,
                "species_id": species.id,
                "quantity": quantity,
                "stock": pond.stock,
                "fry": pond.fry_total,
                "capacity": capacity,
                "cycle_seconds": pond.cycle_seconds,
                "maturation_seconds": int(species.maturation_cycles * pond.cycle_seconds),
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def harvest_pond(self, oauth_sub: str, pond_id: str, quantity: int) -> dict:
        """捞鱼。不消耗体力：鱼塘的成本在鱼苗和饲料槽上，它属于资产轴。"""
        quantity = int(quantity)
        if quantity < 1:
            raise GameError("invalid_quantity", "捞鱼数量必须为正数")
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            pond = self._pond(player, pond_id)
            species = self.content.pond_species_map.get(pond.species_id)
            if species is None or pond.stock <= 0:
                raise GameError("pond_empty", "这口塘里还没有能捞的成鱼")
            if quantity > pond.stock:
                raise GameError("invalid_quantity", f"塘里只有 {pond.stock} 尾成鱼，鱼苗还没长成")
            ability = self._aquatic_ability(player, pond.assigned_partner_ids)
            quality_ability = (
                ability
                + self._pond_tier(pond).quality_bonus
                + player.feed_slot.quality_score
                + pond.generation_score
            )
            probabilities = quality_probabilities(
                quality_ability,
                species.quality.thresholds,
                species.quality.width,
                species.quality.miracle_probability_cap,
                species.quality.miracle_eligible,
            )
            qualities = [roll_quality(self.rng, probabilities) for _ in range(quantity)]
            floor_quality = int(self._talent_modifier(player, "pond_harvest_quality_floor"))
            if floor_quality:
                best = max(range(len(qualities)), key=lambda index: qualities[index])
                qualities[best] = max(qualities[best], min(5, floor_quality))
            tally: dict[int, int] = {}
            for quality in qualities:
                tally[quality] = tally.get(quality, 0) + 1
            for quality, amount in tally.items():
                add_item(player, species.produce_item_id, amount, quality)
            pond.stock -= quantity
            generation_before = pond.generation_score
            if pond.empty:
                # 竭泽而渔：连鱼苗都不剩，塘退回空塘状态，世代加值清零。
                pond.generation_score = 0
                pond.growth_remainder = 0
                pond.settle_remainder = 0
                pond.species_id = ""
                pond.stalled = False
            # 捞到门槛以下不在这里扣分：鱼群不稳定，世代加值会在之后的每个周期里自己回落。
            pond.last_settled_at = now
            return {
                "pond_id": pond_id,
                "species_id": species.id,
                "quantity": quantity,
                "stock": pond.stock,
                "fry": pond.fry_total,
                "steady_stock": self._pond_parameters(player, pond).steady_stock,
                "quality_ability": round(quality_ability, 2),
                "generation_before": round(generation_before, 2),
                "generation_score": round(pond.generation_score, 2),
                "drops": [
                    self._fishing_drop(species.produce_item_id, amount, quality)
                    for quality, amount in sorted(tally.items())
                ],
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def deposit_feed(self, oauth_sub: str, item_id: str, quality: int, count: int) -> dict:
        """向饲料槽投料。投料之前必须先结算，否则新料的品质会被追溯到已经过去的那段时间。"""
        item_id = str(item_id or "").strip()
        quality = int(quality or 0)
        count = int(count)
        if count < 1 or count > 999:
            raise GameError("invalid_quantity", "投料数量需在 1 到 999 之间")
        definition = self.content.item_map.get(item_id)
        if definition is None:
            raise GameError("item_not_found", "物品不存在", 404)
        if definition.feed is None:
            raise GameError("item_not_feedable", "这个东西不能当饲料")
        slot_rules = self._feed_slot_rules()
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            try:
                remove_item(player, item_id, count, quality)
            except EconomyError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            add_units = definition.feed.units * count
            unit_score = definition.feed.score * slot_rules.multiplier(quality)
            try:
                deposit_into_slot(player.feed_slot, add_units, unit_score, slot_rules.capacity)
            except SlotError as exc:
                raise GameError("feed_slot_full", str(exc)) from exc
            return {
                "item_id": item_id,
                "quality": quality or None,
                "count": count,
                "added_units": add_units,
                "unit_score": round(unit_score, 2),
                "units": round(player.feed_slot.units, 2),
                "quality_score": round(player.feed_slot.quality_score, 2),
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def dump_feed(self, oauth_sub: str) -> dict:
        """倾倒饲料槽。无返还 —— 它是被稀释之后的逃生口。"""
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            dumped = round(player.feed_slot.units, 2)
            player.feed_slot.units = 0
            player.feed_slot.quality_score = 0
            player.feed_slot.updated_at = now
            return {"dumped_units": dumped}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    # ------------------------------------------------------- 水产：内部实现

    def _pond(self, player: PlayerState, pond_id: str) -> PondState:
        pond = next((entry for entry in player.ponds if entry.pond_id == pond_id), None)
        if pond is None:
            raise GameError("pond_locked", "这口鱼塘尚未开放", 404)
        return pond

    def _feed_slot_rules(self):
        rules = self.content.feed_slot
        if rules is None:
            raise GameError("feed_slot_missing", "饲料槽配置缺失，请联系管理员", 409)
        return rules

    def _pond_definition(self, pond: PondState):
        return self.content.pond_map.get(pond.pond_id)

    def _pond_tier(self, pond: PondState):
        definition = self._pond_definition(pond)
        tier = self.content.pond_tier_map.get(definition.tier if definition else 1)
        if tier is None:
            raise GameError("pond_tier_missing", "鱼塘等级配置缺失，请联系管理员", 409)
        return tier

    def _pond_capacity(self, pond: PondState) -> int:
        return self._pond_tier(pond).capacity

    def _aquatic_ability(self, player: PlayerState, partner_ids: list[str]) -> int:
        """驻场伙伴数据异常时退回主角能力，避免一条坏引用把整个存档卡住。"""
        try:
            total, _, _ = self._production_ability(player, list(partner_ids), "aquatic")
        except GameError:
            rules = self.content.industries["aquatic"]
            return rules.character_base_ability + self._industry_ability_bonus(player, "aquatic")
        return total

    def _pond_cycle_seconds(self, player: PlayerState, pond: PondState) -> int:
        species = self.content.pond_species_map.get(pond.species_id)
        if species is None:
            return 0
        return pond_cycle_seconds(
            species.base_cycle_seconds,
            self._aquatic_ability(player, pond.assigned_partner_ids),
            species.time_difficulty,
        )

    def _pond_parameters(self, player: PlayerState, pond: PondState) -> PondParameters:
        tier = self._pond_tier(pond)
        species = self.content.pond_species_map.get(pond.species_id)
        generation_cap = (species.generation_cap if species else 0) + self._talent_modifier(player, "pond_generation_cap")
        return PondParameters(
            # 用存档里的周期快照推进这一段，没有快照（老存档、刚开塘）才现算。
            cycle_seconds=pond.cycle_seconds or self._pond_cycle_seconds(player, pond),
            capacity=tier.capacity,
            growth_rate=species.growth_rate if species else 0,
            maturation_cycles=species.maturation_cycles if species else 1,
            steady_ratio=species.steady_ratio if species else 1,
            generation_gain=species.generation_gain if species else 0,
            generation_decay=species.generation_decay if species else 0,
            generation_cap=generation_cap,
            feed_per_cycle=tier.feed_per_cycle,
        )

    def _settle_aquatic(self, player: PlayerState, now: int) -> None:
        if not player.ponds:
            player.feed_slot.updated_at = now
            return
        parameters = {}
        for pond in player.ponds:
            if pond.last_settled_at <= 0 or pond.last_settled_at > now:
                pond.last_settled_at = now
            parameters[pond.pond_id] = self._pond_parameters(player, pond)
        settlement = settle_ponds(player.ponds, player.feed_slot, parameters, now)
        self._grant_pond_partner_experience(player, settlement)
        for pond in player.ponds:
            # 推进用旧快照，推进完立刻换成当前参数：天赋和伙伴的改动从下一段开始生效。
            pond.ability = self._aquatic_ability(player, pond.assigned_partner_ids)
            pond.cycle_seconds = self._pond_cycle_seconds(player, pond)

    def _grant_pond_partner_experience(self, player: PlayerState, settlement) -> None:
        """驻场看塘的伙伴按结算掉的周期数拿经验。停摆的周期没买单，也就不给经验。"""
        per_cycle = self.content.partner_growth.pond_experience_per_cycle
        if not per_cycle:
            return
        owned_map = {entry.partner_id: entry for entry in player.owned_partners}
        for pond in player.ponds:
            advance = settlement.ponds.get(pond.pond_id)
            if advance is None or advance.paid_cycles <= 0:
                continue
            for partner_id in pond.assigned_partner_ids:
                owned = owned_map.get(partner_id)
                if owned is not None:
                    self._grant_partner_experience(owned, advance.paid_cycles * per_cycle)

    def _talent_modifier(self, player: PlayerState, key: str) -> float:
        return sum(
            node.modifiers.get(key, 0)
            for node_id in player.talent_nodes
            if (node := self.content.talent_map.get(node_id)) is not None
        )

    def _combo_cap(self, player: PlayerState) -> int:
        return int(self.content.fishing_combo.max_layers + self._talent_modifier(player, "fishing_combo_cap"))

    def _current_combo(self, player: PlayerState, spot_id: str, now: int) -> int:
        """换钓点立即清零，久不抛竿逐层衰减。"""
        fishing = player.fishing
        if fishing.spot_id != spot_id:
            return 0
        rules = self.content.fishing_combo
        combo = decayed_combo(
            fishing.combo,
            fishing.combo_updated_at,
            now,
            rules.idle_grace_seconds,
            rules.decay_seconds,
        )
        return min(combo, self._combo_cap(player))

    def _fishing_companion_ids(self, player: PlayerState) -> list[str]:
        return [player.fishing.companion_partner_id] if player.fishing.companion_partner_id else []

    def _fishing_draw_count(self, spot, ability: int, combo: int) -> int:
        rules = self.content.fishing_combo
        base = spot.draws.base_draws + combo * rules.draw_bonus_per_layer
        multiplier = 1 + spot.draws.ability_bonus * max(0, ability) / (max(0, ability) + spot.draws.difficulty)
        return max(1, min(FISHING_MAX_DRAWS, floor(base * multiplier + 0.5)))

    def _fishing_pool(self, spot, combo: int) -> list[tuple[object, float, bool]]:
        """产出池。稀有条目和大物吃聚鱼度的权重加成。"""
        rare_multiplier = 1 + self.content.fishing_combo.rare_weight_per_layer * combo
        pool: list[tuple[object, float, bool]] = [
            (entry, entry.weight * (rare_multiplier if entry.rare else 1), False)
            for entry in spot.outputs
        ]
        if spot.big_catch is not None:
            pool.append((spot.big_catch, spot.big_catch.weight * rare_multiplier, True))
        return pool

    def _pick_fishing_entry(self, pool: list[tuple[object, float, bool]]):
        total = sum(weight for _, weight, _ in pool)
        draw = self.rng.random() * total
        cumulative = 0.0
        for entry, weight, big_catch in pool:
            cumulative += weight
            if draw < cumulative:
                return entry, big_catch
        return pool[-1][0], pool[-1][2]

    def _fishing_output(self, spot, item_id: str):
        return next((entry for entry in spot.outputs if entry.item_id == item_id), None)

    def _roll_size(self, entry) -> float:
        """鱼有体型，杂物没有。返回 0 表示这一项不记体型。"""
        if entry is None or not entry.has_size:
            return 0.0
        return round(entry.size_min + self.rng.random() * (entry.size_max - entry.size_min), 1)

    def _roll_batch(self, entry, quantity: int) -> FishingBatch:
        """一批里每条鱼各摇一个体型，图鉴只记最大的那条。"""
        size = max((self._roll_size(entry) for _ in range(max(1, quantity))), default=0.0)
        return FishingBatch(entry.item_id, quantity, entry.codex, size)

    def _grant_fishing_batches(
        self,
        player: PlayerState,
        batches: list[FishingBatch],
        probabilities: list[float],
        now: int,
    ) -> list[dict]:
        """每件独立判品质。无品质的杂物（鱼苗之类）按 0 档直接进背包。"""
        items = self.content.item_map
        tally: dict[tuple[str, int], int] = {}
        order: list[tuple[str, int]] = []
        sizes: dict[str, float] = {}
        for batch in batches:
            definition = items.get(batch.item_id)
            if batch.size:
                sizes[batch.item_id] = max(sizes.get(batch.item_id, 0.0), batch.size)
            for _ in range(batch.quantity):
                quality = roll_quality(self.rng, probabilities) if definition and definition.has_quality else 0
                key = (batch.item_id, quality)
                if key not in tally:
                    order.append(key)
                tally[key] = tally.get(key, 0) + 1
        drops = []
        for key in order:
            item_id, quality = key
            add_item(player, item_id, tally[key], quality)
            drops.append(self._fishing_drop(item_id, tally[key], quality, sizes.get(item_id, 0.0)))
        return drops

    def _fishing_drop(self, item_id: str, quantity: int, quality: int, size: float = 0.0) -> dict:
        item = self.content.item_map.get(item_id)
        return {
            "item_id": item_id,
            "name": item.name if item else item_id,
            "icon": item.icon if item else "package",
            "quantity": quantity,
            "quality": quality or None,
            "quality_name": QUALITY_NAMES.get(quality),
            "size": size or None,
            "item": item.model_dump() if item else None,
        }

    def _grant_companion_experience(self, player: PlayerState, stamina_cost: int) -> list[dict]:
        """陪钓伙伴按体力拿经验，口径与其他产业的体力分量一致；没带伙伴就没有这一项。"""
        companion_id = player.fishing.companion_partner_id
        if not companion_id or stamina_cost <= 0:
            return []
        owned = next(
            (entry for entry in player.owned_partners if entry.partner_id == companion_id),
            None,
        )
        if owned is None:
            return []
        amount = stamina_cost * self.content.partner_growth.experience_per_stamina
        return [{"partner_id": owned.partner_id, **self._grant_partner_experience(owned, amount)}]

    def _record_codex(self, player: PlayerState, batches: list[FishingBatch], now: int) -> list[dict]:
        discoveries = []
        for item_id, quantity, codex, size in batches:
            if not codex or quantity <= 0:
                continue
            if self._record_codex_entry(player, item_id, now, quantity=quantity, size=size):
                item = self.content.item_map.get(item_id)
                discoveries.append({"item_id": item_id, "name": item.name if item else item_id})
        return discoveries

    def _record_codex_entry(
        self,
        player: PlayerState,
        item_id: str,
        now: int,
        quantity: int = 1,
        size: float = 0,
    ) -> bool:
        """返回是否是首次记录。大物额外记录尺寸。"""
        entry = player.fish_codex.entry(item_id)
        if entry is None:
            player.fish_codex.entries.append(FishCodexEntry(
                item_id=item_id,
                caught=quantity,
                first_caught_at=now,
                max_size=size,
            ))
            return True
        entry.caught += quantity
        entry.max_size = max(entry.max_size, size)
        return False

    def _claim_codex_milestones(self, player: PlayerState, now: int) -> list[dict]:
        species_count = len(player.fish_codex.entries)
        granted = []
        for milestone in self.content.fish_codex_milestones:
            if milestone.id in player.fish_codex.claimed_milestones:
                continue
            if species_count < milestone.required:
                continue
            player.fish_codex.claimed_milestones.append(milestone.id)
            granted.append({
                "id": milestone.id,
                "name": milestone.name,
                "required": milestone.required,
                "granted": self._grant_reward(player, milestone.reward, now),
            })
        return granted

    def _big_catch_snapshot(self, player: PlayerState, now: int) -> dict | None:
        pending = player.fishing.pending_big_catch
        if pending is None:
            return None
        spot = self.content.fishing_spot_map.get(pending.spot_id)
        if spot is None or spot.big_catch is None:
            return None
        ability = self._aquatic_ability(player, self._fishing_companion_ids(player))
        item = self.content.item_map.get(spot.big_catch.item_id)
        return {
            "spot_id": pending.spot_id,
            "spot_name": spot.name,
            "created_at": pending.created_at,
            "item_id": spot.big_catch.item_id,
            "name": item.name if item else spot.big_catch.item_id,
            "stamina_cost": spot.big_catch.stamina_cost,
            "chance": round(spot.big_catch.success_chance(ability), 3),
            "min_quality": spot.big_catch.min_quality,
        }

    def _aquatic_snapshot(self, player: PlayerState, now: int, partner_map: dict[str, dict]) -> dict:
        items = self.content.item_map
        slot_rules = self.content.feed_slot
        ability = self._aquatic_ability(player, self._fishing_companion_ids(player))
        spots = []
        for spot in self.content.fishing_spots:
            unlocked = player.level >= spot.min_level
            combo = self._current_combo(player, spot.id, now) if unlocked else 0
            # 产出表和大物都不下发：钓点该保留神秘感，见过什么去图鉴里看。
            spots.append({
                **spot.model_dump(exclude={"outputs", "big_catch", "quality"}),
                "unlocked": unlocked,
                "combo": combo,
                "draws": {
                    **spot.draws.model_dump(),
                    "expected": self._fishing_draw_count(spot, ability, combo) if unlocked else 0,
                },
            })
        # 饲料按周期扣，但"还能撑多久"要按小时说人话，所以折算成每小时的份数。
        hourly_rate = round(sum(
            self._pond_parameters(player, pond).feed_per_cycle * 3600 / pond.cycle_seconds
            for pond in player.ponds
            if not pond.empty and pond.cycle_seconds > 0
        ), 2)
        ponds = []
        for pond in player.ponds:
            definition = self._pond_definition(pond)
            species = self.content.pond_species_map.get(pond.species_id)
            parameters = self._pond_parameters(player, pond)
            assigned_partners = [
                partner_map[partner_id]
                for partner_id in pond.assigned_partner_ids
                if partner_id in partner_map
            ]
            ponds.append({
                **pond.model_dump(),
                "definition": definition.model_dump() if definition else None,
                "species": species.model_dump() if species else None,
                "produce_item": items[species.produce_item_id].model_dump() if species else None,
                "capacity": parameters.capacity,
                "feed_per_cycle": parameters.feed_per_cycle,
                "generation_cap": parameters.generation_cap,
                "generation_gain": parameters.generation_gain,
                "generation_decay": parameters.generation_decay,
                "steady_stock": parameters.steady_stock if species else 0,
                "cycle_seconds": parameters.cycle_seconds,
                "next_cycle_seconds": max(0, parameters.cycle_seconds - pond.settle_remainder) if species else 0,
                "fry_total": pond.fry_total,
                "population": pond.population,
                "next_spawn": (
                    max(0, min(
                        floor(pond.growth_remainder + pond.stock * parameters.growth_rate),
                        parameters.capacity - pond.population,
                    ))
                    if species else 0
                ),
                "maturation_seconds": int(parameters.maturation_cycles * parameters.cycle_seconds) if species else 0,
                "next_maturation_seconds": (
                    int(min(batch.cycles_left for batch in pond.fry) * parameters.cycle_seconds)
                    if pond.fry and parameters.cycle_seconds
                    else 0
                ),
                "quality_ability": round(
                    self._aquatic_ability(player, pond.assigned_partner_ids)
                    + self._pond_tier(pond).quality_bonus
                    + player.feed_slot.quality_score
                    + pond.generation_score,
                    2,
                ),
                "empty": pond.empty,
                "assigned_partners": assigned_partners,
            })
        codex_species = {entry.item_id for entry in player.fish_codex.entries}
        codex_pool: list[str] = []
        for spot in self.content.fishing_spots:
            for output in spot.outputs:
                if output.codex and output.item_id not in codex_pool:
                    codex_pool.append(output.item_id)
            if spot.big_catch and spot.big_catch.item_id not in codex_pool:
                codex_pool.append(spot.big_catch.item_id)
        built = {pond.pond_id for pond in player.ponds}
        return {
            "unlocked": any(entry["unlocked"] for entry in spots),
            "ability": ability,
            "buildable_ponds": [
                {
                    **definition.model_dump(),
                    "unlocked": player.level >= definition.min_level,
                    "affordable": player.coins >= definition.build_cost,
                    "capacity": (self.content.pond_tier_map.get(definition.tier).capacity
                                 if self.content.pond_tier_map.get(definition.tier) else 0),
                }
                for definition in self.content.ponds
                if definition.id not in built
            ],
            "companion_partner_id": player.fishing.companion_partner_id or None,
            "companion": partner_map.get(player.fishing.companion_partner_id),
            "spots": spots,
            "next_spot_level": next(
                (spot.min_level for spot in self.content.fishing_spots if player.level < spot.min_level),
                None,
            ),
            "combo_rules": self.content.fishing_combo.model_dump(),
            "combo_cap": self._combo_cap(player),
            "combo": {
                "spot_id": player.fishing.spot_id or None,
                "layers": self._current_combo(player, player.fishing.spot_id, now) if player.fishing.spot_id else 0,
                "updated_at": player.fishing.combo_updated_at,
            },
            "pending_big_catch": self._big_catch_snapshot(player, now),
            "codex": {
                "recorded": len(player.fish_codex.entries),
                "total": len(codex_pool),
                "entries": [
                    {
                        **entry.model_dump(),
                        "item": items[entry.item_id].model_dump() if entry.item_id in items else None,
                    }
                    for entry in player.fish_codex.entries
                ],
                # 没见过的那一格只回一个占位，连名字和图标都不给 —— 直接读接口也看不到谜底。
                "pool": [
                    {"item_id": item_id, "item": items[item_id].model_dump(), "recorded": True}
                    if item_id in codex_species
                    else {"item_id": None, "item": None, "recorded": False}
                    for item_id in codex_pool
                    if item_id in items
                ],
                "milestones": [
                    {
                        **milestone.model_dump(exclude={"reward"}),
                        "reward": self._reward_snapshot(milestone.reward),
                        "claimed": milestone.id in player.fish_codex.claimed_milestones,
                    }
                    for milestone in self.content.fish_codex_milestones
                ],
            },
            "ponds": ponds,
            "next_pond_level": next(
                (entry.min_level for entry in self.content.ponds if player.level < entry.min_level),
                None,
            ),
            "species": [
                {
                    **species.model_dump(),
                    "fry_item": items[species.fry_item_id].model_dump(),
                    "produce_item": items[species.produce_item_id].model_dump(),
                    "owned_fry": sum(player.inventory.get(species.fry_item_id, {}).values()),
                    "unlocked": player.level >= species.min_level,
                }
                for species in self.content.pond_species
            ],
            "feed_slot": {
                "name": slot_rules.name if slot_rules else "饲料槽",
                "units": round(player.feed_slot.units, 2),
                "quality_score": round(player.feed_slot.quality_score, 2),
                "capacity": slot_rules.capacity if slot_rules else 0,
                "hourly_rate": hourly_rate,
                "runtime_seconds": slot_runtime_seconds(player.feed_slot, hourly_rate),
                "quality_multipliers": slot_rules.quality_multipliers if slot_rules else [],
                "inputs": [
                    {
                        "item_id": item_id,
                        "quality": quality or None,
                        "quality_name": QUALITY_NAMES.get(quality),
                        "quantity": quantity,
                        "item": items[item_id].model_dump(),
                        "units": items[item_id].feed.units,
                        "unit_score": round(
                            items[item_id].feed.score * (slot_rules.multiplier(quality) if slot_rules else 1),
                            2,
                        ),
                    }
                    for item_id, qualities in sorted(player.inventory.items())
                    if item_id in items and items[item_id].feed is not None
                    for quality, quantity in sorted(qualities.items())
                    if quantity > 0
                ],
            },
        }

    def convert_maple_flame(self, oauth_sub: str, quantity: int) -> dict:
        quantity = int(quantity)
        if quantity < 1:
            raise GameError("invalid_quantity", "兑换数量必须为正数")
        cost = quantity * self.content.gacha_economy.maple_flame_per_leaf

        def mutation(player: PlayerState):
            if player.maple_flame < cost:
                raise GameError("resource_insufficient", "枫火不足")
            player.maple_flame -= cost
            player.guide_leaves += quantity
            return {"quantity": quantity, "maple_flame_spent": cost}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def recruit(self, oauth_sub: str, count: int, request_id: str, pool_id: str) -> dict:
        if count not in (1, 10):
            raise GameError("invalid_pull_count", "只能单次或十次招募")
        request_id = str(request_id or "").strip()
        if len(request_id) < 8 or len(request_id) > 128:
            raise GameError("invalid_request_id", "招募请求标识不正确")
        now = self._now()
        gacha = self._gacha_pool(pool_id)
        economy = self.content.gacha_economy
        catalog = self.partner_catalog_loader()
        partners_by_rarity = self._pool_partner_candidates(gacha, catalog)

        def mutation(player: PlayerState):
            self._settle(player, now)
            if player.level < gacha.min_level:
                raise GameError("content_locked", f"达到 {gacha.min_level} 级后开放招募")
            previous = next((entry for entry in player.gacha_history if entry.request_id == request_id), None)
            if previous:
                return {**previous.model_dump(), "replayed": True}
            if not self._pool_is_open(partners_by_rarity):
                raise GameError("gacha_pool_invalid", "这个招募池暂时无法招募", 500)
            if player.guide_leaves < count:
                raise GameError("resource_insufficient", "引路枫叶不足")
            progress = player.gacha_progress.get(pool_id)
            if progress is None:
                progress = GachaPoolProgressState()
                player.gacha_progress[pool_id] = progress
            if gacha.max_pulls_per_player is not None and progress.total_pulls + count > gacha.max_pulls_per_player:
                remaining = max(0, gacha.max_pulls_per_player - progress.total_pulls)
                raise GameError("gacha_pool_exhausted", f"这个招募池最多能招募 {gacha.max_pulls_per_player} 次，你还剩 {remaining} 次")

            player.guide_leaves -= count
            results: list[GachaDropRecord] = []
            for _ in range(count):
                force_five = progress.five_pity + 1 >= gacha.five_star_pity
                force_four = progress.four_pity + 1 >= gacha.four_star_guarantee
                rarity = 5 if force_five else 4 if force_four else self._roll_gacha_rarity(gacha, progress)
                if rarity is None:
                    drop = self._roll_gacha_item(gacha, player)
                    results.append(drop)
                    progress.four_pity += 1
                    progress.five_pity += 1
                else:
                    candidates = partners_by_rarity[rarity]
                    if not candidates:
                        raise GameError("gacha_pool_invalid", f"招募池没有 {rarity} 星伙伴", 500)
                    definition = self._pick_gacha_partner(gacha, candidates, rarity)
                    owned = next(
                        (entry for entry in player.owned_partners if entry.partner_id == definition.id),
                        None,
                    )
                    marks = economy.duplicate_marks[rarity] if owned else 0
                    if owned:
                        player.companion_marks += marks
                    else:
                        player.owned_partners.append(OwnedPartnerState(
                            partner_id=definition.id,
                            stars=definition.rarity,
                            acquired_at=now,
                        ))
                    results.append(GachaDropRecord(
                        kind="partner",
                        content_id=definition.id,
                        rarity=rarity,
                        duplicate=owned is not None,
                        companion_marks=marks,
                    ))
                    progress.four_pity = 0 if rarity >= 4 else progress.four_pity + 1
                    progress.five_pity = 0 if rarity == 5 else progress.five_pity + 1
                progress.total_pulls += 1

            record = GachaRequestRecord(
                request_id=request_id,
                pool_id=pool_id,
                count=count,
                created_at=now,
                results=results,
            )
            player.gacha_history.append(record)
            return {**record.model_dump(), "replayed": False}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def recruit_by_identity(self, identity: QQIdentity, count: int, request_id: str, pool_id: str) -> dict:
        player_id = self.repository.player_id_for_identity(identity)
        player = self.repository.get(player_id) if player_id else None
        if player is None:
            raise GameError("identity_not_bound", "这个 QQ 身份尚未绑定红叶镇角色", 404)
        return self.recruit(player.oauth_sub, count, request_id, pool_id)

    def train_partner(self, oauth_sub: str, partner_id: str, item_id: str, quantity: int) -> dict:
        quantity = int(quantity)
        if quantity < 1 or quantity > 99:
            raise GameError("invalid_quantity", "使用数量需在 1 到 99 之间")
        book_experience = self.content.partner_growth.experience_books.get(item_id)
        if book_experience is None:
            raise GameError("experience_item_invalid", "这个物品不能用于伙伴升级")

        def mutation(player: PlayerState):
            owned = self._owned_partner(player, partner_id)
            try:
                remove_item(player, item_id, quantity)
            except EconomyError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            progress = self._grant_partner_experience(owned, book_experience * quantity)
            return {"partner_id": partner_id, "item_id": item_id, "quantity": quantity, **progress}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def star_up_partner(self, oauth_sub: str, partner_id: str) -> dict:
        def mutation(player: PlayerState):
            owned = self._owned_partner(player, partner_id)
            if owned.stars >= 5:
                raise GameError("partner_max_stars", "伙伴已经达到五星")
            cost = self.content.gacha_economy.star_up_costs[owned.stars]
            if player.companion_marks < cost:
                raise GameError("resource_insufficient", "同行印记不足")
            player.companion_marks -= cost
            owned.stars += 1
            return {"partner_id": partner_id, "stars": owned.stars, "companion_marks_spent": cost}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def breakthrough_partner(self, oauth_sub: str, partner_id: str) -> dict:
        catalog = self.partner_catalog_loader()

        def mutation(player: PlayerState):
            owned = self._owned_partner(player, partner_id)
            definition = catalog.partner_map.get(partner_id)
            if definition is None:
                raise GameError("partner_not_found", "伙伴配置不存在", 404)
            if owned.breakthrough >= 2:
                raise GameError("partner_max_breakthrough", "伙伴已经完成全部突破")
            target = owned.breakthrough + 1
            ascension = next((entry for entry in definition.ascensions if entry.breakthrough == target), None)
            if ascension is None:
                raise GameError("breakthrough_unavailable", "这个伙伴暂不能突破", 409)
            try:
                spend_coins(player, ascension.coins)
                consumed = []
                for requirement in ascension.items:
                    consumed.extend(self._consume_minimum_quality_items(
                        player,
                        requirement.item_id,
                        requirement.quantity,
                        requirement.min_quality,
                    ))
            except EconomyError as exc:
                raise GameError("resource_insufficient", str(exc)) from exc
            owned.breakthrough = target
            progress = self._grant_partner_experience(owned, 0)
            return {
                "partner_id": partner_id,
                "breakthrough": target,
                "coins_spent": ascension.coins,
                "consumed": [entry.model_dump() for entry in consumed],
                **progress,
            }

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player)}

    def use_active_task_item(self, oauth_sub: str, industry: str, slot_id: str, task_item_id: str) -> dict:
        now = self._now()
        definition = self.content.task_item_map.get(task_item_id)
        if definition is None or definition.effect != "instant_finish":
            raise GameError("task_item_invalid", "这个道具不能用于进行中的任务")
        if definition.eligible_industries and industry not in definition.eligible_industries:
            raise GameError("task_item_industry_mismatch", "这个道具不能用于当前产业")

        def mutation(player: PlayerState):
            self._settle(player, now)
            production_slot = self._production_slot(player, industry, slot_id)
            task = production_slot.task_snapshot
            if task is None or task.ready_at <= now:
                raise GameError("task_not_active", "这里没有可以加速的任务")
            if task.ready_at - now > int(definition.value):
                raise GameError("task_item_limit", "任务剩余时间过长，暂时不能使用夜灯茶")
            if player.task_items.get(task_item_id, 0) < 1:
                raise GameError("task_item_insufficient", "这个特殊道具数量不足")
            player.task_items[task_item_id] -= 1
            if player.task_items[task_item_id] <= 0:
                player.task_items.pop(task_item_id, None)
            completed_at = max(now, task.started_at + 1)
            task.final_duration = completed_at - task.started_at
            task.minimum_duration = min(task.minimum_duration, task.final_duration)
            task.ready_at = completed_at
            if hasattr(production_slot, "ready_at"):
                production_slot.ready_at = completed_at
            task.applied_effects.append({
                "task_item_id": definition.id,
                "name": definition.name,
                "effect": definition.effect,
                "value": definition.value,
            })
            self._settle(player, completed_at)
            return {"industry": industry, "slot_id": slot_id, "ready_at": completed_at}

        player, result = self._update_by_sub(oauth_sub, mutation)
        return {"result": result, "state": self._snapshot(player, now)}

    def cancel_task(self, oauth_sub: str, industry: str, slot_id: str) -> dict:
        now = self._now()

        def mutation(player: PlayerState):
            self._settle(player, now)
            production_slot = self._production_slot(player, industry, slot_id)
            task = production_slot.task_snapshot
            if task is None:
                raise GameError("task_not_active", "这里没有可以取消的任务")
            if task.ready_at <= now:
                raise GameError("task_already_ready", "任务已经完成，请直接收取产出")
            # 各生产格目前彼此独立，取消只回滚这一格自身消耗的资源。
            # 如果未来出现"某格效果会影响其他格子"的机制（例如跨格加成、连锁触发），
            # 取消逻辑需要额外处理那些外溢效果，而不能只是清空这一格。
            stamina_cost = task.stamina_cost
            if stamina_cost:
                refund_stamina(player, stamina_cost, self.content, now)
            for entry in task.consumed_inputs:
                add_item(player, entry.item_id, entry.quantity, entry.quality)
            refunded_task_items: dict[str, int] = {}
            for effect in task.applied_effects:
                task_item_id = effect.get("task_item_id")
                if not task_item_id:
                    continue
                player.task_items[task_item_id] = player.task_items.get(task_item_id, 0) + 1
                refunded_task_items[task_item_id] = refunded_task_items.get(task_item_id, 0) + 1
            production_slot.task_snapshot = None
            production_slot.task_results = []
            if industry == "farming":
                production_slot.crop_id = ""
                production_slot.planted_at = 0
                production_slot.ready_at = 0
            return {
                "industry": industry,
                "slot_id": slot_id,
                "refunded_inputs": [entry.model_dump() for entry in task.consumed_inputs],
                "refunded_stamina": stamina_cost,
                "refunded_task_items": refunded_task_items,
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
            if (
                not plot.empty
                and plot.ready_at > now
                and not self._task_releases_partner(plot.task_snapshot)
            ):
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
            player.owned_partners.append(OwnedPartnerState(
                partner_id=partner_id,
                stars=partner_map[partner_id].rarity,
                acquired_at=now,
            ))
            granted_partners.append({"partner_id": partner_id, "name": partner_map[partner_id].name})
        if reward.coins:
            grant_coins(player, reward.coins)
        if reward.talent_points:
            player.bonus_talent_points += reward.talent_points
        if reward.maple_flame:
            player.maple_flame += reward.maple_flame
        if reward.guide_leaves:
            player.guide_leaves += reward.guide_leaves
        levels = grant_experience(player, reward.experience, self.content) if reward.experience else []
        return {
            "coins": reward.coins,
            "experience": reward.experience,
            "talent_points": reward.talent_points,
            "maple_flame": reward.maple_flame,
            "guide_leaves": reward.guide_leaves,
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

    # ---------------------------------------------------------------- 今日委托

    def submit_commission(self, oauth_sub: str) -> dict:
        """自己交自己的委托，拿全额枫火。"""
        now = self._now()
        player = self._require_player(oauth_sub)
        self._apply_commission_payouts(player.player_id)

        def mutation(state: PlayerState):
            self._settle(state, now)
            commission = self._require_commission(state)
            if commission.status != "open":
                raise GameError("commission_not_open", self._commission_status_reason(commission), 409)
            consumed = self._consume_commission_items(state, commission)
            commission.status = "completed"
            commission.completed_at = now
            commission.completed_by_name = state.display_name
            state.maple_flame += commission.reward_maple_flame
            return {
                "commission_id": commission.commission_id,
                "npc_name": commission.npc_name,
                "item_id": commission.item_id,
                "quantity": commission.quantity,
                "lucky": commission.lucky,
                "maple_flame": commission.reward_maple_flame,
                "consumed": [snapshot.model_dump() for snapshot in consumed],
            }

        state, result = self.repository.update(player.player_id, mutation)
        return {"result": result, "state": self._snapshot(state, now)}

    def forward_commission(self, oauth_sub: str) -> dict:
        """转发到公共池。别人交掉之后本人拿回配置里的那一份，剩下的归接单的人。"""
        now = self._now()
        board = self._board()
        player = self._require_player(oauth_sub)
        self._apply_commission_payouts(player.player_id)
        published: dict[str, CommissionBoardEntry] = {}

        def mutation(state: PlayerState):
            self._settle(state, now)
            commission = self._require_commission(state)
            if commission.status != "open":
                raise GameError("commission_not_open", self._commission_status_reason(commission), 409)
            commission.status = "forwarded"
            commission.forwarded_at = now
            published["entry"] = self._board_entry(state, commission)
            return {"commission_id": commission.commission_id}

        state, result = self.repository.update(player.player_id, mutation)
        entry = published["entry"]
        try:
            board.publish(entry)
        except Exception:
            # 池子里没有这一条的话，玩家会卡在“已转发”却谁也看不见的状态，必须回滚。
            self.repository.update(player.player_id, lambda rollback: self._revert_forward(rollback, entry.commission_id))
            raise
        return {
            "result": {**result, "owner_reward": entry.owner_reward, "taker_reward": entry.taker_reward},
            "state": self._snapshot(state, now),
        }

    def withdraw_commission(self, oauth_sub: str) -> dict:
        """还没被接走就能撤回，撤回之后自己交仍然是全额。"""
        now = self._now()
        board = self._board()
        player = self._require_player(oauth_sub)
        self._apply_commission_payouts(player.player_id)
        # 回款可能刚刚入账，撤回资格要看结算之后的状态。
        commission = self._require_commission(self._require_player(oauth_sub))
        if commission.status == "forward_completed":
            raise GameError("commission_already_taken", "这份委托已经有人替你完成了", 409)
        if commission.status != "forwarded":
            raise GameError("commission_not_forwarded", "这份委托没有在转发池里", 409)
        entry = board.withdraw(commission.day, commission.commission_id, player.player_id)
        if entry is None:
            raise GameError("commission_already_taken", "这份委托已经被别人接走了", 409)
        try:
            state, result = self.repository.update(
                player.player_id,
                lambda target: self._revert_forward(target, commission.commission_id),
            )
        except Exception:
            board.publish(entry)
            raise
        return {"result": result, "state": self._snapshot(state, now)}

    def take_commission(self, oauth_sub: str, commission_id: str) -> dict:
        """替别人交一份转发出来的委托。先抢占池子里的名额，再扣物品发奖励。"""
        now = self._now()
        board = self._board()
        player = self._require_player(oauth_sub)
        self._apply_commission_payouts(player.player_id)
        day = self._commission_day(now)
        entry = board.get(day, str(commission_id))
        if entry is None:
            raise GameError("commission_not_found", "这份委托不在转发池里", 404)
        if entry.owner_id == player.player_id:
            raise GameError("commission_own", "不能接自己的委托", 409)
        self._check_take_eligibility(player, entry, day)
        payout = CommissionPayout(
            commission_id=entry.commission_id,
            day=day,
            maple_flame=entry.owner_reward,
            taker_name=player.display_name,
            item_id=entry.item_id,
            quantity=entry.quantity,
            completed_at=now,
        )
        if board.take(day, entry.commission_id, player.player_id, payout) is None:
            raise GameError("commission_already_taken", "手慢了，这份委托刚被接走", 409)

        def mutation(state: PlayerState):
            self._settle(state, now)
            self._check_take_eligibility(state, entry, day)
            consumed = self._consume_commission_items(state, entry)
            state.maple_flame += entry.taker_reward
            state.commission_takes.append(TakenCommissionRecord(
                day=day,
                commission_id=entry.commission_id,
                owner_name=entry.owner_name,
                item_id=entry.item_id,
                quantity=entry.quantity,
                reward_maple_flame=entry.taker_reward,
                completed_at=now,
            ))
            del state.commission_takes[:-30]
            return {
                "commission_id": entry.commission_id,
                "owner_name": entry.owner_name,
                "npc_name": entry.npc_name,
                "item_id": entry.item_id,
                "quantity": entry.quantity,
                "lucky": entry.lucky,
                "maple_flame": entry.taker_reward,
                "consumed": [snapshot.model_dump() for snapshot in consumed],
            }

        try:
            state, result = self.repository.update(player.player_id, mutation)
        except Exception:
            board.release(day, entry.commission_id, player.player_id, payout)
            raise
        return {"result": result, "state": self._snapshot(state, now)}

    def submit_commission_by_identity(self, identity: QQIdentity) -> dict:
        return self.submit_commission(self._sub_for_identity(identity))

    def commission_board_by_identity(self, identity: QQIdentity) -> dict:
        return self.commission_board_snapshot(self._sub_for_identity(identity))

    def _sub_for_identity(self, identity: QQIdentity) -> str:
        player_id = self.repository.player_id_for_identity(identity)
        player = self.repository.get(player_id) if player_id else None
        if player is None:
            raise GameError("identity_not_bound", "这个 QQ 身份尚未绑定红叶镇角色", 404)
        return player.oauth_sub

    def commission_board_snapshot(self, oauth_sub: str) -> dict:
        """公共转发池的当前内容。自己的那份不出现在列表里。"""
        now = self._now()
        player = self._require_player(oauth_sub)
        self._apply_commission_payouts(player.player_id)
        board = self.commission_board
        day = self._commission_day(now)
        entries = board.list_open(day, player.player_id, self.content.commissions.board_limit) if board else []
        state = self.repository.get(player.player_id) or player
        remaining = self._remaining_takes(state, day)
        items = self.content.item_map
        return {
            "day": day,
            "available": board is not None,
            "refresh_at": self._commission_refresh_at(day),
            "remaining_takes": remaining,
            "daily_take_limit": self.content.commissions.daily_take_limit,
            "entries": [
                {
                    **entry.model_dump(exclude={"owner_id"}),
                    "item": items[entry.item_id].model_dump() if entry.item_id in items else None,
                    "owned": self._owned_quantity(state, entry.item_id),
                    "can_take": remaining > 0 and self._owned_quantity(state, entry.item_id) >= entry.quantity,
                }
                for entry in entries
            ],
        }

    def _board(self) -> CommissionBoardRepository:
        if self.commission_board is None:
            raise GameError("commission_board_unavailable", "转发池暂时不可用", 503)
        return self.commission_board

    def _require_player(self, oauth_sub: str) -> PlayerState:
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return player

    def _require_commission(self, player: PlayerState) -> CommissionState:
        if player.commission is None:
            raise GameError("commission_unavailable", "今天还没有委托", 404)
        return player.commission

    def _commission_status_reason(self, commission: CommissionState) -> str:
        if commission.status == "forwarded":
            return "这份委托已经转发到公共池了"
        return "今天的委托已经完成了"

    def _commission_day(self, now: int) -> str:
        commissions = self.content.commissions
        return commission_day(now, commissions.reset_hour, commissions.timezone)

    def _commission_refresh_at(self, day: str) -> int:
        commissions = self.content.commissions
        return commission_day_end(day, commissions.reset_hour, commissions.timezone)

    def _owned_quantity(self, player: PlayerState, item_id: str) -> int:
        return sum(player.inventory.get(item_id, {}).values())

    def _remaining_takes(self, player: PlayerState, day: str) -> int:
        taken = sum(1 for entry in player.commission_takes if entry.day == day)
        return max(0, self.content.commissions.daily_take_limit - taken)

    def _check_take_eligibility(self, player: PlayerState, entry: CommissionBoardEntry, day: str) -> None:
        if self._remaining_takes(player, day) <= 0:
            raise GameError("commission_take_limit", "今天已经替别人跑过一趟了", 409)
        if any(record.commission_id == entry.commission_id for record in player.commission_takes):
            raise GameError("commission_already_taken", "你已经接过这份委托了", 409)
        if self._owned_quantity(player, entry.item_id) < entry.quantity:
            item = self.content.item_map.get(entry.item_id)
            raise GameError("resource_insufficient", f"{item.name if item else entry.item_id}数量不足")

    def _consume_commission_items(self, player: PlayerState, request) -> list[TaskInputSnapshot]:
        """委托暂时不看品质，所以从最低品质开始扣，不会吃掉玩家的臻品。"""
        try:
            return self._consume_minimum_quality_items(player, request.item_id, request.quantity, 0)
        except EconomyError as exc:
            item = self.content.item_map.get(request.item_id)
            raise GameError("resource_insufficient", f"{item.name if item else request.item_id}数量不足") from exc

    def _board_entry(self, player: PlayerState, commission: CommissionState) -> CommissionBoardEntry:
        commissions = self.content.commissions
        return CommissionBoardEntry(
            commission_id=commission.commission_id,
            day=commission.day,
            owner_id=player.player_id,
            owner_name=player.display_name,
            npc_name=commission.npc_name,
            npc_title=commission.npc_title,
            line=commission.line,
            item_id=commission.item_id,
            quantity=commission.quantity,
            tier=commission.tier,
            lucky=commission.lucky,
            reward_maple_flame=commission.reward_maple_flame,
            owner_reward=commissions.owner_share(commission.reward_maple_flame),
            taker_reward=commissions.taker_share(commission.reward_maple_flame),
            forwarded_at=commission.forwarded_at,
        )

    def _revert_forward(self, player: PlayerState, commission_id: str) -> dict:
        commission = player.commission
        if commission and commission.commission_id == commission_id and commission.status == "forwarded":
            commission.status = "open"
            commission.forwarded_at = 0
        return {"commission_id": commission_id}

    def _apply_commission_payouts(self, player_id: str) -> None:
        """别人替我交掉之后回给我的枫火。必须在玩家事务之外取出，否则 WATCH 重试会把它吞掉。"""
        board = self.commission_board
        if board is None:
            return
        payouts = board.drain_payouts(player_id)
        if not payouts:
            return
        try:
            self.repository.update(player_id, lambda player: self._credit_payouts(player, payouts))
        except Exception:
            board.restore_payouts(player_id, payouts)
            raise

    def _credit_payouts(self, player: PlayerState, payouts: list[CommissionPayout]) -> None:
        for payout in payouts:
            player.maple_flame += payout.maple_flame
            commission = player.commission
            if commission and commission.commission_id == payout.commission_id:
                commission.status = "forward_completed"
                commission.completed_at = payout.completed_at
                commission.completed_by_name = payout.taker_name

    def _settle_commission(self, player: PlayerState, now: int) -> None:
        """换日就重掷。掷出的内容当场冻结，玩家中途升级不会改掉今天的委托。"""
        if player.level < self.content.commissions.min_level:
            return
        day = self._commission_day(now)
        if player.commission is not None and player.commission.day == day:
            return
        player.commission = self._roll_commission(player, day)
        stale = [index for index, entry in enumerate(player.commission_takes) if entry.day < day]
        for index in reversed(stale):
            del player.commission_takes[index]

    def _unlocked_commission_items(self, player: PlayerState) -> set[str]:
        """能被要求的只有玩家已经能自己产出的东西，条件直接取自现有内容配置。"""
        unlocked: set[str] = set()
        for crop in self.content.crops:
            if crop.min_level <= player.level:
                unlocked.add(crop.produce_item_id)
        gathering_sites = self.content.gathering_site_map
        for task in self.content.gathering_tasks:
            site = gathering_sites.get(task.site_id)
            if site and task.min_level <= player.level and site.min_level <= player.level:
                unlocked.update(output.item_id for output in task.outputs)
        mining_sites = self.content.mining_site_map
        for task in self.content.mining_tasks:
            site = mining_sites.get(task.site_id)
            if site and task.min_level <= player.level and site.min_level <= player.level:
                unlocked.add(task.produce_item_id)
        stations = self.content.crafting_station_map
        for recipe in self.content.recipes:
            station = stations.get(recipe.station_id)
            if not station or station.min_level > player.level:
                continue
            if evaluate_recipe_unlock(player, recipe.unlock_condition.hook, recipe.unlock_condition.params):
                unlocked.add(recipe.produce_item_id)
        return unlocked

    def _roll_commission(self, player: PlayerState, day: str) -> CommissionState | None:
        commissions = self.content.commissions
        entry_map = commissions.entry_map
        candidates = [
            entry_map[item_id]
            for item_id in sorted(self._unlocked_commission_items(player))
            if item_id in entry_map
        ]
        if not candidates:
            return None
        lucky = is_lucky_day(player.player_id, day)
        tiers = commissions.tier_map
        available = sorted({entry.tier for entry in candidates})
        weights = [tiers[tier].lucky_weight if lucky else tiers[tier].weight for tier in available]
        if not any(weights):
            # 幸运日撞上低等级玩家时高难度档可能一个都没解锁，退回手上最难的一档。
            weights = [1 if tier == available[-1] else 0 for tier in available]
        rng = random.Random(commission_seed(player.player_id, day))
        tier = rng.choices(available, weights=weights, k=1)[0]
        item_id = rng.choice(sorted(entry.item_id for entry in candidates if entry.tier == tier))
        entry = entry_map[item_id]
        quantity_min, quantity_max = entry.quantity_range(tiers[tier])
        quantity = rng.randint(quantity_min, quantity_max)
        npc = commissions.npcs[rng.randrange(len(commissions.npcs))]
        item = self.content.item_map[item_id]
        return CommissionState(
            day=day,
            commission_id=commission_identifier(player.player_id, day),
            npc_id=npc.id,
            npc_name=npc.name,
            npc_title=npc.title,
            line=npc.render(item.name, quantity),
            item_id=item_id,
            quantity=quantity,
            tier=tier,
            lucky=lucky,
            reward_maple_flame=commissions.reward_for(lucky),
        )

    def _commission_snapshot(self, player: PlayerState, now: int) -> dict:
        commissions = self.content.commissions
        day = self._commission_day(now)
        items = self.content.item_map
        commission = player.commission if player.commission and player.commission.day == day else None
        tiers = commissions.tier_map
        payload = None
        if commission:
            owned = self._owned_quantity(player, commission.item_id)
            item = items.get(commission.item_id)
            tier = tiers.get(commission.tier)
            payload = {
                **commission.model_dump(),
                "item": item.model_dump() if item else None,
                "tier_name": tier.name if tier else "",
                "owned": owned,
                "settled": commission.settled,
                "can_submit": commission.status == "open" and owned >= commission.quantity,
                "can_forward": commission.status == "open",
                "can_withdraw": commission.status == "forwarded",
                "owner_reward": commissions.owner_share(commission.reward_maple_flame),
                "taker_reward": commissions.taker_share(commission.reward_maple_flame),
            }
        return {
            "day": day,
            "unlocked": player.level >= commissions.min_level,
            "min_level": commissions.min_level,
            "board_available": self.commission_board is not None,
            "refresh_at": self._commission_refresh_at(day),
            "lucky_weekday": lucky_weekday(player.player_id),
            "lucky_today": is_lucky_day(player.player_id, day),
            "reward_maple_flame": commissions.reward_maple_flame,
            "lucky_reward_maple_flame": commissions.lucky_reward_maple_flame,
            "daily_take_limit": commissions.daily_take_limit,
            "remaining_takes": self._remaining_takes(player, day),
            "takes": [entry.model_dump() for entry in player.commission_takes if entry.day == day],
            "commission": payload,
        }

    # -------------------------------------------------------------------- 镇邮局

    def mailbox(self, oauth_sub: str) -> dict:
        """收件箱全文。顺手清掉指向已删除或已过期信件的收据，存档不会越攒越厚。"""
        now = self._now()
        player = self._require_player(oauth_sub)
        letters = self._delivered_mail(player, now)
        player = self._prune_mail_receipts(player, letters)
        receipts = {entry.mail_id: entry for entry in player.mail_receipts}
        partners = self.partner_catalog_loader()
        return {
            "available": self.mailbox_repository is not None,
            "entries": [
                self._mail_snapshot(mail, receipts.get(mail.mail_id), partners)
                for mail in letters[:MAIL_LIST_LIMIT]
            ],
            **self._mail_summary(player, now, letters),
        }

    def read_mail(self, oauth_sub: str, mail_id: str) -> dict:
        now = self._now()
        player = self._require_player(oauth_sub)
        mail = self._require_mail(player, mail_id, now)

        def mutation(state: PlayerState):
            self._settle(state, now)
            receipt = self._mail_receipt(state, mail.mail_id)
            receipt.read_at = receipt.read_at or now
            return {"mail_id": mail.mail_id, "read_at": receipt.read_at}

        state, result = self.repository.update(player.player_id, mutation)
        return {"result": result, "state": self._snapshot(state, now)}

    def claim_mail(self, oauth_sub: str, mail_id: str) -> dict:
        """整封一次领完。已领标记和发放写在同一次事务里，重复点击不会领两份。"""
        now = self._now()
        player = self._require_player(oauth_sub)
        mail = self._require_mail(player, mail_id, now)
        if mail.attachments.empty:
            raise GameError("mail_without_attachment", "这封信没有附件", 409)

        def mutation(state: PlayerState):
            self._settle(state, now)
            receipt = self._mail_receipt(state, mail.mail_id)
            if receipt.claimed_at:
                raise GameError("mail_already_claimed", "这封信的附件已经领过了", 409)
            receipt.claimed_at = now
            receipt.read_at = receipt.read_at or now
            return {
                "mail_id": mail.mail_id,
                "title": mail.title,
                "granted": self._grant_reward(state, mail.attachments, now),
            }

        state, result = self.repository.update(player.player_id, mutation)
        return {"result": result, "state": self._snapshot(state, now)}

    def admin_send_mail(self, payload: dict) -> dict:
        """写一封信投进公共信箱。全服信只投给截止时刻之前注册的人，个人信指定收件人。"""
        now = self._now()
        store = self._mail_store()
        scope = str(payload.get("scope") or "global").strip()
        if scope not in ("global", "player"):
            raise GameError("invalid_mail_scope", "邮件类型只能是全服或个人")
        recipient = None
        registered_before = 0
        if scope == "player":
            recipient = self.repository.get(str(payload.get("recipient_id") or "").strip())
            if not recipient:
                raise GameError("player_not_found", "收件人不存在", 404)
        else:
            registered_before = int(payload.get("registered_before") or 0) or now
        try:
            attachments = RewardDefinition.model_validate(payload.get("attachments") or {})
            validate_reward_references(attachments, self.content, self.partner_catalog_loader(), "邮件附件")
            mail = MailMessage(
                mail_id=secrets.token_hex(8),
                scope=scope,
                recipient_id=recipient.player_id if recipient else "",
                registered_before=registered_before,
                title=str(payload.get("title") or "").strip(),
                sender=str(payload.get("sender") or "").strip(),
                body=str(payload.get("body") or "").strip(),
                attachments=attachments,
                created_at=now,
                expires_at=int(payload.get("expires_at") or 0),
            )
        except ValueError as exc:
            raise GameError("invalid_mail", str(exc)) from exc
        store.publish(mail)
        return {"mail": self._mail_admin_snapshot(mail, recipient)}

    def admin_list_mail(self, scope: str = "global", player_id: str = "") -> dict:
        """后台信箱视图。顺带把物品和伙伴清单带上，写信页面挑附件时不用再请求一次。"""
        store = self._mail_store()
        if scope == "player":
            recipient = self.repository.get(str(player_id or "").strip())
            if not recipient:
                raise GameError("player_not_found", "收件人不存在", 404)
            letters = store.list_for_player(recipient.player_id)
            entries = [self._mail_admin_snapshot(mail, recipient) for mail in letters]
        else:
            scope = "global"
            entries = [self._mail_admin_snapshot(mail) for mail in store.list_global()]
        return {
            "scope": scope,
            "entries": entries,
            "items": [item.model_dump() for item in self.content.items],
            "partners": [
                {"partner_id": partner.id, "name": partner.name, "rarity": partner.rarity}
                for partner in self.partner_catalog_loader().partners
            ],
        }

    def admin_delete_mail(self, mail_id: str, recipient_id: str = "") -> dict:
        store = self._mail_store()
        mail = store.get(mail_id, recipient_id)
        if not mail or not store.delete(mail_id, recipient_id):
            raise GameError("mail_not_found", "这封信不存在", 404)
        return {"mail_id": mail_id, "title": mail.title}

    def _mail_store(self) -> MailRepository:
        if self.mailbox_repository is None:
            raise GameError("mailbox_unavailable", "镇邮局暂时不可用", 503)
        return self.mailbox_repository

    def _delivered_mail(self, player: PlayerState, now: int) -> list[MailMessage]:
        store = self.mailbox_repository
        if store is None:
            return []
        letters = [
            mail
            for mail in (*store.list_global(), *store.list_for_player(player.player_id))
            if mail.deliverable_to(player, now)
        ]
        letters.sort(key=lambda mail: (-mail.created_at, mail.mail_id))
        return letters

    def _require_mail(self, player: PlayerState, mail_id: str, now: int) -> MailMessage:
        store = self._mail_store()
        mail = store.get(mail_id, player.player_id) or store.get(mail_id)
        if mail is None or not mail.deliverable_to(player, now):
            raise GameError("mail_not_found", "这封信不在你的信箱里", 404)
        return mail

    @staticmethod
    def _mail_receipt(player: PlayerState, mail_id: str) -> MailReceiptState:
        receipt = next((entry for entry in player.mail_receipts if entry.mail_id == mail_id), None)
        if receipt is None:
            receipt = MailReceiptState(mail_id=mail_id)
            player.mail_receipts.append(receipt)
        return receipt

    def _prune_mail_receipts(self, player: PlayerState, letters: list[MailMessage]) -> PlayerState:
        if self.mailbox_repository is None:
            return player
        live = {mail.mail_id for mail in letters}
        if all(entry.mail_id in live for entry in player.mail_receipts):
            return player

        def mutation(state: PlayerState):
            state.mail_receipts = [entry for entry in state.mail_receipts if entry.mail_id in live]

        refreshed, _ = self.repository.update(player.player_id, mutation)
        return refreshed

    def _mail_summary(self, player: PlayerState, now: int, letters: list[MailMessage] | None = None) -> dict:
        letters = self._delivered_mail(player, now) if letters is None else letters
        receipts = {entry.mail_id: entry for entry in player.mail_receipts}
        unread = sum(1 for mail in letters if not receipts.get(mail.mail_id, _UNSEEN).read_at)
        unclaimed = sum(
            1
            for mail in letters
            if not mail.attachments.empty and not receipts.get(mail.mail_id, _UNSEEN).claimed_at
        )
        return {"total": len(letters), "unread": unread, "unclaimed": unclaimed}

    def _mail_snapshot(self, mail: MailMessage, receipt: MailReceiptState | None, partners: PartnerCatalog) -> dict:
        claimed = bool(receipt and receipt.claimed_at)
        return {
            "mail_id": mail.mail_id,
            "scope": mail.scope,
            "title": mail.title,
            "sender": mail.sender,
            "body": mail.body,
            "created_at": mail.created_at,
            "expires_at": mail.expires_at or None,
            "attachments": serialize_reward(mail.attachments, self.content, partners),
            "read": bool(receipt and receipt.read_at),
            "claimed": claimed,
            "claimable": not mail.attachments.empty and not claimed,
        }

    def _mail_admin_snapshot(self, mail: MailMessage, recipient: PlayerState | None = None) -> dict:
        return {
            **mail.model_dump(exclude={"attachments"}),
            "attachments": serialize_reward(mail.attachments, self.content, self.partner_catalog_loader()),
            "recipient_name": recipient.display_name if recipient else "",
        }

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
            owned = OwnedPartnerState(partner_id=partner_id, stars=partner.rarity, acquired_at=now)
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

    def admin_grant_resources(self, player_id: str, coins: int, experience: int, maple_flame: int) -> dict:
        if type(coins) is not int or type(experience) is not int or type(maple_flame) is not int:
            raise GameError("invalid_grant_amount", "发放数量必须是整数")
        if min(coins, experience, maple_flame) < 0 or (coins == 0 and experience == 0 and maple_flame == 0):
            raise GameError("invalid_grant_amount", "请填写要发放的正数资源")

        def mutation(player: PlayerState):
            if coins:
                grant_coins(player, coins)
            if maple_flame:
                player.maple_flame += maple_flame
            unlocked_levels = grant_experience(player, experience, self.content) if experience else []
            return unlocked_levels

        try:
            player, unlocked_levels = self.repository.update(player_id, mutation)
        except KeyError as exc:
            raise GameError("player_not_found", "玩家不存在", 404) from exc
        return {
            "coins": coins,
            "experience": experience,
            "maple_flame": maple_flame,
            "unlocked_levels": unlocked_levels,
            "player": self._admin_player_summary(player),
        }

    def admin_delete_player(self, player_id: str) -> dict:
        """彻底删除一个角色。存档不可恢复，玩家再次登录会当作新居民重新建号。"""
        player = self.repository.get(player_id)
        if not player:
            raise GameError("player_not_found", "玩家不存在", 404)
        summary = self._admin_player_summary(player)
        if self.mailbox_repository is not None:
            for mail in self.mailbox_repository.list_for_player(player_id):
                self.mailbox_repository.delete(mail.mail_id, player_id)
        if not self.repository.delete(player_id):
            raise GameError("player_not_found", "玩家不存在", 404)
        return {"player": summary}

    def _settled_snapshot(self, player_id: str) -> dict:
        now = self._now()
        self._apply_commission_payouts(player_id)

        def mutation(player: PlayerState):
            self._settle(player, now)

        player, _ = self.repository.update(player_id, mutation)
        return self._snapshot(player, now)

    def _update_by_sub(self, oauth_sub: str, mutation):
        player = self.repository.get_by_sub(oauth_sub)
        if not player:
            raise GameError("player_not_found", "角色不存在", 404)
        return self.repository.update(player.player_id, mutation)

    def _roll_gacha_rarity(self, gacha: GachaDefinition, progress: GachaPoolProgressState) -> int | None:
        probabilities = gacha.rarity_probabilities
        if progress.total_pulls < gacha.first_pulls_without_items:
            total = sum(probabilities.values())
            draw = self.rng.random() * total
            for rarity in (5, 4, 3):
                draw -= probabilities[rarity]
                if draw < 0:
                    return rarity
            return 3
        draw = self.rng.random()
        for rarity in (5, 4, 3):
            draw -= probabilities[rarity]
            if draw < 0:
                return rarity
        return None

    @staticmethod
    def _pool_partner_candidates(gacha: GachaDefinition, catalog: PartnerCatalog) -> dict[int, list[PartnerDefinition]]:
        """招募池的候选伙伴：只收画了一破立绘的，partner_ids 非空时再限定在这份名单里。"""
        allowed = set(gacha.partner_ids)
        return {
            rarity: [
                entry
                for entry in catalog.partners
                if entry.rarity == rarity and entry.recruitable and (not allowed or entry.id in allowed)
            ]
            for rarity in (3, 4, 5)
        }

    @staticmethod
    def _pool_is_open(candidates: dict[int, list[PartnerDefinition]]) -> bool:
        """保底会强制抽出 4★ 和 5★，所以三个星级都得有人，池子才算能开。"""
        return all(candidates[rarity] for rarity in (3, 4, 5))

    def _pick_gacha_partner(self, gacha: GachaDefinition, candidates: list[PartnerDefinition], rarity: int) -> PartnerDefinition:
        """五星的 up 池：featured_rate 概率抽中 featured_partner_id，否则在同星级里均匀抽其它角色。"""
        if rarity == 5 and gacha.featured_partner_id:
            featured = next((entry for entry in candidates if entry.id == gacha.featured_partner_id), None)
            if featured is not None:
                if self.rng.random() < gacha.featured_rate:
                    return featured
                others = [entry for entry in candidates if entry.id != gacha.featured_partner_id]
                if others:
                    return others[self.rng.randrange(len(others))]
                return featured
        return candidates[self.rng.randrange(len(candidates))]

    def _roll_gacha_item(self, gacha: GachaDefinition, player: PlayerState) -> GachaDropRecord:
        drops = gacha.item_drops
        total = sum(entry.weight for entry in drops)
        draw = self.rng.random() * total
        selected = drops[-1]
        for entry in drops:
            draw -= entry.weight
            if draw < 0:
                selected = entry
                break
        player.task_items[selected.task_item_id] = (
            player.task_items.get(selected.task_item_id, 0) + selected.quantity
        )
        return GachaDropRecord(
            kind="task_item",
            content_id=selected.task_item_id,
            quantity=selected.quantity,
        )

    @staticmethod
    def _owned_partner(player: PlayerState, partner_id: str) -> OwnedPartnerState:
        owned = next((entry for entry in player.owned_partners if entry.partner_id == partner_id), None)
        if owned is None:
            raise GameError("partner_not_owned", "你还没有这个伙伴", 404)
        return owned

    def _grant_partner_experience(self, owned: OwnedPartnerState, amount: int) -> dict:
        owned.experience += max(0, int(amount))
        previous_level = owned.level
        level_cap = level_cap_for_breakthrough(owned.breakthrough)
        while owned.level < level_cap:
            cost = self.content.partner_growth.experience_for_next_level(owned.level)
            if owned.experience < cost:
                break
            owned.experience -= cost
            owned.level += 1
        return {
            "experience_gained": max(0, int(amount)),
            "previous_level": previous_level,
            "level": owned.level,
            "level_cap": level_cap,
        }

    def _grant_task_partner_experience(
        self,
        player: PlayerState,
        task: ProductionTaskSnapshot | None,
    ) -> list[dict]:
        if task is None or not task.partner_snapshots:
            return []
        amount = max(
            1,
            floor(task.final_duration / self.content.partner_growth.experience_interval_seconds)
            + task.stamina_cost * self.content.partner_growth.experience_per_stamina,
        )
        records = []
        for snapshot in task.partner_snapshots:
            owned = next(
                (entry for entry in player.owned_partners if entry.partner_id == snapshot.partner_id),
                None,
            )
            if owned:
                records.append({"partner_id": owned.partner_id, **self._grant_partner_experience(owned, amount)})
        return records

    def _consume_minimum_quality_items(
        self,
        player: PlayerState,
        item_id: str,
        quantity: int,
        min_quality: int,
    ) -> list[TaskInputSnapshot]:
        available = sum(
            amount
            for quality, amount in player.inventory.get(item_id, {}).items()
            if quality >= min_quality
        )
        if available < quantity:
            raise EconomyError("材料数量不足")
        remaining = quantity
        consumed = []
        for quality, amount in sorted(player.inventory.get(item_id, {}).items()):
            if quality < min_quality or remaining <= 0:
                continue
            taken = min(amount, remaining)
            remove_item(player, item_id, taken, quality)
            consumed.append(TaskInputSnapshot(item_id=item_id, quality=quality, quantity=taken))
            remaining -= taken
        return consumed

    def _production_slot(self, player: PlayerState, industry: str, slot_id: str):
        if industry == "farming":
            try:
                return self._plot(player, int(slot_id))
            except ValueError as exc:
                raise GameError("production_slot_not_found", "生产位置不存在", 404) from exc
        if industry == "gathering":
            return self._gathering_site(player, slot_id)
        if industry == "crafting":
            return self._crafting_station(player, slot_id)
        if industry == "mining":
            return self._mining_site(player, slot_id)
        raise GameError("industry_not_found", "产业不存在", 404)

    def _settle(self, player: PlayerState, now: int) -> None:
        self._normalize_inventory_quality(player)
        partner_map = self.partner_catalog_loader().partner_map
        for owned in player.owned_partners:
            if owned.stars == 0 and owned.partner_id in partner_map:
                owned.stars = partner_map[owned.partner_id].rarity
        level = self.content.level_for_xp(player.experience)
        player.level = level.level
        normalize_plot_slots(player, self.content)
        normalize_gathering_sites(player, self.content)
        normalize_crafting_stations(player, self.content)
        normalize_mining_sites(player, self.content)
        normalize_ponds(player, self.content)
        settle_stamina(player, self.content, now)
        self._settle_aquatic(player, now)
        for plot in player.plots:
            if not plot.empty and plot.ready_at <= now and not plot.task_results:
                self._resolve_output(plot, now, self.content.crop_map.get(plot.crop_id))
        for site in player.gathering_sites:
            if site.task_snapshot and site.task_snapshot.ready_at <= now and not site.task_results:
                self._resolve_gathering_outputs(site, now)
        for station in player.crafting_stations:
            if station.task_snapshot and station.task_snapshot.ready_at <= now and not station.task_results:
                self._resolve_output(station, now)
        for site in player.mining_sites:
            if site.task_snapshot and site.task_snapshot.ready_at <= now and not site.task_results:
                self._resolve_output(site, now)
        self._settle_commission(player, now)

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

    def _build_farming_task_snapshot(
        self,
        player,
        plot,
        crop,
        now: int,
        task_item_id: str = "",
    ) -> ProductionTaskSnapshot:
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
            stamina_cost=crop.stamina_cost,
            quality=crop.quality,
            consumed_inputs=[TaskInputSnapshot(item_id=crop.seed_item_id, quality=0, quantity=1)],
            task_item_id=task_item_id,
        )

    def _production_ability(
        self,
        player: PlayerState,
        assigned_partner_ids: list[str],
        industry: str,
    ) -> tuple[int, int, list[TaskPartnerSnapshot]]:
        rules = self.content.industries[industry]
        catalog = self.partner_catalog_loader()
        owned_map = {entry.partner_id: entry for entry in player.owned_partners}
        partner_snapshots: list[TaskPartnerSnapshot] = []
        for partner_id in assigned_partner_ids:
            owned = owned_map.get(partner_id)
            definition = catalog.partner_map.get(partner_id)
            if owned is None or definition is None:
                raise GameError("partner_assignment_invalid", "驻场伙伴数据无效，请重新安排", 409)
            if not any(entry.industry == industry for entry in definition.tendencies):
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
                ability=definition.ability_at(industry, effective_level, owned.stars),
            ))
        character_ability = rules.character_base_ability + self._industry_ability_bonus(player, industry)
        return character_ability + sum(entry.ability for entry in partner_snapshots), character_ability, partner_snapshots

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
        time_difficulty: int | None,
        produce_item_id: str,
        yield_min: int,
        yield_max: int,
        harvest_xp: int,
        stamina_cost: int,
        quality,
        minimum_duration: int = 1,
        consumed_inputs: list[TaskInputSnapshot] | None = None,
        output_pool: list[TaskOutputSnapshot] | None = None,
        draws: GatheringDrawDefinition | None = None,
        fixed_duration: bool = False,
        yield_efficiency: float = 1,
        task_item_id: str = "",
    ) -> ProductionTaskSnapshot:
        rules = self.content.industries[industry]
        if len(assigned_partner_ids) > rules.collaborator_slots:
            raise GameError("collaborator_slots_exceeded", "这个生产格的伙伴位置超过当前上限", 409)
        total_ability, character_ability, partner_snapshots = self._production_ability(
            player,
            assigned_partner_ids,
            industry,
        )
        task_item = self._consume_start_task_item(player, task_item_id, industry)
        applied_effects = [
            {
                "task_item_id": task_item.id,
                "name": task_item.name,
                "effect": task_item.effect,
                "value": task_item.value,
            }
        ] if task_item else []
        time_efficiency = 1 if fixed_duration else 1 + 2 * total_ability / (total_ability + int(time_difficulty))
        duration_multiplier = task_item.value if task_item and task_item.effect == "duration_multiplier" else 1
        final_duration = max(minimum_duration, ceil(base_duration / time_efficiency))
        if duration_multiplier != 1:
            # 缩时道具压在最小时长之后结算，踩到时长下限的高能力玩家也能吃到这份折扣
            final_duration = max(1, ceil(final_duration * duration_multiplier))
            minimum_duration = min(minimum_duration, final_duration)
        quality_ability = total_ability + round(task_item.value if task_item and task_item.effect == "quality_boost" else 0)
        miracle_unlocked = bool(task_item and task_item.effect == "unlock_miracle")
        miracle_width_multiplier = task_item.value if miracle_unlocked else 1
        probabilities = quality_probabilities(
            quality_ability,
            quality.thresholds,
            quality.width,
            quality.miracle_probability_cap,
            quality.miracle_eligible or miracle_unlocked,
            miracle_width_multiplier=miracle_width_multiplier,
            ignore_miracle_cap=miracle_unlocked,
        )
        effective_yield_min = max(1, floor(yield_min * yield_efficiency))
        effective_yield_max = max(effective_yield_min, floor(yield_max * yield_efficiency))
        extra_yield = round(task_item.value) if task_item and task_item.effect == "yield_bonus" else 0
        effective_draw_count = draw_count(
            total_ability,
            draws.base_draws,
            draws.ability_bonus,
            draws.difficulty,
        ) if draws else 0
        if extra_yield:
            if draws:
                effective_draw_count += extra_yield
            else:
                effective_yield_min += extra_yield
                effective_yield_max += extra_yield
        return ProductionTaskSnapshot(
            industry=industry,
            content_id=content_id,
            production_slot_id=production_slot_id,
            started_at=now,
            ready_at=now + final_duration,
            assigned_partner_ids=list(assigned_partner_ids),
            support_partner_ids=[],
            partner_snapshots=partner_snapshots,
            applied_effects=applied_effects,
            character_ability=character_ability,
            total_ability=total_ability,
            time_efficiency=time_efficiency,
            yield_efficiency=yield_efficiency,
            base_duration=base_duration,
            minimum_duration=minimum_duration,
            final_duration=final_duration,
            stamina_cost=stamina_cost,
            produce_item_id=produce_item_id,
            yield_min=effective_yield_min,
            yield_max=effective_yield_max,
            harvest_xp=harvest_xp,
            consumed_inputs=consumed_inputs or [],
            output_pool=output_pool or [],
            draw_count=effective_draw_count,
            quality_parameters=TaskQualitySnapshot(
                ability=quality_ability,
                thresholds=quality.thresholds,
                width=quality.width,
                miracle_probability_cap=quality.miracle_probability_cap,
                miracle_eligible=quality.miracle_eligible or miracle_unlocked,
                miracle_width_multiplier=miracle_width_multiplier,
                miracle_cap_ignored=miracle_unlocked,
                probabilities=probabilities,
            ),
        )

    def _consume_start_task_item(self, player: PlayerState, task_item_id: str, industry: str):
        task_item_id = str(task_item_id or "").strip()
        if not task_item_id:
            return None
        definition = self.content.task_item_map.get(task_item_id)
        if definition is None or definition.timing != "start":
            raise GameError("task_item_invalid", "这个道具不能在开工时使用")
        if definition.eligible_industries and industry not in definition.eligible_industries:
            raise GameError("task_item_industry_mismatch", "这个道具不能用于当前产业")
        if player.task_items.get(task_item_id, 0) < 1:
            raise GameError("task_item_insufficient", "这个特殊道具数量不足")
        player.task_items[task_item_id] -= 1
        if player.task_items[task_item_id] <= 0:
            player.task_items.pop(task_item_id, None)
        return definition

    @staticmethod
    def _partner_lock_deadlines(player: PlayerState, now: int) -> dict[str, int]:
        deadlines: dict[str, int] = {}
        for production_slot in [*player.plots, *player.gathering_sites, *player.crafting_stations, *player.mining_sites]:
            task = production_slot.task_snapshot
            if task is None or task.ready_at <= now:
                continue
            if GameService._task_releases_partner(task):
                continue
            for partner_id in {*task.assigned_partner_ids, *task.support_partner_ids}:
                deadlines[partner_id] = max(deadlines.get(partner_id, 0), task.ready_at)
        return deadlines

    @staticmethod
    def _task_releases_partner(task: ProductionTaskSnapshot | None) -> bool:
        return bool(task and any(effect.get("effect") == "release_partner" for effect in task.applied_effects))

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
                "task_results": [self._result_snapshot(result) for result in plot.task_results],
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
                "task_results": [self._result_snapshot(result) for result in site.task_results],
                "empty": site.empty,
                "ready": bool(task_snapshot and task_snapshot.ready_at <= now),
                "remaining_seconds": max(0, task_snapshot.ready_at - now) if task_snapshot else 0,
                "definition": definition.model_dump() if definition else None,
                "task": {
                    **gathering_task_map[task_snapshot.content_id].model_dump(),
                    "item": items[gathering_task_map[task_snapshot.content_id].outputs[0].item_id].model_dump(),
                    "outputs": [
                        {**output.model_dump(), "item": items[output.item_id].model_dump()}
                        for output in gathering_task_map[task_snapshot.content_id].outputs
                    ],
                } if task_snapshot and task_snapshot.content_id in gathering_task_map else None,
                "available_tasks": [
                    {
                        **entry.model_dump(),
                        "item": items[entry.outputs[0].item_id].model_dump(),
                        "outputs": [
                            {**output.model_dump(), "item": items[output.item_id].model_dump()}
                            for output in entry.outputs
                        ],
                    }
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
                "task_results": [self._result_snapshot(result) for result in station.task_results],
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
                "task_results": [self._result_snapshot(result) for result in site.task_results],
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
                "maple_flame": player.maple_flame,
                "guide_leaves": player.guide_leaves,
                "companion_marks": player.companion_marks,
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
            "aquatic": self._aquatic_snapshot(player, now, partner_map),
            "inventory": inventory,
            "task_items": [
                {
                    **definition.model_dump(),
                    "quantity": player.task_items.get(definition.id, 0),
                }
                for definition in self.content.task_items
                if player.task_items.get(definition.id, 0) > 0
            ],
            "partners": partner_records,
            "partner_count": len(partner_records),
            "partner_growth": {
                "experience_books": [
                    {
                        "item_id": item_id,
                        "experience": experience,
                        "item": items[item_id].model_dump(),
                        "owned": sum(player.inventory.get(item_id, {}).values()),
                    }
                    for item_id, experience in self.content.partner_growth.experience_books.items()
                ],
            },
            "gacha_pools": self._gacha_pools_snapshot(player),
            "industry_rules": {
                industry: {
                    **rules.model_dump(),
                    "base_character_ability": rules.character_base_ability,
                    "global_ability_bonus": self._industry_ability_bonus(player, industry),
                    "character_base_ability": rules.character_base_ability + self._industry_ability_bonus(player, industry),
                    "base_partner_capacity": rules.partner_capacity,
                    "partner_capacity": self._industry_partner_capacity(player, industry),
                }
                for industry, rules in self.content.industries.items()
            },
            "talents": self._talent_snapshot(player),
            "portals": self._portal_snapshot(player),
            "commissions": self._commission_snapshot(player, now),
            "mail": self._mail_summary(player, now),
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
                "origin_rarity": definition.rarity,
                "stars": owned.stars,
                "description": definition.description,
                "growth_curve": definition.growth_curve,
                "growth_curve_name": GROWTH_CURVE_NAMES[definition.growth_curve],
                "level_cap": level_cap_for_breakthrough(owned.breakthrough),
                "experience_to_next_level": (
                    self.content.partner_growth.experience_for_next_level(owned.level)
                    if owned.level < level_cap_for_breakthrough(owned.breakthrough)
                    else None
                ),
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
                "upgrade_available": owned.level < level_cap_for_breakthrough(owned.breakthrough),
                "star_up_available": owned.stars < 5,
                "star_up_cost": self.content.gacha_economy.star_up_costs.get(owned.stars),
                **self._partner_breakthrough_snapshot(player, definition, owned),
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
            "current_ability": definition.ability_at(tendency.industry, owned.level, owned.stars),
            "effective_level": effective_level,
            "effective_ability": definition.ability_at(tendency.industry, effective_level, owned.stars),
        }

    def _partner_breakthrough_snapshot(self, player: PlayerState, definition, owned: OwnedPartnerState) -> dict:
        if owned.breakthrough >= 2:
            return {"breakthrough_available": False, "breakthrough_reason": "已完成全部突破", "ascension": None}
        target = owned.breakthrough + 1
        ascension = next((entry for entry in definition.ascensions if entry.breakthrough == target), None)
        if ascension is None:
            return {"breakthrough_available": False, "breakthrough_reason": "暂不能突破", "ascension": None}
        items = []
        affordable = player.coins >= ascension.coins
        for requirement in ascension.items:
            item = self.content.item_map.get(requirement.item_id)
            owned_quantity = sum(
                quantity
                for quality, quantity in player.inventory.get(requirement.item_id, {}).items()
                if quality >= requirement.min_quality
            )
            affordable = affordable and item is not None and owned_quantity >= requirement.quantity
            items.append({
                **requirement.model_dump(),
                "name": item.name if item else requirement.item_id,
                "icon": item.icon if item else "package",
                "owned": owned_quantity,
            })
        return {
            "breakthrough_available": affordable,
            "breakthrough_reason": None if affordable else "突破材料不足",
            "ascension": {"breakthrough": target, "coins": ascension.coins, "items": items},
        }

    def _gacha_pools_snapshot(self, player: PlayerState) -> list[dict]:
        catalog = self.partner_catalog_loader()
        catalog_payload = {
            definition.id: {
                "partner_id": definition.id,
                "name": definition.name,
                "rarity": definition.rarity,
                "artwork": (
                    definition.artwork_for(0).model_dump()
                    if definition.artwork_for(0)
                    else None
                ),
                "avatar_crop": next(
                    (entry.model_dump() for entry in definition.avatar_crops if entry.breakthrough == 0),
                    None,
                ),
            }
            for definition in catalog.partners
            if definition.recruitable
        }
        task_items_payload = [entry.model_dump() for entry in self.content.task_items]
        story_assets = self.story_asset_loader().asset_map
        pools = sorted(self.gacha_pool_loader().values(), key=lambda entry: (entry.min_level, entry.pool_id))
        snapshots = []
        for gacha in pools:
            candidates = self._pool_partner_candidates(gacha, catalog)
            # 还凑不齐三个星级的池子（比如限定池的立绘还没画完）先不摆出来。
            if not self._pool_is_open(candidates):
                continue
            progress = player.gacha_progress.get(gacha.pool_id)
            total_pulls = progress.total_pulls if progress else 0
            four_pity = progress.four_pity if progress else 0
            five_pity = progress.five_pity if progress else 0
            remaining_pulls = (
                max(0, gacha.max_pulls_per_player - total_pulls)
                if gacha.max_pulls_per_player is not None
                else None
            )
            # 限定池抽完就撤下，不再占着招募界面。
            if remaining_pulls == 0:
                continue
            background_asset = story_assets.get(gacha.background_asset_id) if gacha.background_asset_id else None
            snapshots.append({
                "pool_id": gacha.pool_id,
                "title": gacha.title,
                "unlocked": player.level >= gacha.min_level,
                "min_level": gacha.min_level,
                "maple_flame_per_leaf": self.content.gacha_economy.maple_flame_per_leaf,
                "rarity_probabilities": gacha.rarity_probabilities,
                "item_probability": gacha.item_probability,
                "four_star_guarantee": gacha.four_star_guarantee,
                "five_star_pity": gacha.five_star_pity,
                "pulls_until_four_star": gacha.four_star_guarantee - four_pity,
                "pulls_until_five_star": gacha.five_star_pity - five_pity,
                "max_pulls_per_player": gacha.max_pulls_per_player,
                "total_pulls": total_pulls,
                "remaining_pulls": remaining_pulls,
                "background": background_asset.model_dump() if background_asset else None,
                "featured_partner_id": gacha.featured_partner_id,
                "featured_rate": gacha.featured_rate,
                "catalog": [
                    catalog_payload[definition.id]
                    for rarity in (5, 4, 3)
                    for definition in candidates[rarity]
                ],
                "task_items": task_items_payload,
            })
        return snapshots

    @staticmethod
    def _clear_partner_assignment(player: PlayerState, partner_id: str) -> None:
        for production_slot in [
            *player.plots,
            *player.gathering_sites,
            *player.crafting_stations,
            *player.mining_sites,
            *player.ponds,
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
        if industry == "aquatic":
            # 陪钓不占编制（不锁定、瞬时完成），驻场在鱼塘的才算。
            return sum(len(pond.assigned_partner_ids) for pond in player.ponds)
        return 0

    def _industry_partner_capacity(self, player: PlayerState, industry: str) -> int:
        rules = self.content.industries[industry]
        bonuses = sum(
            node.partner_capacity_bonus
            for node_id in player.talent_nodes
            if (node := self.content.talent_map.get(node_id)) is not None and node.industry == industry
        )
        return rules.partner_capacity + bonuses

    def _industry_ability_bonus(self, player: PlayerState, industry: str) -> int:
        return sum(
            node.global_ability_bonus
            for node_id in player.talent_nodes
            if (node := self.content.talent_map.get(node_id)) is not None and node.industry == industry
        )

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
        quantity = self.rng.randint(yield_min, yield_max)
        production_slot.task_results = build_results(self.rng, [(item_id, quantity)], probabilities, now)

    def _resolve_gathering_outputs(self, site: GatheringSiteState, now: int) -> None:
        task = site.task_snapshot
        if task is None:
            return
        output_pool = task.output_pool or [TaskOutputSnapshot(
            item_id=task.produce_item_id,
            weight=1,
            chance=1,
            quantity_min=task.yield_min,
            quantity_max=task.yield_max,
        )]
        if task.draw_count and any(output.weight > 0 for output in output_pool):
            batches = [
                (output.item_id, self.rng.randint(output.quantity_min, output.quantity_max))
                for output in (pick_weighted(self.rng, output_pool) for _ in range(task.draw_count))
            ]
        else:
            batches = [
                (output.item_id, self.rng.randint(output.quantity_min, output.quantity_max))
                for output in output_pool
                if output.chance == 1 or self.rng.random() < output.chance
            ]
        site.task_results = build_results(self.rng, batches, task.quality_parameters.probabilities, now)

    def _result_snapshot(self, result: ProductionResultSnapshot) -> dict:
        item = self.content.item_map.get(result.item_id)
        return {
            **result.model_dump(),
            "quality_name": QUALITY_NAMES[result.quality],
            "item": item.model_dump() if item else None,
        }

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
            "experience": player.experience,
            "coins": player.coins,
            "maple_flame": player.maple_flame,
            "owned_partner_ids": [entry.partner_id for entry in player.owned_partners],
            "updated_at": player.updated_at,
        }

    def _now(self) -> int:
        return int(self.clock())
