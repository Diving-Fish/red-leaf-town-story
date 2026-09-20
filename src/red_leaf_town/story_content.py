from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from red_leaf_town.content import DEFAULT_CONTENT_PATH, GameContent, RewardDefinition, load_content
from red_leaf_town.partner_content import (
    DEFAULT_PARTNER_CONTENT_PATH,
    PartnerCatalog,
    load_partner_catalog,
)
from red_leaf_town.rewards import serialize_reward, validate_reward_references
from red_leaf_town.story_assets import (
    DEFAULT_STORY_ASSET_PATH,
    DEFAULT_STORY_LAYOUT,
    StoryAssetCatalog,
    load_story_asset_catalog,
)
from red_leaf_town.story_triggers import (
    StoryContext,
    describe_story_trigger,
    evaluate_story_trigger,
    validate_story_trigger,
)


DEFAULT_STORY_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "data" / "story"
PortraitSlot = Literal["left", "right", "center"]
BackgroundTransition = Literal["fade", "cut"]
PortraitTransition = Literal["fade", "slide", "cut"]


class StepLayout(BaseModel):
    """某一步单独覆盖的立绘站位。比素材默认站位放得开，允许把立绘推到画面中间甚至半出画。"""

    scale: float = Field(default=1.0, ge=0.2, le=4.0)
    offset_x: float = Field(default=0.0, ge=-1.5, le=1.5)
    offset_y: float = Field(default=0.0, ge=-0.8, le=0.8)


class BackgroundStep(BaseModel):
    """把舞台背景换成某张背景图；asset_id 留空表示撤掉背景。"""

    type: Literal["background"]
    asset_id: str = ""
    transition: BackgroundTransition = "fade"
    duration: float = Field(default=0.45, ge=0.0, le=3.0)


class PortraitStep(BaseModel):
    """在对话框旁边显示或收起一张立绘。"""

    type: Literal["portrait"]
    slot: PortraitSlot = "left"
    visible: bool = True
    asset_id: str = ""
    partner_id: str = ""
    breakthrough: int = Field(default=0, ge=0, le=2)
    transition: PortraitTransition = "fade"
    duration: float = Field(default=0.28, ge=0.0, le=3.0)
    flip: bool = False
    layout: StepLayout | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if not self.visible:
            return self
        if bool(self.asset_id) == bool(self.partner_id):
            raise ValueError("a visible portrait step needs exactly one of asset_id or partner_id")
        return self


class DialogueStep(BaseModel):
    """一句对话；speaker 留空表示旁白。"""

    type: Literal["dialogue"]
    speaker: str = Field(default="", max_length=32)
    text: str = Field(min_length=1, max_length=500)
    focus: Literal["left", "right", "none"] = "none"


StoryStep = Annotated[BackgroundStep | PortraitStep | DialogueStep, Field(discriminator="type")]


class StoryTrigger(BaseModel):
    hook: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    repeatable: bool = False

    @model_validator(mode="after")
    def validate_hook(self):
        validate_story_trigger(self.hook, self.params)
        return self

    @property
    def description(self) -> str:
        return describe_story_trigger(self.hook, self.params)


class StoryScript(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=64)
    trigger: StoryTrigger
    steps: list[StoryStep] = Field(min_length=1, max_length=200)
    priority: int = Field(default=0, ge=-100, le=100)
    rewards: RewardDefinition = Field(default_factory=RewardDefinition)

    @model_validator(mode="after")
    def validate_script(self):
        if not any(step.type == "dialogue" for step in self.steps):
            raise ValueError("a story script must contain at least one dialogue step")
        if self.trigger.repeatable and not self.rewards.empty:
            raise ValueError("a repeatable story cannot carry rewards")
        return self

    @property
    def mode(self) -> Literal["stage", "inline"]:
        """带背景的剧本走全屏舞台，纯对话的剧本就地插话。"""
        return "stage" if any(step.type == "background" and step.asset_id for step in self.steps) else "inline"

    @property
    def asset_ids(self) -> set[str]:
        return {
            step.asset_id
            for step in self.steps
            if step.type in ("background", "portrait") and step.asset_id
        }

    @property
    def partner_ids(self) -> set[str]:
        return {step.partner_id for step in self.steps if step.type == "portrait" and step.partner_id}


class StoryCatalog(BaseModel):
    scripts: list[StoryScript] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [script.id for script in self.scripts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate story script id")
        return self

    @property
    def script_map(self) -> dict[str, StoryScript]:
        return {script.id: script for script in self.scripts}

    def matching(self, context: StoryContext, seen_ids: set[str]) -> list[StoryScript]:
        matched = [
            script
            for script in self.scripts
            if (script.trigger.repeatable or script.id not in seen_ids)
            and evaluate_story_trigger(context, script.trigger.hook, script.trigger.params)
        ]
        matched.sort(key=lambda script: (-script.priority, script.id))
        return matched


def validate_story_references(
    catalog: StoryCatalog,
    assets: StoryAssetCatalog,
    partners: PartnerCatalog,
    content: GameContent | None = None,
) -> None:
    content = content if content is not None else load_content()
    asset_map = assets.asset_map
    partner_map = partners.partner_map
    for script in catalog.scripts:
        validate_reward_references(script.rewards, content, partners, f"story {script.id}")
        unknown_assets = script.asset_ids - set(asset_map)
        if unknown_assets:
            raise ValueError(f"story {script.id} references unknown assets: {', '.join(sorted(unknown_assets))}")
        unknown_partners = script.partner_ids - set(partner_map)
        if unknown_partners:
            raise ValueError(f"story {script.id} references unknown partners: {', '.join(sorted(unknown_partners))}")
        for step in script.steps:
            if step.type == "background" and step.asset_id and asset_map[step.asset_id].kind != "background":
                raise ValueError(f"story {script.id} uses a non-background asset as background")
            if step.type == "portrait" and step.asset_id and asset_map[step.asset_id].kind != "portrait":
                raise ValueError(f"story {script.id} uses a non-portrait asset as a portrait")


@lru_cache(maxsize=8)
def load_story_catalog(
    directory: str | Path = DEFAULT_STORY_SCRIPT_DIR,
    asset_path: str | Path = DEFAULT_STORY_ASSET_PATH,
    partner_path: str | Path = DEFAULT_PARTNER_CONTENT_PATH,
    content_path: str | Path = DEFAULT_CONTENT_PATH,
) -> StoryCatalog:
    script_dir = Path(directory)
    scripts: list[StoryScript] = []
    if script_dir.is_dir():
        for entry in sorted(script_dir.glob("*.json")):
            payload = json.loads(entry.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                try:
                    scripts.append(StoryScript.model_validate(record))
                except Exception as exc:
                    raise ValueError(f"invalid story script in {entry.name}: {exc}") from exc
    catalog = StoryCatalog(scripts=scripts)
    validate_story_references(
        catalog,
        load_story_asset_catalog(asset_path),
        load_partner_catalog(partner_path),
        load_content(content_path),
    )
    return catalog


def serialize_step(step, assets: StoryAssetCatalog, partners: PartnerCatalog) -> dict:
    payload = step.model_dump()
    if step.type == "background":
        payload["asset"] = _serialize_asset(assets.asset_map.get(step.asset_id)) if step.asset_id else None
        return payload
    if step.type != "portrait":
        return payload
    payload["asset"] = None
    if not step.visible:
        return payload
    if step.asset_id:
        payload["asset"] = _serialize_asset(assets.asset_map.get(step.asset_id))
        return payload
    partner = partners.partner_map.get(step.partner_id)
    artwork = partner.artwork_for(step.breakthrough) if partner else None
    if artwork:
        payload["asset"] = {
            "id": f"partner:{partner.id}:{step.breakthrough}",
            "name": partner.name,
            "asset_key": artwork.asset_key,
            "width": artwork.width,
            "height": artwork.height,
            "layouts": {
                "inline": DEFAULT_STORY_LAYOUT.model_dump(),
                "stage": DEFAULT_STORY_LAYOUT.model_dump(),
            },
        }
    return payload


def serialize_script(
    script: StoryScript,
    assets: StoryAssetCatalog,
    partners: PartnerCatalog,
    content: GameContent | None = None,
) -> dict:
    content = content if content is not None else load_content()
    return {
        "id": script.id,
        "title": script.title,
        "mode": script.mode,
        "priority": script.priority,
        "repeatable": script.trigger.repeatable,
        "trigger_description": script.trigger.description,
        "rewards": serialize_reward(script.rewards, content, partners),
        "steps": [serialize_step(step, assets, partners) for step in script.steps],
    }


def _serialize_asset(asset) -> dict | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "name": asset.name,
        "asset_key": asset.asset_key,
        "width": asset.width,
        "height": asset.height,
        "layouts": {
            "inline": asset.inline_layout.model_dump(),
            "stage": asset.stage_layout.model_dump(),
        },
    }
