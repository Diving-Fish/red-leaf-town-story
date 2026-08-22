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
