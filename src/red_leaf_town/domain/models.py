from __future__ import annotations

from pydantic import BaseModel, Field


class PlotState(BaseModel):
    slot: int = Field(ge=0)
    crop_id: str = ""
    planted_at: int = 0
    ready_at: int = 0

    @property
    def empty(self) -> bool:
        return not self.crop_id


class PlayerState(BaseModel):
    schema_version: int = 1
    version: int = 1
    player_id: str
    oauth_sub: str
    display_name: str
    level: int = 1
    experience: int = 0
    coins: int = Field(default=0, ge=0)
    stamina: int = Field(default=0, ge=0)
    stamina_updated_at: int
    inventory: dict[str, int] = Field(default_factory=dict)
    plots: list[PlotState] = Field(default_factory=list)
    created_at: int
    updated_at: int


class QQIdentity(BaseModel):
    platform: str
    bot_id: str
    subject: str

    @property
    def public_label(self) -> str:
        return f"{self.platform} Bot"
