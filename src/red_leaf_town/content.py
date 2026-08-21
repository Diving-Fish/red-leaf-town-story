from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GameMeta(BaseModel):
    title: str
    starting_coins: int = Field(ge=0)
    initial_inventory: dict[str, int] = Field(default_factory=dict)


class StaminaDefinition(BaseModel):
    restore_seconds: int = Field(gt=0)


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
    kind: Literal["seed", "produce", "material", "product"]
    sell_price: int = Field(ge=0)


class CropDefinition(BaseModel):
    id: str
    name: str
    seed_item_id: str
    produce_item_id: str
    growth_seconds: int = Field(gt=0)
    yield_min: int = Field(ge=1)
    yield_max: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)
    plant_xp: int = Field(ge=0)
    harvest_xp: int = Field(ge=0)
    min_level: int = Field(ge=1)
    accent: str

    @model_validator(mode="after")
    def validate_yield(self):
        if self.yield_max < self.yield_min:
            raise ValueError(f"crop {self.id}: yield_max must be >= yield_min")
        return self


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
    levels: list[LevelDefinition]
    items: list[ItemDefinition]
    crops: list[CropDefinition]
    shop: list[ShopEntry]

    @model_validator(mode="after")
    def validate_references(self):
        def unique(values: list[str], label: str):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} id")

        unique([item.id for item in self.items], "item")
        unique([crop.id for crop in self.crops], "crop")
        unique([entry.id for entry in self.shop], "shop")
        levels = [entry.level for entry in self.levels]
        unique([str(level) for level in levels], "level")
        if levels != sorted(levels) or not levels or levels[0] != 1:
            raise ValueError("levels must be sorted and start at 1")
        xp = [entry.total_xp for entry in self.levels]
        if xp != sorted(xp) or xp[0] != 0:
            raise ValueError("level total_xp must be sorted and start at 0")

        items = {item.id for item in self.items}
        for crop in self.crops:
            if crop.seed_item_id not in items or crop.produce_item_id not in items:
                raise ValueError(f"crop {crop.id} references an unknown item")
        for entry in self.shop:
            if entry.item_id not in items:
                raise ValueError(f"shop {entry.id} references an unknown item")
        return self

    @property
    def item_map(self) -> dict[str, ItemDefinition]:
        return {item.id: item for item in self.items}

    @property
    def crop_map(self) -> dict[str, CropDefinition]:
        return {crop.id: crop for crop in self.crops}

    @property
    def shop_map(self) -> dict[str, ShopEntry]:
        return {entry.id: entry for entry in self.shop}

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


@lru_cache(maxsize=4)
def load_content(path: str | Path = DEFAULT_CONTENT_PATH) -> GameContent:
    content_path = Path(path)
    return GameContent.model_validate(json.loads(content_path.read_text(encoding="utf-8")))
