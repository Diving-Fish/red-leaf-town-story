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
    assert content.gathering_task_map["collect_maple_wood"].outputs[0].item_id == "maple_wood"
    assert content.item_map["maple_wood"].has_quality is True
    assert content.talent_map["gathering_roster_1"].partner_capacity_bonus == 1
    assert content.recipe_map["saw_maple_plank"].unlock_condition.hook == "player_level"
    assert content.industries["mining"].collaborator_slots == 1
    assert content.mining_site_map["copper_foothill"].min_level == 2
    assert content.mining_task_map["mine_red_copper"].produce_item_id == "red_copper_ore"
    assert content.item_map["red_copper_ore"].has_quality is True


def test_gathering_tasks_have_frozen_multi_drop_pools_and_eight_hour_floor():
    content = load_content()
    forest = content.gathering_task_map["collect_maple_wood"]
    meadow = content.gathering_task_map["collect_autumn_herb"]

    assert forest.stamina_cost == meadow.stamina_cost == 0
    assert forest.minimum_duration_seconds == meadow.minimum_duration_seconds == 8 * 3600
    assert [output.item_id for output in forest.outputs] == [
        "maple_wood",
        "woodland_mushroom",
        "maple_resin",
        "amber_beeswax",
    ]
    assert [output.item_id for output in meadow.outputs] == [
        "tough_fodder",
        "autumn_herb",
        "morning_dew_flower",
        "silver_star_moss",
    ]
    assert [(output.chance, output.quantity_min, output.quantity_max) for output in forest.outputs] == [
        (1, 6, 9),
        (0.75, 2, 4),
        (0.4, 1, 3),
        (0.15, 1, 2),
    ]
    assert [(output.chance, output.quantity_min, output.quantity_max) for output in meadow.outputs] == [
        (1, 7, 11),
        (0.8, 3, 5),
        (0.35, 1, 3),
        (0.1, 1, 1),
    ]
    assert {output.item_id: content.item_map[output.item_id].sell_price for output in [*forest.outputs, *meadow.outputs]} == {
        "maple_wood": 6,
        "woodland_mushroom": 7,
        "maple_resin": 10,
        "amber_beeswax": 16,
        "tough_fodder": 5,
        "autumn_herb": 10,
        "morning_dew_flower": 14,
        "silver_star_moss": 30,
    }
    assert forest.quality.thresholds == [25, 55, 90, 210]
    assert meadow.quality.thresholds == [35, 65, 100, 230]
    assert forest.outputs[0].chance == meadow.outputs[0].chance == 1
    assert all(content.item_map[output.item_id].has_quality for task in (forest, meadow) for output in task.outputs)


def test_gathering_pool_requires_unique_items_and_a_guaranteed_drop():
    payload = load_content().model_dump()
    payload["gathering_tasks"][0]["outputs"][0]["chance"] = 0.5
    with pytest.raises(ValidationError, match="guaranteed"):
        GameContent.model_validate(payload)

    payload = load_content().model_dump()
    payload["gathering_tasks"][0]["outputs"][1]["item_id"] = "maple_wood"
    with pytest.raises(ValidationError, match="unique"):
        GameContent.model_validate(payload)


def test_crop_roster_separates_tutorial_and_regular_economy():
    content = load_content()
    tutorial = content.crop_map["orange_berry"]
    regular_ids = ["carrot", "potato", "wheat", "pumpkin"]
    regular = [content.crop_map[crop_id] for crop_id in regular_ids]

    assert tutorial.growth_seconds == 30
    assert tutorial.stamina_cost == 0
    assert content.item_map[tutorial.produce_item_id].sell_price == 300
    assert tutorial.seed_item_id not in {entry.item_id for entry in content.shop}
    assert [crop.min_level for crop in regular] == [1, 2, 3, 4]
    assert all(crop.stamina_cost == 0 for crop in regular)
    assert all(crop.growth_seconds >= 3 * 3600 for crop in regular)
    assert [crop.quality.thresholds for crop in regular] == [
        [0, 20, 40, 140],
        [10, 30, 50, 170],
        [25, 50, 75, 200],
        [45, 70, 95, 230],
    ]


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


def test_every_recipe_requires_an_explicit_unlock_condition():
    payload = load_content().model_dump()
    payload["recipes"][0].pop("unlock_condition")
    with pytest.raises(ValidationError, match="unlock_condition"):
        GameContent.model_validate(payload)


def test_unknown_or_invalid_recipe_unlock_hook_is_rejected():
    payload = load_content().model_dump()
    payload["recipes"][0]["unlock_condition"]["hook"] = "implicit_default"
    with pytest.raises(ValidationError, match="unknown unlock hook"):
        GameContent.model_validate(payload)

    payload = load_content().model_dump()
    payload["recipes"][0]["unlock_condition"]["params"] = {}
    with pytest.raises(ValidationError, match="positive integer level"):
        GameContent.model_validate(payload)


def test_mining_task_requires_known_site_and_quality_item():
    payload = load_content().model_dump()
    payload["mining_tasks"][0]["site_id"] = "missing_mine"
    with pytest.raises(ValidationError, match="unknown site"):
        GameContent.model_validate(payload)

    payload = load_content().model_dump()
    payload["mining_tasks"][0]["produce_item_id"] = "carrot_seed"
    with pytest.raises(ValidationError, match="output must support quality"):
        GameContent.model_validate(payload)
