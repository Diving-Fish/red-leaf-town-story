from __future__ import annotations

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, Field, model_validator


RENAMED_PARTNER_IDS: dict[str, str] = {"sprite_001": "fein"}
LEGACY_PARTNER_LEVEL_COST_BASE = 20
LEGACY_PARTNER_LEVEL_COST_GROWTH = 5
LEGACY_PARTNER_EXPERIENCE_DIVISOR = 12
PARTNER_LEVEL_CAPS = (20, 40, 60)
LEGACY_TASK_STAMINA_COSTS: dict[tuple[str, str], int] = {
    ("crafting", "saw_maple_plank"): 2,
    ("crafting", "make_herbal_salve"): 2,
    ("crafting", "mill_flour"): 2,
    ("crafting", "pickle_carrot"): 2,
    ("mining", "mine_red_copper"): 1,
    ("mining", "mine_moon_silver"): 2,
}
LEGACY_MINING_DURATION_CAPS: dict[str, int] = {
    "mine_red_copper": 12 * 60,
    "mine_moon_silver": 24 * 60,
}


def _legacy_partner_total_experience(level: int, experience: int = 0) -> int:
    completed_levels = max(0, int(level) - 1)
    return (
        completed_levels * LEGACY_PARTNER_LEVEL_COST_BASE
        + LEGACY_PARTNER_LEVEL_COST_GROWTH * completed_levels * (completed_levels - 1) // 2
        + max(0, int(experience))
    )


def _partner_progress_from_experience(total_experience: int, breakthrough: int) -> tuple[int, int]:
    remaining = max(0, int(total_experience))
    level = 1
    level_cap = PARTNER_LEVEL_CAPS[max(0, min(2, int(breakthrough)))]
    while level < level_cap:
        cost = LEGACY_PARTNER_LEVEL_COST_BASE + LEGACY_PARTNER_LEVEL_COST_GROWTH * (level - 1)
        if remaining < cost:
            break
        remaining -= cost
        level += 1
    return level, remaining


def _migrate_partner_progress(partner: dict) -> None:
    total = _legacy_partner_total_experience(partner.get("level", 1), partner.get("experience", 0))
    level, experience = _partner_progress_from_experience(
        total // LEGACY_PARTNER_EXPERIENCE_DIVISOR,
        partner.get("breakthrough", 0),
    )
    partner["level"] = level
    partner["experience"] = experience


def _migrate_task_snapshot(snapshot: dict) -> None:
    industry = str(snapshot.get("industry") or "")
    content_id = str(snapshot.get("content_id") or "")
    snapshot["stamina_cost"] = LEGACY_TASK_STAMINA_COSTS.get((industry, content_id), 0)
    snapshot["rule_version"] = 2
    for partner in snapshot.get("partner_snapshots") or []:
        if not isinstance(partner, dict):
            continue
        level, _ = _partner_progress_from_experience(
            _legacy_partner_total_experience(partner.get("level", 1)) // LEGACY_PARTNER_EXPERIENCE_DIVISOR,
            partner.get("breakthrough", 0),
        )
        effective_level, _ = _partner_progress_from_experience(
            _legacy_partner_total_experience(partner.get("effective_level", 1))
            // LEGACY_PARTNER_EXPERIENCE_DIVISOR,
            partner.get("breakthrough", 0),
        )
        partner["level"] = level
        partner["effective_level"] = min(level, effective_level)
    duration_cap = LEGACY_MINING_DURATION_CAPS.get(content_id)
    if industry == "mining" and duration_cap:
        final_duration = min(int(snapshot.get("final_duration", duration_cap)), duration_cap)
        snapshot["base_duration"] = duration_cap
        snapshot["final_duration"] = final_duration
        snapshot["minimum_duration"] = min(int(snapshot.get("minimum_duration", 1)), final_duration)
        snapshot["ready_at"] = int(snapshot.get("started_at", 0)) + final_duration


class TaskPartnerSnapshot(BaseModel):
    partner_id: str = Field(min_length=1)
    level: int = Field(ge=1, le=60)
    effective_level: int = Field(ge=1, le=60)
    breakthrough: int = Field(ge=0, le=2)
    ability: int = Field(ge=0)


class TaskInputSnapshot(BaseModel):
    item_id: str = Field(min_length=1)
    quality: int = Field(ge=0, le=5)
    quantity: int = Field(ge=1)


class TaskOutputSnapshot(BaseModel):
    """产出池的一项。weight 用于加权抽取；chance 只存在于旧快照里，按独立掉率结算。"""

    item_id: str = Field(min_length=1)
    weight: float = Field(default=0, ge=0)
    chance: float = Field(default=0, ge=0, le=1)
    quantity_min: int = Field(ge=1)
    quantity_max: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_quantity(self):
        if self.quantity_max < self.quantity_min:
            raise ValueError("task output quantity_max must be greater than or equal to quantity_min")
        if self.weight <= 0 and self.chance <= 0:
            raise ValueError("task output must carry either a draw weight or a legacy chance")
        return self


class TaskQualitySnapshot(BaseModel):
    ability: int = Field(default=0, ge=0)
    thresholds: list[float] = Field(default_factory=lambda: [1, 2, 3, 4], min_length=4, max_length=4)
    width: float = Field(default=1, gt=0)
    miracle_probability_cap: float = Field(default=0, ge=0, le=0.01)
    miracle_eligible: bool = False
    miracle_width_multiplier: float = Field(default=1, ge=1)
    miracle_cap_ignored: bool = False
    probabilities: list[float] = Field(default_factory=lambda: [1, 0, 0, 0, 0], min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_quality_parameters(self):
        if self.thresholds != sorted(self.thresholds) or len(set(self.thresholds)) != 4:
            raise ValueError("quality thresholds must be strictly increasing")
        if any(probability < 0 or probability > 1 for probability in self.probabilities):
            raise ValueError("quality probabilities must be between zero and one")
        if abs(sum(self.probabilities) - 1.0) > 1e-8:
            raise ValueError("quality probabilities must sum to one")
        return self


class ProductionTaskSnapshot(BaseModel):
    rule_version: int = Field(default=2, ge=1)
    industry: str = Field(min_length=1)
    content_id: str = Field(min_length=1)
    production_slot_id: str = Field(min_length=1)
    started_at: int = Field(ge=0)
    ready_at: int = Field(ge=0)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=2)
    support_partner_ids: list[str] = Field(default_factory=list)
    partner_snapshots: list[TaskPartnerSnapshot] = Field(default_factory=list, max_length=2)
    applied_effects: list[dict[str, object]] = Field(default_factory=list)
    character_ability: int = Field(ge=0)
    total_ability: int = Field(ge=0)
    time_efficiency: float = Field(ge=1, le=3)
    yield_efficiency: float = Field(default=1, ge=1)
    base_duration: int = Field(gt=0)
    minimum_duration: int = Field(default=1, gt=0)
    final_duration: int = Field(gt=0)
    stamina_cost: int = Field(default=0, ge=0)
    produce_item_id: str = Field(min_length=1)
    yield_min: int = Field(ge=1)
    yield_max: int = Field(ge=1)
    harvest_xp: int = Field(ge=0)
    consumed_inputs: list[TaskInputSnapshot] = Field(default_factory=list)
    output_pool: list[TaskOutputSnapshot] = Field(default_factory=list, max_length=5)
    draw_count: int = Field(default=0, ge=0, le=60)
    quality_parameters: TaskQualitySnapshot = Field(default_factory=TaskQualitySnapshot)

    @model_validator(mode="after")
    def validate_snapshot(self):
        if self.ready_at != self.started_at + self.final_duration:
            raise ValueError("task ready_at must equal started_at plus final_duration")
        if self.final_duration > self.base_duration:
            raise ValueError("task final_duration cannot exceed base_duration")
        if self.minimum_duration > self.final_duration:
            raise ValueError("task final_duration cannot be shorter than minimum_duration")
        if self.yield_max < self.yield_min:
            raise ValueError("task yield_max must be greater than or equal to yield_min")
        if self.assigned_partner_ids != [entry.partner_id for entry in self.partner_snapshots]:
            raise ValueError("task partner snapshots must match assigned partner ids")
        output_ids = [entry.item_id for entry in self.output_pool]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("task output pool items must be unique")
        if self.draw_count and self.output_pool and not any(entry.weight > 0 for entry in self.output_pool):
            raise ValueError("weighted task must carry an output pool with positive weights")
        if self.output_pool and not self.draw_count and not any(entry.chance == 1 for entry in self.output_pool):
            raise ValueError("legacy chance pool must contain a guaranteed output")
        return self


class ProductionResultSnapshot(BaseModel):
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    quality: int = Field(ge=1, le=5)
    resolved_at: int = Field(ge=0)


class PlotState(BaseModel):
    slot: int = Field(ge=0)
    crop_id: str = ""
    planted_at: int = 0
    ready_at: int = 0
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_results: list[ProductionResultSnapshot] = Field(default_factory=list, max_length=25)

    @property
    def empty(self) -> bool:
        return not self.crop_id


class GatheringSiteState(BaseModel):
    site_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_results: list[ProductionResultSnapshot] = Field(default_factory=list, max_length=25)

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class CraftingStationState(BaseModel):
    station_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_results: list[ProductionResultSnapshot] = Field(default_factory=list, max_length=25)

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class MiningSiteState(BaseModel):
    site_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_results: list[ProductionResultSnapshot] = Field(default_factory=list, max_length=25)

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class SlotState(BaseModel):
    """饲料槽/肥料槽的状态。quality_score 是存量加权平均，消耗只扣 units、不改分数。"""

    units: float = Field(default=0, ge=0)
    quality_score: float = Field(default=0, ge=0)
    updated_at: int = Field(default=0, ge=0)


class FryBatchState(BaseModel):
    """一批还没长成的鱼苗。

    剩余时间记的是【还差几个繁殖周期】而不是到期时间戳：周期本身随水产能力变化，
    换了更强的伙伴之后，塘里在长的这几批也应该跟着加速；饲料槽空了塘停摆，鱼苗
    同样停止计时。批次各自独立，先投的先成。
    """

    count: int = Field(gt=0)
    cycles_left: float = Field(gt=0)


class PondState(BaseModel):
    """资产轴生产格：没有完成时间，靠 last_settled_at 与参数快照分段推进。"""

    pond_id: str = Field(min_length=1)
    species_id: str = ""
    stock: int = Field(default=0, ge=0)
    fry: list[FryBatchState] = Field(default_factory=list, max_length=64)
    growth_remainder: float = Field(default=0, ge=0)
    generation_score: float = Field(default=0, ge=0)
    settle_remainder: int = Field(default=0, ge=0)
    last_settled_at: int = Field(default=0, ge=0)
    ability: int = Field(default=0, ge=0)
    cycle_seconds: int = Field(default=0, ge=0)
    stalled: bool = False
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)

    @property
    def fry_total(self) -> int:
        return sum(batch.count for batch in self.fry)

    @property
    def population(self) -> int:
        """占塘的总数：鱼苗也要占位置，否则鱼苗池会变成无限仓库。"""

        return self.stock + self.fry_total

    @property
    def empty(self) -> bool:
        return not self.species_id or self.population <= 0


class PendingBigCatchState(BaseModel):
    """抽中大物之后悬而未决的一次搏鱼。玩家要么追加体力搏一把，要么放弃拿回普通鱼。"""

    spot_id: str = Field(min_length=1)
    created_at: int = Field(ge=0)


class FishingState(BaseModel):
    spot_id: str = ""
    combo: int = Field(default=0, ge=0, le=60)
    combo_updated_at: int = Field(default=0, ge=0)
    last_cast_at: int = Field(default=0, ge=0)
    companion_partner_id: str = ""
    pending_big_catch: PendingBigCatchState | None = None
    recent_request_ids: list[str] = Field(default_factory=list, max_length=8)


class FishCodexEntry(BaseModel):
    item_id: str = Field(min_length=1)
    caught: int = Field(default=1, ge=1)
    first_caught_at: int = Field(ge=0)
    max_size: float = Field(default=0, ge=0)


class FishCodexState(BaseModel):
    entries: list[FishCodexEntry] = Field(default_factory=list, max_length=200)
    claimed_milestones: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_codex(self):
        item_ids = [entry.item_id for entry in self.entries]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("fish codex cannot record the same species twice")
        if len(self.claimed_milestones) != len(set(self.claimed_milestones)):
            raise ValueError("fish codex cannot claim the same milestone twice")
        return self

    def entry(self, item_id: str) -> FishCodexEntry | None:
        return next((entry for entry in self.entries if entry.item_id == item_id), None)


class OwnedPartnerState(BaseModel):
    partner_id: str = Field(min_length=1)
    level: int = Field(default=1, ge=1, le=60)
    experience: int = Field(default=0, ge=0)
    breakthrough: int = Field(default=0, ge=0, le=2)
    stars: int = Field(default=0, ge=0, le=5)
    acquired_at: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_id(cls, value):
        if not isinstance(value, dict) or "partner_id" in value:
            return value
        migrated = dict(value)
        if "spirit_id" in migrated:
            migrated["partner_id"] = migrated.pop("spirit_id")
        return migrated


class GachaDropRecord(BaseModel):
    kind: Literal["partner", "task_item"]
    content_id: str = Field(min_length=1)
    rarity: int | None = Field(default=None, ge=3, le=5)
    duplicate: bool = False
    quantity: int = Field(default=1, ge=1)
    companion_marks: int = Field(default=0, ge=0)


class GachaRequestRecord(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    pool_id: str = Field(min_length=1)
    count: Literal[1, 10]
    created_at: int = Field(ge=0)
    results: list[GachaDropRecord] = Field(min_length=1, max_length=10)


class GachaPoolProgressState(BaseModel):
    """玩家在某一个招募池里的进度：累计抽数、四星/五星保底计数器。按 pool_id 分别记录。"""

    total_pulls: int = Field(default=0, ge=0)
    four_pity: int = Field(default=0, ge=0)
    five_pity: int = Field(default=0, ge=0)


def _rename_partner_ids(migrated: dict) -> dict:
    """伙伴改 ID 之后，存档里所有引用它的地方都要跟着改，包括进行中的任务快照。"""
    migrated = deepcopy(migrated)
    for owned in migrated.get("owned_partners") or []:
        if isinstance(owned, dict) and owned.get("partner_id") in RENAMED_PARTNER_IDS:
            owned["partner_id"] = RENAMED_PARTNER_IDS[owned["partner_id"]]
    slots = [
        production_slot
        for key in ("plots", "gathering_sites", "crafting_stations", "mining_sites")
        for production_slot in (migrated.get(key) or [])
        if isinstance(production_slot, dict)
    ]
    for production_slot in slots:
        production_slot["assigned_partner_ids"] = _renamed_list(production_slot.get("assigned_partner_ids"))
        task = production_slot.get("task_snapshot")
        if not isinstance(task, dict):
            continue
        task["assigned_partner_ids"] = _renamed_list(task.get("assigned_partner_ids"))
        task["support_partner_ids"] = _renamed_list(task.get("support_partner_ids"))
        for snapshot in task.get("partner_snapshots") or []:
            if isinstance(snapshot, dict) and snapshot.get("partner_id") in RENAMED_PARTNER_IDS:
                snapshot["partner_id"] = RENAMED_PARTNER_IDS[snapshot["partner_id"]]
    return migrated


def _renamed_list(partner_ids) -> list[str]:
    return [RENAMED_PARTNER_IDS.get(partner_id, partner_id) for partner_id in (partner_ids or [])]


class PortalTributeProgress(BaseModel):
    """一项贡品的交付进度。completed_at 非零表示这一项的奖励已经结算过。"""

    tribute_id: str = Field(min_length=1)
    delivered: int = Field(default=0, ge=0)
    completed_at: int = Field(default=0, ge=0)


class PortalProgressState(BaseModel):
    portal_id: str = Field(min_length=1)
    tributes: list[PortalTributeProgress] = Field(default_factory=list, max_length=8)
    completed_at: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_progress(self):
        tribute_ids = [entry.tribute_id for entry in self.tributes]
        if len(tribute_ids) != len(set(tribute_ids)):
            raise ValueError(f"portal {self.portal_id} records the same tribute twice")
        return self

    def tribute(self, tribute_id: str) -> PortalTributeProgress | None:
        return next((entry for entry in self.tributes if entry.tribute_id == tribute_id), None)


CommissionStatus = Literal["open", "forwarded", "completed", "forward_completed"]


class CommissionState(BaseModel):
    """本人当天的委托。day 是按刷新时区算出来的自然日，换日时整条重掷。"""

    day: str = Field(min_length=1)
    commission_id: str = Field(min_length=8, max_length=64)
    npc_id: str = Field(min_length=1)
    npc_name: str = Field(min_length=1)
    npc_title: str = ""
    line: str = ""
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    tier: int = Field(ge=1, le=9)
    lucky: bool = False
    reward_maple_flame: int = Field(ge=0)
    status: CommissionStatus = "open"
    forwarded_at: int = Field(default=0, ge=0)
    completed_at: int = Field(default=0, ge=0)
    completed_by_name: str = ""

    @model_validator(mode="after")
    def validate_commission(self):
        if self.status == "forwarded" and not self.forwarded_at:
            raise ValueError("forwarded commission must record when it was forwarded")
        if self.status in ("completed", "forward_completed") and not self.completed_at:
            raise ValueError("completed commission must record when it was completed")
        return self

    @property
    def settled(self) -> bool:
        return self.status in ("completed", "forward_completed")


class TakenCommissionRecord(BaseModel):
    """接走并完成的别人的委托。按天限次靠这份流水判断。"""

    day: str = Field(min_length=1)
    commission_id: str = Field(min_length=8, max_length=64)
    owner_name: str = ""
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    reward_maple_flame: int = Field(ge=0)
    completed_at: int = Field(ge=0)


class CommissionBoardEntry(BaseModel):
    """公共转发池里的一条。发布之后内容不再改动，是否被接走由另一张表记录。"""

    commission_id: str = Field(min_length=8, max_length=64)
    day: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_name: str = ""
    npc_name: str = ""
    npc_title: str = ""
    line: str = ""
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    tier: int = Field(ge=1, le=9)
    lucky: bool = False
    reward_maple_flame: int = Field(ge=0)
    owner_reward: int = Field(ge=0)
    taker_reward: int = Field(ge=0)
    forwarded_at: int = Field(ge=0)


class CommissionPayout(BaseModel):
    """别人替我完成之后回给我的那一份。收件人下次读档时入账。"""

    commission_id: str = Field(min_length=8, max_length=64)
    day: str = Field(min_length=1)
    maple_flame: int = Field(ge=0)
    taker_name: str = ""
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    completed_at: int = Field(ge=0)


class MailReceiptState(BaseModel):
    """一封信在我这边的状态。信本身存在公共信箱里，这里只记我读没读过、附件领没领过。"""

    mail_id: str = Field(min_length=8, max_length=64)
    read_at: int = Field(default=0, ge=0)
    claimed_at: int = Field(default=0, ge=0)


class PlayerState(BaseModel):
    schema_version: int = 19
    version: int = 1
    player_id: str
    oauth_sub: str
    display_name: str
    level: int = 1
    experience: int = 0
    coins: int = Field(default=0, ge=0)
    maple_flame: int = Field(default=0, ge=0)
    guide_leaves: int = Field(default=0, ge=0)
    companion_marks: int = Field(default=0, ge=0)
    stamina: int = Field(default=0, ge=0)
    stamina_updated_at: int
    inventory: dict[str, dict[int, int]] = Field(default_factory=dict)
    task_items: dict[str, int] = Field(default_factory=dict)
    plots: list[PlotState] = Field(default_factory=list)
    gathering_sites: list[GatheringSiteState] = Field(default_factory=list)
    crafting_stations: list[CraftingStationState] = Field(default_factory=list)
    mining_sites: list[MiningSiteState] = Field(default_factory=list)
    ponds: list[PondState] = Field(default_factory=list)
    feed_slot: SlotState = Field(default_factory=SlotState)
    fishing: FishingState = Field(default_factory=FishingState)
    fish_codex: FishCodexState = Field(default_factory=FishCodexState)
    talent_nodes: list[str] = Field(default_factory=list)
    owned_partners: list[OwnedPartnerState] = Field(default_factory=list)
    seen_story_ids: list[str] = Field(default_factory=list)
    portals: list[PortalProgressState] = Field(default_factory=list)
    commission: CommissionState | None = None
    commission_takes: list[TakenCommissionRecord] = Field(default_factory=list, max_length=30)
    mail_receipts: list[MailReceiptState] = Field(default_factory=list, max_length=1000)
    bonus_talent_points: int = Field(default=0, ge=0)
    gacha_progress: dict[str, GachaPoolProgressState] = Field(default_factory=dict)
    gacha_history: list[GachaRequestRecord] = Field(default_factory=list)
    created_at: int
    updated_at: int

    @model_validator(mode="before")
    @classmethod
    def migrate_schema(cls, value):
        if not isinstance(value, dict):
            return value
        migrated = deepcopy(value)
        schema_version = int(migrated.get("schema_version", 1))
        if schema_version < 3:
            legacy_partners = migrated.pop("owned_spirits", None)
            if "owned_partners" not in migrated and isinstance(legacy_partners, list):
                migrated["owned_partners"] = legacy_partners
            migrated.setdefault("owned_partners", [])
        if schema_version < 4:
            schema_version = 4
        inventory = migrated.get("inventory")
        if schema_version < 5 or (
            isinstance(inventory, dict)
            and any(not isinstance(quantity, dict) for quantity in inventory.values())
        ):
            migrated["inventory"] = {
                str(item_id): ({0: int(quantity)} if not isinstance(quantity, dict) else quantity)
                for item_id, quantity in (inventory or {}).items()
            }
        if schema_version < 6:
            migrated.setdefault("gathering_sites", [])
            migrated.setdefault("talent_nodes", [])
        if schema_version < 7:
            migrated.setdefault("crafting_stations", [])
        if schema_version < 8:
            migrated.setdefault("mining_sites", [])
        if schema_version < 9:
            migrated.setdefault("seen_story_ids", [])
        if schema_version < 10:
            migrated = _rename_partner_ids(migrated)
        if schema_version < 11:
            migrated.setdefault("portals", [])
            migrated.setdefault("bonus_talent_points", 0)
        if schema_version < 12:
            for site in migrated.get("gathering_sites") or []:
                if not isinstance(site, dict):
                    continue
                legacy_result = site.pop("task_result", None)
                site.setdefault("task_results", [legacy_result] if legacy_result else [])
        if schema_version < 13:
            for key in ("plots", "crafting_stations", "mining_sites"):
                for production_slot in migrated.get(key) or []:
                    if not isinstance(production_slot, dict):
                        continue
                    legacy_result = production_slot.pop("task_result", None)
                    production_slot.setdefault("task_results", [legacy_result] if legacy_result else [])
        if schema_version < 14:
            migrated.setdefault("maple_flame", 0)
            migrated.setdefault("guide_leaves", 0)
            migrated.setdefault("companion_marks", 0)
            migrated.setdefault("task_items", {})
            migrated.setdefault("gacha_total_pulls", 0)
            migrated.setdefault("gacha_four_pity", 0)
            migrated.setdefault("gacha_five_pity", 0)
            migrated.setdefault("gacha_history", [])
        if schema_version < 15:
            # 招募池从单一常驻池拆成多池，保底计数器改成按 pool_id 分开存。
            # 老存档的进度只可能来自当时唯一的常驻池，原样迁移过去。
            legacy_total = migrated.pop("gacha_total_pulls", 0)
            legacy_four = migrated.pop("gacha_four_pity", 0)
            legacy_five = migrated.pop("gacha_five_pity", 0)
            if legacy_total or legacy_four or legacy_five:
                migrated["gacha_progress"] = {
                    "standard-1": {
                        "total_pulls": legacy_total,
                        "four_pity": legacy_four,
                        "five_pity": legacy_five,
                    }
                }
            else:
                migrated.setdefault("gacha_progress", {})
        if schema_version < 16:
            migrated.setdefault("commission", None)
            migrated.setdefault("commission_takes", [])
        if schema_version < 17:
            for partner in migrated.get("owned_partners") or []:
                if isinstance(partner, dict):
                    _migrate_partner_progress(partner)
            for key in ("plots", "gathering_sites", "crafting_stations", "mining_sites"):
                for production_slot in migrated.get(key) or []:
                    if not isinstance(production_slot, dict):
                        continue
                    snapshot = production_slot.get("task_snapshot")
                    if isinstance(snapshot, dict):
                        _migrate_task_snapshot(snapshot)
        if schema_version < 18:
            migrated.setdefault("mail_receipts", [])
        if schema_version < 19:
            # 水产上线。两个资产轴字段和饲料槽都从空状态开始，旧存档不补发任何东西。
            migrated.setdefault("ponds", [])
            migrated.setdefault("feed_slot", {"units": 0, "quality_score": 0})
            migrated.setdefault("fishing", {})
            migrated.setdefault("fish_codex", {})
        migrated["schema_version"] = 19
        return migrated

    @model_validator(mode="after")
    def validate_owned_partners(self):
        for item_id, qualities in self.inventory.items():
            if any(quality < 0 or quality > 5 for quality in qualities):
                raise ValueError(f"inventory item {item_id} has an invalid quality")
            if any(quantity < 0 for quantity in qualities.values()):
                raise ValueError(f"inventory item {item_id} has a negative quantity")
        if any(quantity < 0 for quantity in self.task_items.values()):
            raise ValueError("task item quantity cannot be negative")
        partner_ids = [entry.partner_id for entry in self.owned_partners]
        if len(partner_ids) != len(set(partner_ids)):
            raise ValueError("player cannot own the same partner more than once")
        if len(self.talent_nodes) != len(set(self.talent_nodes)):
            raise ValueError("player cannot unlock the same talent node more than once")
        if len(self.seen_story_ids) != len(set(self.seen_story_ids)):
            raise ValueError("player cannot record the same story more than once")
        request_ids = [entry.request_id for entry in self.gacha_history]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("gacha request ids must be unique")
        portal_ids = [entry.portal_id for entry in self.portals]
        if len(portal_ids) != len(set(portal_ids)):
            raise ValueError("player cannot record the same portal more than once")
        mail_ids = [entry.mail_id for entry in self.mail_receipts]
        if len(mail_ids) != len(set(mail_ids)):
            raise ValueError("player cannot record the same mail more than once")
        taken_ids = [entry.commission_id for entry in self.commission_takes]
        if len(taken_ids) != len(set(taken_ids)):
            raise ValueError("player cannot take the same commission more than once")
        if self.commission and self.commission.commission_id in set(taken_ids):
            raise ValueError("player cannot take their own commission")
        pond_ids = [entry.pond_id for entry in self.ponds]
        if len(pond_ids) != len(set(pond_ids)):
            raise ValueError("player cannot record the same pond more than once")
        assigned_ids = [
            partner_id
            for production_slot in [
                *self.plots,
                *self.gathering_sites,
                *self.crafting_stations,
                *self.mining_sites,
                *self.ponds,
            ]
            for partner_id in production_slot.assigned_partner_ids
        ]
        if len(assigned_ids) != len(set(assigned_ids)):
            raise ValueError("partner cannot be assigned to more than one production slot")
        unknown_ids = set(assigned_ids) - set(partner_ids)
        if unknown_ids:
            raise ValueError("production slots cannot assign partners the player does not own")
        companion_id = self.fishing.companion_partner_id
        if companion_id:
            if companion_id not in set(partner_ids):
                raise ValueError("fishing companion must be a partner the player owns")
            # 陪钓不写锁定引用，但跨产业唯一派驻规则照样适用。
            if companion_id in set(assigned_ids):
                raise ValueError("a partner stationed at a production slot cannot also come fishing")
        return self


class QQIdentity(BaseModel):
    platform: str
    bot_id: str
    subject: str

    @property
    def public_label(self) -> str:
        return f"{self.platform} Bot"
