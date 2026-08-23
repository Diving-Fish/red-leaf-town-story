from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel, Field, model_validator


RENAMED_PARTNER_IDS: dict[str, str] = {"sprite_001": "fein"}


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
    item_id: str = Field(min_length=1)
    chance: float = Field(gt=0, le=1)
    quantity_min: int = Field(ge=1)
    quantity_max: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_quantity(self):
        if self.quantity_max < self.quantity_min:
            raise ValueError("task output quantity_max must be greater than or equal to quantity_min")
        return self


class TaskQualitySnapshot(BaseModel):
    ability: int = Field(default=0, ge=0)
    thresholds: list[float] = Field(default_factory=lambda: [1, 2, 3, 4], min_length=4, max_length=4)
    width: float = Field(default=1, gt=0)
    miracle_probability_cap: float = Field(default=0, ge=0, le=0.01)
    miracle_eligible: bool = False
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
    rule_version: int = Field(default=1, ge=1)
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
    base_duration: int = Field(gt=0)
    minimum_duration: int = Field(default=1, gt=0)
    final_duration: int = Field(gt=0)
    produce_item_id: str = Field(min_length=1)
    yield_min: int = Field(ge=1)
    yield_max: int = Field(ge=1)
    harvest_xp: int = Field(ge=0)
    consumed_inputs: list[TaskInputSnapshot] = Field(default_factory=list)
    output_pool: list[TaskOutputSnapshot] = Field(default_factory=list, max_length=5)
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
        if self.output_pool and not any(entry.chance == 1 for entry in self.output_pool):
            raise ValueError("task output pool must contain a guaranteed output")
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
    task_result: ProductionResultSnapshot | None = None

    @property
    def empty(self) -> bool:
        return not self.crop_id


class GatheringSiteState(BaseModel):
    site_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_results: list[ProductionResultSnapshot] = Field(default_factory=list, max_length=5)

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class CraftingStationState(BaseModel):
    station_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_result: ProductionResultSnapshot | None = None

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class MiningSiteState(BaseModel):
    site_id: str = Field(min_length=1)
    assigned_partner_ids: list[str] = Field(default_factory=list, max_length=1)
    task_snapshot: ProductionTaskSnapshot | None = None
    task_result: ProductionResultSnapshot | None = None

    @property
    def empty(self) -> bool:
        return self.task_snapshot is None


class OwnedPartnerState(BaseModel):
    partner_id: str = Field(min_length=1)
    level: int = Field(default=1, ge=1, le=60)
    breakthrough: int = Field(default=0, ge=0, le=2)
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


class PlayerState(BaseModel):
    schema_version: int = 12
    version: int = 1
    player_id: str
    oauth_sub: str
    display_name: str
    level: int = 1
    experience: int = 0
    coins: int = Field(default=0, ge=0)
    stamina: int = Field(default=0, ge=0)
    stamina_updated_at: int
    inventory: dict[str, dict[int, int]] = Field(default_factory=dict)
    plots: list[PlotState] = Field(default_factory=list)
    gathering_sites: list[GatheringSiteState] = Field(default_factory=list)
    crafting_stations: list[CraftingStationState] = Field(default_factory=list)
    mining_sites: list[MiningSiteState] = Field(default_factory=list)
    talent_nodes: list[str] = Field(default_factory=list)
    owned_partners: list[OwnedPartnerState] = Field(default_factory=list)
    seen_story_ids: list[str] = Field(default_factory=list)
    portals: list[PortalProgressState] = Field(default_factory=list)
    bonus_talent_points: int = Field(default=0, ge=0)
    created_at: int
    updated_at: int

    @model_validator(mode="before")
    @classmethod
    def migrate_schema(cls, value):
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
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
        migrated["schema_version"] = 12
        return migrated

    @model_validator(mode="after")
    def validate_owned_partners(self):
        for item_id, qualities in self.inventory.items():
            if any(quality < 0 or quality > 5 for quality in qualities):
                raise ValueError(f"inventory item {item_id} has an invalid quality")
            if any(quantity < 0 for quantity in qualities.values()):
                raise ValueError(f"inventory item {item_id} has a negative quantity")
        partner_ids = [entry.partner_id for entry in self.owned_partners]
        if len(partner_ids) != len(set(partner_ids)):
            raise ValueError("player cannot own the same partner more than once")
        if len(self.talent_nodes) != len(set(self.talent_nodes)):
            raise ValueError("player cannot unlock the same talent node more than once")
        if len(self.seen_story_ids) != len(set(self.seen_story_ids)):
            raise ValueError("player cannot record the same story more than once")
        portal_ids = [entry.portal_id for entry in self.portals]
        if len(portal_ids) != len(set(portal_ids)):
            raise ValueError("player cannot record the same portal more than once")
        assigned_ids = [
            partner_id
            for production_slot in [*self.plots, *self.gathering_sites, *self.crafting_stations, *self.mining_sites]
            for partner_id in production_slot.assigned_partner_ids
        ]
        if len(assigned_ids) != len(set(assigned_ids)):
            raise ValueError("partner cannot be assigned to more than one production slot")
        unknown_ids = set(assigned_ids) - set(partner_ids)
        if unknown_ids:
            raise ValueError("production slots cannot assign partners the player does not own")
        return self


class QQIdentity(BaseModel):
    platform: str
    bot_id: str
    subject: str

    @property
    def public_label(self) -> str:
        return f"{self.platform} Bot"
