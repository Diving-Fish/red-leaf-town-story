from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from red_leaf_town.content import GameContent, load_content


def test_default_content_is_consistent():
    content = load_content()
    assert content.game.title == "红叶镇物语"
    assert content.level_for_xp(0).level == 1
    assert content.level_for_xp(20).level == 2
    assert content.crop_map["carrot"].seed_item_id == "carrot_seed"
    assert content.crop_map["carrot"].time_difficulty > 0
    assert content.industries["farming"].collaborator_slots == 1
    assert content.item_map["carrot"].sell_price > 0
    assert [grade.name for grade in content.quality.grades] == ["普通", "良品", "上品", "臻品", "奇迹"]
    assert content.crop_map["carrot"].quality.thresholds == sorted(content.crop_map["carrot"].quality.thresholds)
    assert content.industries["gathering"].partner_capacity == 1
    assert content.gathering_task_map["collect_maple_wood"].produce_item_id == "maple_wood"
    assert content.item_map["maple_wood"].has_quality is True
    assert content.talent_map["gathering_roster_1"].partner_capacity_bonus == 1


def test_unknown_crop_item_is_rejected():
    payload = load_content().model_dump()
    payload["crops"][0]["seed_item_id"] = "missing_seed"
    with pytest.raises(ValidationError, match="unknown item"):
        GameContent.model_validate(payload)


def test_duplicate_ids_are_rejected():
    payload = json.loads(load_content().model_dump_json())
    payload["items"].append(payload["items"][0])
    with pytest.raises(ValidationError, match="duplicate item"):
        GameContent.model_validate(payload)


def test_non_increasing_quality_thresholds_are_rejected():
    payload = load_content().model_dump()
    payload["crops"][0]["quality"]["thresholds"] = [40, 80, 80, 220]
    with pytest.raises(ValidationError, match="strictly increasing"):
        GameContent.model_validate(payload)
