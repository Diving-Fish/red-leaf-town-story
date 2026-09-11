from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SailingRoute(BaseModel):
    id: str
    name: str
    description: str
    duration: int = Field(gt=0)
    coins: int = Field(gt=0)
    stamina: int = Field(gt=0)
    required_voyages: int = Field(ge=0)
    quantity: int = Field(gt=0)
    common_item: str
    rare_item: str
    events: int = Field(ge=1, le=4)


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
    routes: list[SailingRoute] = Field(min_length=1)
    supplies: list[SailingSupply] = Field(min_length=1)
    events: list[SailingEvent] = Field(min_length=4)

    @model_validator(mode='after')
    def unique_ids(self):
        for entries in (self.routes, self.supplies, self.events):
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError('duplicate sailing content ID')
        return self

    def validate_items(self, items):
        references = {r.common_item for r in self.routes} | {r.rare_item for r in self.routes}
        references |= {s.item_id for s in self.supplies if s.item_id}
        if references - set(items):
            raise ValueError(f'unknown sailing items: {references - set(items)}')


@lru_cache(maxsize=1)
def load_sailing_content() -> SailingContent:
    path = Path(__file__).resolve().parents[2] / 'data' / 'sailing.json'
    return SailingContent.model_validate_json(path.read_text(encoding='utf-8'))
