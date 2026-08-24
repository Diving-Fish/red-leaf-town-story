from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GameMeta(BaseModel):
    title: str
    starting_coins: int = Field(ge=0)
    starting_maple_flame: int = Field(default=0, ge=0)
    starting_guide_leaves: int = Field(default=0, ge=0)
    initial_inventory: dict[str, int] = Field(default_factory=dict)


class StaminaDefinition(BaseModel):
    restore_seconds: int = Field(gt=0)


class IndustryRulesDefinition(BaseModel):
    character_base_ability: int = Field(default=0, ge=0)
    partner_capacity: int = Field(default=1, ge=0)
    partner_level_cap: int = Field(default=20, ge=1, le=60)
    collaborator_slots: int = Field(default=1, ge=1, le=2)


class LevelDefinition(BaseModel):
    level: int = Field(ge=1)
    total_xp: int = Field(ge=0)
    plot_slots: int = Field(ge=1)
    stamina_cap: int = Field(ge=1)
    unlocks: list[str] = Field(default_factory=list)


class ItemDefinition(BaseModel):
    id: str
    name: str
    icon: str
    kind: Literal["seed", "produce", "material", "product", "consumable"]
    sell_price: int = Field(ge=0)
    has_quality: bool = False


class QualityGradeDefinition(BaseModel):
    level: int = Field(ge=1, le=5)
    name: str = Field(min_length=1)
    sale_multiplier: float = Field(gt=0)


class QualitySystemDefinition(BaseModel):
    grades: list[QualityGradeDefinition] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_grades(self):
        if [grade.level for grade in self.grades] != [1, 2, 3, 4, 5]:
            raise ValueError("quality grades must define levels 1 through 5 in order")
        return self

    @property
    def grade_map(self) -> dict[int, QualityGradeDefinition]:
        return {grade.level: grade for grade in self.grades}


class QualityCurveDefinition(BaseModel):
    thresholds: list[float] = Field(min_length=4, max_length=4)
    width: float = Field(gt=0)
    miracle_probability_cap: float = Field(default=0, ge=0, le=0.01)
    miracle_eligible: bool = False

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.thresholds != sorted(self.thresholds) or len(set(self.thresholds)) != 4:
            raise ValueError("quality thresholds must be strictly increasing")
        return self


class CropDefinition(BaseModel):
    id: str
    name: str
    icon: str
    seed_item_id: str
    produce_item_id: str
    growth_seconds: int = Field(gt=0)
    time_difficulty: int = Field(gt=0)
    yield_min: int = Field(ge=1)
    yield_max: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)
    plant_xp: int = Field(ge=0)
    harvest_xp: int = Field(ge=0)
    min_level: int = Field(ge=1)
    accent: str
    quality: QualityCurveDefinition

    @model_validator(mode="after")
    def validate_yield(self):
        if self.yield_max < self.yield_min:
            raise ValueError(f"crop {self.id}: yield_max must be >= yield_min")
        return self


class GatheringSiteDefinition(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    accent: str
    min_level: int = Field(default=1, ge=1)


class GatheringOutputDefinition(BaseModel):
    """探索产出池的一项。weight 是抽取权重，抽中后产出 quantity_min—quantity_max 件。"""

    item_id: str = Field(min_length=1)
    weight: float = Field(gt=0)
    quantity_min: int = Field(ge=1)
    quantity_max: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_quantity(self):
        if self.quantity_max < self.quantity_min:
            raise ValueError("gathering output quantity_max must be >= quantity_min")
        return self


class GatheringDrawDefinition(BaseModel):
    """抽取次数曲线：base_draws × (1 + ability_bonus × A/(A + difficulty))。"""

    base_draws: int = Field(ge=1, le=30)
    ability_bonus: float = Field(default=0, ge=0, le=5)
    difficulty: int = Field(gt=0)


class GatheringTaskDefinition(BaseModel):
    id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    duration_seconds: int = Field(gt=0)
    minimum_duration_seconds: int = Field(gt=0)
    time_difficulty: int = Field(gt=0)
    outputs: list[GatheringOutputDefinition] = Field(min_length=2, max_length=5)
    draws: GatheringDrawDefinition
    stamina_cost: int = Field(ge=0)
    collect_xp: int = Field(ge=0)
    min_level: int = Field(ge=1)
    quality: QualityCurveDefinition

    @model_validator(mode="after")
    def validate_outputs(self):
        if self.minimum_duration_seconds > self.duration_seconds:
            raise ValueError(f"gathering task {self.id}: minimum duration cannot exceed base duration")
        item_ids = [entry.item_id for entry in self.outputs]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError(f"gathering task {self.id}: output items must be unique")
        return self

    @property
    def headline_output(self) -> GatheringOutputDefinition:
        """权重最高的一项，用于列表和任务快照里的代表产物。"""

        return max(self.outputs, key=lambda entry: entry.weight)


class TalentNodeDefinition(BaseModel):
    id: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    cost: int = Field(default=1, ge=1)
    min_level: int = Field(default=1, ge=1)
    prerequisites: list[str] = Field(default_factory=list)
    partner_capacity_bonus: int = Field(default=0, ge=0)
    global_ability_bonus: int = Field(default=0, ge=0)


class RecipeUnlockCondition(BaseModel):
    hook: str = Field(min_length=1)
    params: dict[str, int | str | bool]


class RecipeInputDefinition(BaseModel):
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class CraftingStationDefinition(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    accent: str
    min_level: int = Field(default=1, ge=1)


class RecipeDefinition(BaseModel):
    id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    inputs: list[RecipeInputDefinition] = Field(min_length=1)
    produce_item_id: str = Field(min_length=1)
    produce_quantity: int = Field(default=1, ge=1)
    duration_seconds: int = Field(gt=0)
    time_difficulty: int = Field(gt=0)
    stamina_cost: int = Field(ge=0)
    collect_xp: int = Field(ge=0)
    quality: QualityCurveDefinition
    unlock_condition: RecipeUnlockCondition


class MiningSiteDefinition(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    accent: str
    min_level: int = Field(default=1, ge=1)


class MiningTaskDefinition(BaseModel):
    id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    produce_item_id: str = Field(min_length=1)
    duration_seconds: int = Field(gt=0)
    yield_bonus: float = Field(default=1, ge=0, le=5)
    yield_difficulty: int = Field(gt=0)
    yield_min: int = Field(ge=1)
    yield_max: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)
    collect_xp: int = Field(ge=0)
    min_level: int = Field(ge=1)
    quality: QualityCurveDefinition

    @model_validator(mode="after")
    def validate_yield(self):
        if self.yield_max < self.yield_min:
            raise ValueError(f"mining task {self.id}: yield_max must be >= yield_min")
        return self


class TaskItemDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    effect: Literal[
        "quality_boost",
        "duration_multiplier",
        "yield_bonus",
        "release_partner",
        "instant_finish",
        "unlock_miracle",
    ]
    value: float = Field(default=1, gt=0)
    timing: Literal["start", "active"] = "start"
    eligible_industries: list[str] = Field(default_factory=list)


class GachaEconomyDefinition(BaseModel):
    """所有招募池共用的经济参数：兑换汇率、重复伙伴印记、升星消耗。跟具体池子无关。"""

    maple_flame_per_leaf: int = Field(gt=0)
    duplicate_marks: dict[int, int]
    star_up_costs: dict[int, int]

    @model_validator(mode="after")
    def validate_economy(self):
        if set(self.duplicate_marks) != {3, 4, 5}:
            raise ValueError("gacha duplicate marks must define 3, 4 and 5 stars")
        if set(self.star_up_costs) != {3, 4}:
            raise ValueError("star-up costs must define the 3-to-4 and 4-to-5 steps")
        return self


class PartnerGrowthDefinition(BaseModel):
    experience_interval_seconds: int = Field(gt=0)
    experience_per_stamina: int = Field(gt=0)
    level_cost_base: int = Field(gt=0)
    level_cost_growth: int = Field(ge=0)
    experience_books: dict[str, int] = Field(min_length=1)

    def experience_for_next_level(self, level: int) -> int:
        return self.level_cost_base + self.level_cost_growth * max(0, level - 1)


class RewardItemDefinition(BaseModel):
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    quality: int = Field(default=0, ge=0, le=5)


class RewardDefinition(BaseModel):
    """一次性发放的奖励，贡品和传送门全完成共用同一个结构。"""

    coins: int = Field(default=0, ge=0)
    experience: int = Field(default=0, ge=0)
    talent_points: int = Field(default=0, ge=0)
    maple_flame: int = Field(default=0, ge=0)
    guide_leaves: int = Field(default=0, ge=0)
    items: list[RewardItemDefinition] = Field(default_factory=list, max_length=8)
    partner_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_reward(self):
        if len(self.partner_ids) != len(set(self.partner_ids)):
            raise ValueError("reward cannot grant the same partner twice")
        return self

    @property
    def empty(self) -> bool:
        return not (
            self.coins
            or self.experience
            or self.talent_points
            or self.maple_flame
            or self.guide_leaves
            or self.items
            or self.partner_ids
        )


class PortalTributeDefinition(BaseModel):
    """传送门要求的一项贡品。玩家可以分次交，交满结算这一项的奖励。"""

    id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    min_quality: int = Field(default=0, ge=0, le=5)
    reward: RewardDefinition = Field(default_factory=RewardDefinition)


class PortalDefinition(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    accent: str
    min_level: int = Field(default=1, ge=1)
    prerequisites: list[str] = Field(default_factory=list, max_length=4)
    tributes: list[PortalTributeDefinition] = Field(min_length=1, max_length=8)
    completion_reward: RewardDefinition = Field(default_factory=RewardDefinition)

    @model_validator(mode="after")
    def validate_portal(self):
        if self.id in self.prerequisites:
            raise ValueError(f"portal {self.id} cannot require itself")
        if len(self.prerequisites) != len(set(self.prerequisites)):
            raise ValueError(f"portal {self.id} repeats a prerequisite")
        tribute_ids = [tribute.id for tribute in self.tributes]
        if len(tribute_ids) != len(set(tribute_ids)):
            raise ValueError(f"portal {self.id} repeats a tribute id")
        return self


COMMISSIONABLE_KINDS = ("produce", "material", "product")


class CommissionTierDefinition(BaseModel):
    """一个难度档：平日和幸运日各自的抽取权重，以及这一档要求的件数区间。"""

    tier: int = Field(ge=1, le=9)
    name: str = Field(min_length=1)
    weight: float = Field(ge=0)
    lucky_weight: float = Field(ge=0)
    quantity_min: int = Field(ge=1)
    quantity_max: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_tier(self):
        if self.quantity_max < self.quantity_min:
            raise ValueError(f"commission tier {self.tier}: quantity_max must be >= quantity_min")
        return self


class CommissionItemDefinition(BaseModel):
    """把一个物品挂到某个难度档上。件数默认跟随档位，个别物品可以单独覆盖。"""

    item_id: str = Field(min_length=1)
    tier: int = Field(ge=1, le=9)
    quantity_min: int | None = Field(default=None, ge=1)
    quantity_max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_override(self):
        if (self.quantity_min is None) != (self.quantity_max is None):
            raise ValueError(f"commission entry {self.item_id}: quantity override needs both bounds")
        if self.quantity_min is not None and self.quantity_max < self.quantity_min:
            raise ValueError(f"commission entry {self.item_id}: quantity_max must be >= quantity_min")
        return self

    def quantity_range(self, tier: CommissionTierDefinition) -> tuple[int, int]:
        if self.quantity_min is None:
            return tier.quantity_min, tier.quantity_max
        return self.quantity_min, self.quantity_max


class CommissionNpcDefinition(BaseModel):
    """委托人只是包装，line 里必须留出物品和件数的占位。"""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    line: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_line(self):
        for placeholder in ("{item}", "{quantity}"):
            if placeholder not in self.line:
                raise ValueError(f"commission npc {self.id}: line must contain {placeholder}")
        return self

    def render(self, item_name: str, quantity: int) -> str:
        return self.line.replace("{item}", item_name).replace("{quantity}", str(quantity))


class CommissionsDefinition(BaseModel):
    reset_hour: int = Field(default=4, ge=0, le=23)
    timezone: str = Field(default="Asia/Shanghai", min_length=1)
    min_level: int = Field(default=1, ge=1)
    reward_maple_flame: int = Field(gt=0)
    lucky_reward_maple_flame: int = Field(gt=0)
    forward_owner_share: float = Field(gt=0, le=1)
    forward_taker_share: float = Field(gt=0, le=1)
    daily_take_limit: int = Field(default=1, ge=1, le=10)
    board_limit: int = Field(default=30, ge=1, le=200)
    excluded_item_ids: list[str] = Field(default_factory=list)
    tiers: list[CommissionTierDefinition] = Field(min_length=1, max_length=9)
    entries: list[CommissionItemDefinition] = Field(min_length=1)
    npcs: list[CommissionNpcDefinition] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_commissions(self):
        tiers = [entry.tier for entry in self.tiers]
        if len(tiers) != len(set(tiers)):
            raise ValueError("commission tiers must be unique")
        if not any(entry.weight > 0 for entry in self.tiers):
            raise ValueError("commissions need at least one tier with a positive weekday weight")
        if not any(entry.lucky_weight > 0 for entry in self.tiers):
            raise ValueError("commissions need at least one tier with a positive lucky-day weight")
        item_ids = [entry.item_id for entry in self.entries]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("commission entries must not repeat an item")
        unknown_tiers = {entry.tier for entry in self.entries} - set(tiers)
        if unknown_tiers:
            raise ValueError(f"commission entries reference unknown tiers: {sorted(unknown_tiers)}")
        npc_ids = [entry.id for entry in self.npcs]
        if len(npc_ids) != len(set(npc_ids)):
            raise ValueError("commission npc ids must be unique")
        return self

    @property
    def tier_map(self) -> dict[int, CommissionTierDefinition]:
        return {entry.tier: entry for entry in self.tiers}

    @property
    def entry_map(self) -> dict[str, CommissionItemDefinition]:
        return {entry.item_id: entry for entry in self.entries}

    @property
    def npc_map(self) -> dict[str, CommissionNpcDefinition]:
        return {entry.id: entry for entry in self.npcs}

    def reward_for(self, lucky: bool) -> int:
        return self.lucky_reward_maple_flame if lucky else self.reward_maple_flame

    def owner_share(self, reward: int) -> int:
        return max(1, round(reward * self.forward_owner_share))

    def taker_share(self, reward: int) -> int:
        return max(1, round(reward * self.forward_taker_share))


class ShopEntry(BaseModel):
    id: str
    item_id: str
    price: int = Field(gt=0)
    currency: Literal["coins"] = "coins"
    min_level: int = Field(ge=1)


class GameContent(BaseModel):
    schema_version: int = Field(ge=1)
    game: GameMeta
    stamina: StaminaDefinition
    quality: QualitySystemDefinition
    industries: dict[str, IndustryRulesDefinition]
    levels: list[LevelDefinition]
    items: list[ItemDefinition]
    crops: list[CropDefinition]
    gathering_sites: list[GatheringSiteDefinition] = Field(default_factory=list)
    gathering_tasks: list[GatheringTaskDefinition] = Field(default_factory=list)
    talents: list[TalentNodeDefinition] = Field(default_factory=list)
    crafting_stations: list[CraftingStationDefinition] = Field(default_factory=list)
    recipes: list[RecipeDefinition] = Field(default_factory=list)
    mining_sites: list[MiningSiteDefinition] = Field(default_factory=list)
    mining_tasks: list[MiningTaskDefinition] = Field(default_factory=list)
    task_items: list[TaskItemDefinition] = Field(default_factory=list)
    gacha_economy: GachaEconomyDefinition
    partner_growth: PartnerGrowthDefinition
    portals: list[PortalDefinition] = Field(default_factory=list)
    commissions: CommissionsDefinition
    shop: list[ShopEntry]

    @model_validator(mode="after")
    def validate_references(self):
        def unique(values: list[str], label: str):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} id")

        unique([item.id for item in self.items], "item")
        unique([crop.id for crop in self.crops], "crop")
        unique([entry.id for entry in self.shop], "shop")
        unique([entry.id for entry in self.gathering_sites], "gathering site")
        unique([entry.id for entry in self.gathering_tasks], "gathering task")
        unique([entry.id for entry in self.talents], "talent")
        unique([entry.id for entry in self.crafting_stations], "crafting station")
        unique([entry.id for entry in self.recipes], "recipe")
        unique([entry.id for entry in self.mining_sites], "mining site")
        unique([entry.id for entry in self.mining_tasks], "mining task")
        unique([entry.id for entry in self.task_items], "task item")
        unique([entry.id for entry in self.portals], "portal")
        unique([tribute.id for portal in self.portals for tribute in portal.tributes], "portal tribute")
        levels = [entry.level for entry in self.levels]
        unique([str(level) for level in levels], "level")
        if levels != sorted(levels) or not levels or levels[0] != 1:
            raise ValueError("levels must be sorted and start at 1")
        xp = [entry.total_xp for entry in self.levels]
        if xp != sorted(xp) or xp[0] != 0:
            raise ValueError("level total_xp must be sorted and start at 0")
        if "farming" not in self.industries:
            raise ValueError("farming industry rules are required")
        if "gathering" not in self.industries:
            raise ValueError("gathering industry rules are required")
        if "crafting" not in self.industries:
            raise ValueError("crafting industry rules are required")
        if "mining" not in self.industries:
            raise ValueError("mining industry rules are required")

        items = {item.id for item in self.items}
        for crop in self.crops:
            if crop.seed_item_id not in items or crop.produce_item_id not in items:
                raise ValueError(f"crop {crop.id} references an unknown item")
            if not self.item_map[crop.produce_item_id].has_quality:
                raise ValueError(f"crop {crop.id} output must support quality")
        gathering_site_ids = {site.id for site in self.gathering_sites}
        for task in self.gathering_tasks:
            if task.site_id not in gathering_site_ids:
                raise ValueError(f"gathering task {task.id} references an unknown site")
            if any(output.item_id not in items for output in task.outputs):
                raise ValueError(f"gathering task {task.id} references an unknown item")
            if any(not self.item_map[output.item_id].has_quality for output in task.outputs):
                raise ValueError(f"gathering task {task.id} output must support quality")
        talent_ids = {talent.id for talent in self.talents}
        for talent in self.talents:
            if talent.industry not in self.industries:
                raise ValueError(f"talent {talent.id} references an unknown industry")
            if any(prerequisite not in talent_ids for prerequisite in talent.prerequisites):
                raise ValueError(f"talent {talent.id} references an unknown prerequisite")
        crafting_station_ids = {station.id for station in self.crafting_stations}
        from red_leaf_town.recipe_unlocks import recipe_unlock_hook_exists, validate_recipe_unlock
        for recipe in self.recipes:
            if recipe.station_id not in crafting_station_ids:
                raise ValueError(f"recipe {recipe.id} references an unknown crafting station")
            if recipe.produce_item_id not in items:
                raise ValueError(f"recipe {recipe.id} references an unknown output item")
            if not self.item_map[recipe.produce_item_id].has_quality:
                raise ValueError(f"recipe {recipe.id} output must support quality")
            if any(requirement.item_id not in items for requirement in recipe.inputs):
                raise ValueError(f"recipe {recipe.id} references an unknown input item")
            if not recipe_unlock_hook_exists(recipe.unlock_condition.hook):
                raise ValueError(f"recipe {recipe.id} references an unknown unlock hook")
            validate_recipe_unlock(recipe.unlock_condition.hook, recipe.unlock_condition.params)
        mining_site_ids = {site.id for site in self.mining_sites}
        for task in self.mining_tasks:
            if task.site_id not in mining_site_ids:
                raise ValueError(f"mining task {task.id} references an unknown site")
            if task.produce_item_id not in items:
                raise ValueError(f"mining task {task.id} references an unknown item")
            if not self.item_map[task.produce_item_id].has_quality:
                raise ValueError(f"mining task {task.id} output must support quality")
            if task.duration_seconds != task.stamina_cost * self.stamina.restore_seconds:
                raise ValueError(f"mining task {task.id} duration must equal stamina recovery time")
        for entry in self.task_items:
            if entry.effect == "instant_finish" and entry.timing != "active":
                raise ValueError(f"task item {entry.id} must be used on an active task")
            if entry.effect != "instant_finish" and entry.timing != "start":
                raise ValueError(f"task item {entry.id} must be used when a task starts")
            if any(industry not in self.industries for industry in entry.eligible_industries):
                raise ValueError(f"task item {entry.id} references an unknown industry")
        if any(item_id not in items for item_id in self.partner_growth.experience_books):
            raise ValueError("partner growth references an unknown experience book")
        self._validate_portals(items)
        self._validate_commissions()
        for entry in self.shop:
            if entry.item_id not in items:
                raise ValueError(f"shop {entry.id} references an unknown item")
        return self

    def _validate_portals(self, items: set[str]) -> None:
        portal_ids = {portal.id for portal in self.portals}
        for portal in self.portals:
            unknown = [entry for entry in portal.prerequisites if entry not in portal_ids]
            if unknown:
                raise ValueError(f"portal {portal.id} references unknown prerequisites: {', '.join(unknown)}")
            for tribute in portal.tributes:
                if tribute.item_id not in items:
                    raise ValueError(f"portal tribute {tribute.id} references an unknown item")
                if tribute.min_quality and not self.item_map[tribute.item_id].has_quality:
                    raise ValueError(f"portal tribute {tribute.id} demands a quality the item cannot have")
                self._validate_reward(tribute.reward, items, f"portal tribute {tribute.id}")
            self._validate_reward(portal.completion_reward, items, f"portal {portal.id}")
        self._validate_portal_graph()

    def _validate_commissions(self) -> None:
        """新加一个可生产的物品就必须给它定难度档，否则它永远不会出现在委托里。"""
        commissions = self.commissions
        item_map = self.item_map
        unknown = {entry.item_id for entry in commissions.entries} - set(item_map)
        if unknown:
            raise ValueError(f"commissions reference unknown items: {', '.join(sorted(unknown))}")
        excluded = set(commissions.excluded_item_ids)
        unknown_excluded = excluded - set(item_map)
        if unknown_excluded:
            raise ValueError(f"commissions exclude unknown items: {', '.join(sorted(unknown_excluded))}")
        listed = {entry.item_id for entry in commissions.entries}
        overlap = listed & excluded
        if overlap:
            raise ValueError(f"commissions both list and exclude: {', '.join(sorted(overlap))}")
        wrong_kind = [entry.item_id for entry in commissions.entries if item_map[entry.item_id].kind == "seed"]
        if wrong_kind:
            raise ValueError(f"commissions cannot ask for seeds: {', '.join(sorted(wrong_kind))}")
        missing = sorted(
            item.id
            for item in self.items
            if item.kind in COMMISSIONABLE_KINDS and item.id not in listed and item.id not in excluded
        )
        if missing:
            raise ValueError(f"commissions do not grade these items: {', '.join(missing)}")

    def _validate_reward(self, reward: RewardDefinition, items: set[str], label: str) -> None:
        for entry in reward.items:
            if entry.item_id not in items:
                raise ValueError(f"{label} rewards an unknown item")
            if entry.quality and not self.item_map[entry.item_id].has_quality:
                raise ValueError(f"{label} rewards a quality the item cannot have")

    def _validate_portal_graph(self) -> None:
        """解锁是树状的，成环会让整棵子树永远打不开，所以加载时就拦下来。"""
        prerequisites = {portal.id: list(portal.prerequisites) for portal in self.portals}
        resolved: set[str] = set()
        pending = set(prerequisites)
        while pending:
            ready = {
                portal_id
                for portal_id in pending
                if all(entry in resolved for entry in prerequisites[portal_id])
            }
            if not ready:
                raise ValueError(f"portal prerequisites form a cycle: {', '.join(sorted(pending))}")
            resolved |= ready
            pending -= ready

    @property
    def item_map(self) -> dict[str, ItemDefinition]:
        return {item.id: item for item in self.items}

    @property
    def crop_map(self) -> dict[str, CropDefinition]:
        return {crop.id: crop for crop in self.crops}

    @property
    def shop_map(self) -> dict[str, ShopEntry]:
        return {entry.id: entry for entry in self.shop}

    @property
    def gathering_site_map(self) -> dict[str, GatheringSiteDefinition]:
        return {entry.id: entry for entry in self.gathering_sites}

    @property
    def gathering_task_map(self) -> dict[str, GatheringTaskDefinition]:
        return {entry.id: entry for entry in self.gathering_tasks}

    @property
    def talent_map(self) -> dict[str, TalentNodeDefinition]:
        return {entry.id: entry for entry in self.talents}

    @property
    def crafting_station_map(self) -> dict[str, CraftingStationDefinition]:
        return {entry.id: entry for entry in self.crafting_stations}

    @property
    def recipe_map(self) -> dict[str, RecipeDefinition]:
        return {entry.id: entry for entry in self.recipes}

    @property
    def mining_site_map(self) -> dict[str, MiningSiteDefinition]:
        return {entry.id: entry for entry in self.mining_sites}

    @property
    def mining_task_map(self) -> dict[str, MiningTaskDefinition]:
        return {entry.id: entry for entry in self.mining_tasks}

    @property
    def task_item_map(self) -> dict[str, TaskItemDefinition]:
        return {entry.id: entry for entry in self.task_items}

    @property
    def portal_map(self) -> dict[str, PortalDefinition]:
        return {entry.id: entry for entry in self.portals}

    @property
    def portal_tribute_map(self) -> dict[str, tuple[PortalDefinition, PortalTributeDefinition]]:
        return {
            tribute.id: (portal, tribute)
            for portal in self.portals
            for tribute in portal.tributes
        }

    def level_for_xp(self, experience: int) -> LevelDefinition:
        current = self.levels[0]
        for entry in self.levels:
            if experience < entry.total_xp:
                break
            current = entry
        return current

    def level_definition(self, level: int) -> LevelDefinition:
        eligible = [entry for entry in self.levels if entry.level <= level]
        return eligible[-1] if eligible else self.levels[0]


DEFAULT_CONTENT_PATH = Path(__file__).resolve().parents[2] / "data" / "game.json"
_SAVE_LOCK = Lock()


@lru_cache(maxsize=4)
def load_content(path: str | Path = DEFAULT_CONTENT_PATH) -> GameContent:
    content_path = Path(path)
    return GameContent.model_validate(json.loads(content_path.read_text(encoding="utf-8")))


def save_content(content: GameContent, path: str | Path = DEFAULT_CONTENT_PATH) -> None:
    content_path = Path(path)
    payload = content.model_dump_json(indent=2)
    with _SAVE_LOCK:
        content_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = content_path.with_suffix(f"{content_path.suffix}.tmp")
        temporary.write_text(f"{payload}\n", encoding="utf-8")
        temporary.replace(content_path)
        load_content.cache_clear()
