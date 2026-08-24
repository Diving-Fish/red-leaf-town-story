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


def test_gathering_tasks_have_frozen_weighted_pools_and_eight_hour_floor():
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
    assert [(output.weight, output.quantity_min, output.quantity_max) for output in forest.outputs] == [
        (50, 1, 2),
        (30, 1, 1),
        (15, 1, 1),
        (5, 1, 1),
    ]
    assert [(output.weight, output.quantity_min, output.quantity_max) for output in meadow.outputs] == [
        (50, 1, 2),
        (30, 1, 1),
        (15, 1, 1),
        (5, 1, 1),
    ]
    assert (forest.draws.base_draws, forest.draws.ability_bonus, forest.draws.difficulty) == (6, 1.5, 120)
    assert (meadow.draws.base_draws, meadow.draws.ability_bonus, meadow.draws.difficulty) == (6, 1.5, 120)
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
    assert forest.headline_output.item_id == "maple_wood"
    assert meadow.headline_output.item_id == "tough_fodder"
    assert all(content.item_map[output.item_id].has_quality for task in (forest, meadow) for output in task.outputs)


def test_gathering_pool_requires_positive_weights_and_unique_items():
    payload = load_content().model_dump()
    payload["gathering_tasks"][0]["outputs"][0]["weight"] = 0
    with pytest.raises(ValidationError, match="greater than 0"):
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

    assert tutorial.stamina_cost == 0
    assert tutorial.seed_item_id not in {entry.item_id for entry in content.shop}
    assert all(crop.stamina_cost == 0 for crop in regular)
    assert all(crop.growth_seconds > tutorial.growth_seconds for crop in regular)
    assert all(crop.quality.thresholds == sorted(crop.quality.thresholds) for crop in regular)


def test_crafting_prices_reflect_inputs_and_mining_stamina_value():
    content = load_content()
    mining_values_per_stamina = []
    for task in content.mining_tasks:
        item = content.item_map[task.produce_item_id]
        average_yield = (task.yield_min + task.yield_max) / 2
        mining_values_per_stamina.append(average_yield * item.sell_price / task.stamina_cost)

    minimum_value = min(mining_values_per_stamina)
    maximum_value = max(mining_values_per_stamina)
    assert {
        item_id: content.item_map[item_id].sell_price
        for item_id in ("maple_plank", "herbal_salve", "flour", "pickled_carrot")
    } == {
        "maple_plank": 110,
        "herbal_salve": 120,
        "flour": 130,
        "pickled_carrot": 130,
    }
    for recipe in content.recipes:
        input_value = sum(
            content.item_map[entry.item_id].sell_price * entry.quantity
            for entry in recipe.inputs
        )
        output_value = content.item_map[recipe.produce_item_id].sell_price * recipe.produce_quantity
        added_value_per_stamina = (output_value - input_value) / recipe.stamina_cost
        assert recipe.stamina_cost == 10
        assert minimum_value <= added_value_per_stamina <= maximum_value


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
