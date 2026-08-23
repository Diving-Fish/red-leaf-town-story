from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


StoryAssetKind = Literal["background", "portrait"]

STORY_ASSET_KIND_NAMES: dict[str, str] = {"background": "背景", "portrait": "立绘"}
DEFAULT_STORY_ASSET_PATH = Path(__file__).resolve().parents[2] / "data" / "story_assets.json"
_SAVE_LOCK = threading.Lock()


class StoryAssetLayout(BaseModel):
    """立绘在某一种演出模式下的站位。缩放是相对该模式默认高度的倍数。"""

    scale: float = Field(default=1.0, ge=0.4, le=4.0)
    offset_x: float = Field(default=0.0, ge=-0.5, le=0.5)
    offset_y: float = Field(default=0.0, ge=-0.5, le=0.5)


DEFAULT_STORY_LAYOUT = StoryAssetLayout()


class StoryAsset(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    kind: StoryAssetKind
    name: str = Field(min_length=1, max_length=64)
    asset_key: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    content_type: str = Field(pattern=r"^image/")
    inline_layout: StoryAssetLayout = Field(default_factory=StoryAssetLayout)
    stage_layout: StoryAssetLayout = Field(default_factory=StoryAssetLayout)
    created_at: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def migrate_shared_layout(cls, value):
        """旧结构把一套参数直接挂在素材上，两种模式共用。"""
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        shared = {key: migrated.pop(key) for key in ("scale", "offset_x", "offset_y") if key in migrated}
        if shared:
            migrated.setdefault("inline_layout", shared)
            migrated.setdefault("stage_layout", shared)
        return migrated

    @model_validator(mode="after")
    def validate_layout(self):
        if self.kind == "background" and (
            self.inline_layout != DEFAULT_STORY_LAYOUT or self.stage_layout != DEFAULT_STORY_LAYOUT
        ):
            raise ValueError("only portrait assets carry layout parameters")
        return self


class StoryAssetCatalog(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    assets: list[StoryAsset] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [asset.id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate story asset id")
        return self

    @property
    def asset_map(self) -> dict[str, StoryAsset]:
        return {asset.id: asset for asset in self.assets}


@lru_cache(maxsize=8)
def load_story_asset_catalog(path: str | Path = DEFAULT_STORY_ASSET_PATH) -> StoryAssetCatalog:
    content_path = Path(path)
    if not content_path.exists():
        return StoryAssetCatalog()
    return StoryAssetCatalog.model_validate(json.loads(content_path.read_text(encoding="utf-8")))


def save_story_asset_catalog(catalog: StoryAssetCatalog, path: str | Path = DEFAULT_STORY_ASSET_PATH) -> None:
    content_path = Path(path)
    records = sorted(catalog.assets, key=lambda asset: asset.id)
    payload = StoryAssetCatalog(schema_version=catalog.schema_version, assets=records).model_dump_json(indent=2)
    with _SAVE_LOCK:
        content_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = content_path.with_suffix(f"{content_path.suffix}.tmp")
        temporary.write_text(f"{payload}\n", encoding="utf-8")
        temporary.replace(content_path)
        load_story_asset_catalog.cache_clear()
