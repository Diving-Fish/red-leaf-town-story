from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from red_leaf_town.content import GatheringDrawDefinition, GatheringOutputDefinition, RecipeInputDefinition


class SailingOutput(GatheringOutputDefinition):
    rarity: Literal['common', 'rare', 'seed', 'equipment']


class SailingRoute(BaseModel):
    id: str
    name: str
    description: str
    duration: int = Field(gt=0)
    coins: int = Field(gt=0)
    stamina: int = Field(gt=0)
    required_voyages: int = Field(ge=0)
    draws: GatheringDrawDefinition
    outputs: list[SailingOutput] = Field(min_length=15, max_length=20)
    equipment_expected_stamina: int = Field(ge=200, le=300)
    events: int = Field(ge=1, le=4)

    @model_validator(mode='after')
    def validate_outputs(self):
        if len({o.item_id for o in self.outputs}) != len(self.outputs):
            raise ValueError('duplicate sailing output')
        equipment = [o for o in self.outputs if o.rarity == 'equipment']
        if len(equipment) != 1 or equipment[0].quantity_min != 1 or equipment[0].quantity_max != 1:
            raise ValueError('each sailing route needs one single-unit equipment output')
        if self.stamina >= self.equipment_expected_stamina:
            raise ValueError('sailing stamina must be below equipment expectation')
        return self


class SailingSupply(BaseModel):
    id: str
    name: str
    description: str
    item_id: str
    quantity: int = Field(ge=0)
    effect: Literal['none', 'quantity', 'rare', 'protect']

    @model_validator(mode='after')
    def validate_cost(self):
        if bool(self.item_id) != (self.quantity > 0):
            raise ValueError('sailing supplies must specify both item and quantity')
        return self


class SailingEvent(BaseModel):
    id: str
    name: str
    attribute: Literal['strength', 'agility', 'intelligence', 'luck']
    success: str
    failure: str


class SailingContent(BaseModel):
    min_level: int = Field(ge=1)
    construction_coins: int = Field(gt=0)
    construction_materials: list[RecipeInputDefinition] = Field(min_length=1)
    routes: list[SailingRoute] = Field(min_length=1)
    supplies: list[SailingSupply] = Field(min_length=1)
    events: list[SailingEvent] = Field(min_length=4)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({m.item_id for m in self.construction_materials}) != len(self.construction_materials):
            raise ValueError("duplicate ship construction material")
        for entries in (self.routes, self.supplies, self.events):
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError('duplicate sailing content ID')
        common = {o.item_id for r in self.routes for o in r.outputs if o.rarity == 'common'}
        rare = {o.item_id for r in self.routes for o in r.outputs if o.rarity == 'rare'}
        if common & rare:
            raise ValueError('rare sailing items cannot be common on another route')
        equipment = [o.item_id for r in self.routes for o in r.outputs if o.rarity == 'equipment']
        if len(set(equipment)) != len(equipment):
            raise ValueError('sailing equipment must be route-exclusive')
        return self

    def validate_items(self, items):
        references = {o.item_id for r in self.routes for o in r.outputs}
        references.update(m.item_id for m in self.construction_materials)
        references |= {s.item_id for s in self.supplies if s.item_id}
        if references - set(items):
            raise ValueError(f'unknown sailing items: {references - set(items)}')


@lru_cache(maxsize=1)
def load_sailing_content() -> SailingContent:
    path = Path(__file__).resolve().parents[2] / 'data' / 'sailing.json'
    return SailingContent.model_validate_json(path.read_text(encoding='utf-8'))
