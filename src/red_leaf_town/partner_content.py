from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from red_leaf_town.partner_traits import partner_trait_codes


Industry = Literal["farming", "gathering", "mining", "aquatic", "livestock", "crafting", "exploration"]
GrowthCurve = Literal["early", "linear", "late"]

INDUSTRY_NAMES: dict[str, str] = {
    "farming": "农作",
    "gathering": "采集",
    "mining": "矿产",
    "aquatic": "水产",
    "livestock": "畜牧",
    "crafting": "加工",
    "exploration": "探索",
}
GROWTH_CURVE_NAMES = {"early": "早熟", "linear": "线性", "late": "晚熟"}
BREAKTHROUGH_LEVEL_CAPS = (20, 40, 60)
DEFAULT_PARTNER_CONTENT_PATH = Path(__file__).resolve().parents[2] / "data" / "partners.json"
_SAVE_LOCK = threading.Lock()


class PartnerTendency(BaseModel):
    industry: Industry
    level_1: int = Field(ge=0)
    level_60: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_growth(self):
        if self.level_60 < self.level_1:
            raise ValueError("level_60 must be greater than or equal to level_1")
        return self


class PartnerArtwork(BaseModel):
    breakthrough: int = Field(ge=0, le=2)
    asset_key: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    content_type: str = Field(pattern=r"^image/")

    @model_validator(mode="after")
    def validate_ratio(self):
        if self.width * 16 != self.height * 9:
            raise ValueError("partner artwork must use a 9:16 aspect ratio")
        return self


class AvatarCrop(BaseModel):
    breakthrough: int = Field(ge=0, le=2)
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=1, gt=0)
    h: int = Field(default=1, gt=0)


def default_avatar_crops() -> list[AvatarCrop]:
    return [AvatarCrop(breakthrough=stage) for stage in range(3)]


class AscensionItemRequirement(BaseModel):
    item_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    min_quality: int = Field(default=0, ge=0, le=5)


class PartnerAscension(BaseModel):
    breakthrough: Literal[1, 2]
    coins: int = Field(default=0, ge=0)
    items: list[AscensionItemRequirement] = Field(min_length=1, max_length=4)


class PartnerDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=64)
    rarity: Literal[3, 4, 5]
    description: str = Field(default="", max_length=500)
    growth_curve: GrowthCurve = "linear"
    tendencies: list[PartnerTendency] = Field(min_length=1, max_length=3)
    trait_codes: list[str] = Field(default_factory=list)
    artworks: list[PartnerArtwork] = Field(default_factory=list, max_length=3)
    avatar_crops: list[AvatarCrop] = Field(default_factory=default_avatar_crops, min_length=3, max_length=3)
    ascensions: list[PartnerAscension] = Field(default_factory=list, max_length=2)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_avatar_crop(cls, value):
        if not isinstance(value, dict) or "avatar_crops" in value:
            return value
        value = dict(value)
        legacy = value.pop("avatar_crop", None)
        if not isinstance(legacy, dict):
            return value
        legacy = dict(legacy)
        stage = int(legacy.pop("source_breakthrough", 0))
        crops = [AvatarCrop(breakthrough=index).model_dump() for index in range(3)]
        if stage in (0, 1, 2):
            crops[stage] = {"breakthrough": stage, **legacy}
        value["avatar_crops"] = crops
        return value

    @model_validator(mode="after")
    def validate_definition(self):
        industries = [entry.industry for entry in self.tendencies]
        if len(industries) != len(set(industries)):
            raise ValueError("partner tendencies must use unique industries")
        if len(self.trait_codes) != len(set(self.trait_codes)):
            raise ValueError("partner trait codes must be unique")
        unknown_traits = set(self.trait_codes) - partner_trait_codes()
        if unknown_traits:
            raise ValueError(f"unknown partner trait codes: {', '.join(sorted(unknown_traits))}")
        stages = [entry.breakthrough for entry in self.artworks]
        if len(stages) != len(set(stages)):
            raise ValueError("partner artworks must use unique breakthrough stages")
        crop_stages = [entry.breakthrough for entry in self.avatar_crops]
        if set(crop_stages) != {0, 1, 2} or len(crop_stages) != 3:
            raise ValueError("avatar crops must contain breakthrough stages 0, 1 and 2")
        for crop in self.avatar_crops:
            source = next(
                (artwork for artwork in self.artworks if artwork.breakthrough == crop.breakthrough),
                None,
            )
            if source and (
                crop.x + crop.w > source.width
                or crop.y + crop.h > source.height
            ):
                raise ValueError(f"avatar crop for breakthrough {crop.breakthrough} must stay inside its artwork")
        ascension_stages = [entry.breakthrough for entry in self.ascensions]
        if len(ascension_stages) != len(set(ascension_stages)):
            raise ValueError("partner ascensions must use unique breakthrough stages")
        return self

    def artwork_for(self, breakthrough: int) -> PartnerArtwork | None:
        return next((artwork for artwork in self.artworks if artwork.breakthrough == breakthrough), None)

    @property
    def complete(self) -> bool:
        return {artwork.breakthrough for artwork in self.artworks} == {0, 1, 2}

    @property
    def recruitable(self) -> bool:
        """没有一破立绘的伙伴还在草稿阶段，不进招募池，也不出现在池子的常驻名单里。"""
        return self.artwork_for(0) is not None

    def ability_at(self, industry: str, level: int, stars: int | None = None) -> int:
        tendency = next((entry for entry in self.tendencies if entry.industry == industry), None)
        if tendency is None:
            raise KeyError(industry)
        progress = growth_progress(level, self.growth_curve)
        base = tendency.level_1 + (tendency.level_60 - tendency.level_1) * progress
        multiplier = {3: 1.0, 4: 1.1, 5: 1.2}.get(stars, 1.0)
        return round(base * multiplier)


class PartnerCatalog(BaseModel):
    schema_version: int = Field(default=2, ge=1)
    partners: list[PartnerDefinition] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_collection(cls, value):
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if int(migrated.get("schema_version", 1)) < 2:
            if "partners" not in migrated and "spirits" in migrated:
                migrated["partners"] = migrated.pop("spirits")
            migrated["schema_version"] = 2
        return migrated

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [partner.id for partner in self.partners]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate partner id")
        return self

    @property
    def partner_map(self) -> dict[str, PartnerDefinition]:
        return {partner.id: partner for partner in self.partners}


def growth_progress(level: int, curve: GrowthCurve) -> float:
    bounded_level = max(1, min(60, int(level)))
    linear = (bounded_level - 1) / 59
    if curve == "early":
        return 1 - (1 - linear) ** 2
    if curve == "late":
        return linear**2
    return linear


def level_cap_for_breakthrough(breakthrough: int) -> int:
    if breakthrough < 0 or breakthrough > 2:
        raise ValueError("breakthrough must be between 0 and 2")
    return BREAKTHROUGH_LEVEL_CAPS[breakthrough]


@lru_cache(maxsize=8)
def load_partner_catalog(path: str | Path = DEFAULT_PARTNER_CONTENT_PATH) -> PartnerCatalog:
    content_path = Path(path)
    if not content_path.exists():
        return PartnerCatalog()
    return PartnerCatalog.model_validate(json.loads(content_path.read_text(encoding="utf-8")))


def save_partner_catalog(catalog: PartnerCatalog, path: str | Path = DEFAULT_PARTNER_CONTENT_PATH) -> None:
    content_path = Path(path)
    payload = catalog.model_dump_json(indent=2)
    with _SAVE_LOCK:
        content_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = content_path.with_suffix(f"{content_path.suffix}.tmp")
        temporary.write_text(f"{payload}\n", encoding="utf-8")
        temporary.replace(content_path)
        load_partner_catalog.cache_clear()
