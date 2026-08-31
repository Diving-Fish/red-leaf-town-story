from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.economy import add_item
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


def crafting_partner() -> PartnerDefinition:
    return PartnerDefinition.model_validate({
        "id": "artisan",
        "name": "工匠伙伴",
        "rarity": 4,
        "growth_curve": "linear",
        "tendencies": [
            {"industry": "crafting", "level_1": 50, "level_60": 180},
            {"industry": "gathering", "level_1": 30, "level_60": 120},
        ],
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def crafting_game():
    content = load_content().model_copy(deep=True)
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    catalog = PartnerCatalog(partners=[crafting_partner()])
    service = GameService(
        content,
        repository,
        clock=clock,
        rng=random.Random(12),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("craft-sub", "工坊居民")
    service.admin_grant_partner(player.player_id, "artisan")
    return service, repository, clock, player


def reach_level(repository, player_id: str, experience: int):
    repository.update(player_id, lambda player: setattr(player, "experience", experience))


def test_crafting_station_and_recipes_are_never_implicitly_unlocked(crafting_game):
    service, repository, _, player = crafting_game
    level_one = service.snapshot_by_sub("craft-sub")
    assert level_one["crafting_stations"] == []
    assert level_one["next_crafting_station_level"] == 3

    reach_level(repository, player.player_id, 60)
    level_three = service.snapshot_by_sub("craft-sub")
    station = level_three["crafting_stations"][0]
    recipes = {recipe["id"]: recipe for recipe in station["recipes"]}
    assert recipes["saw_maple_plank"]["unlocked"] is True
    assert recipes["saw_maple_plank"]["unlock_condition"] == {
        "hook": "player_level",
        "params": {"level": 3},
    }
    assert recipes["pickle_carrot"]["unlocked"] is False
    assert recipes["pickle_carrot"]["unlock_description"] == "居民等级达到 4 级"
    with pytest.raises(GameError, match="配方尚未解锁"):
        service.start_crafting("craft-sub", "town_workbench", "pickle_carrot")


def test_crafting_consumes_lowest_quality_inputs_and_freezes_task(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 1, 3: 2}}))

    started = service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    assert task["industry"] == "crafting"
    assert task["assigned_partner_ids"] == []
    assert task["consumed_inputs"] == [
        {"item_id": "maple_wood", "quality": 1, "quantity": 1},
        {"item_id": "maple_wood", "quality": 3, "quantity": 1},
    ]
    assert repository.get(player.player_id).inventory["maple_wood"] == {3: 1}

    service.content.recipe_map["saw_maple_plank"].produce_quantity = 99
    clock.advance(task["final_duration"])
    results = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]["task_results"]
    assert [entry["quantity"] for entry in results] == [1]
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["item_id"] == "maple_plank"
    assert repository.get(player.player_id).inventory["maple_plank"][results[0]["quality"]] == 1


def test_optional_crafting_partner_contributes_and_is_locked(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    repository.update(player.player_id, lambda state: add_item(state, "autumn_herb", 2, 1))
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")
    started = service.start_crafting("craft-sub", "town_workbench", "make_herbal_salve")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    assert task["partner_snapshots"][0]["ability"] > 0
    assert task["quality_parameters"]["ability"] == task["total_ability"]
    assert next(partner for partner in started["state"]["partners"] if partner["partner_id"] == "artisan")["locked"] is True

    with pytest.raises(GameError, match="暂时不能移动"):
        service.assign_gathering_partner("craft-sub", "maple_forest", "artisan")
    clock.advance(task["final_duration"])
    service.snapshot_by_sub("craft-sub")
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["partner_experience"][0]["experience_gained"] == 4


def test_primordial_return_refunds_one_consumed_input_at_collection(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    service.partner_catalog_loader().partner_map["artisan"].trait_codes = ["primordial_return"]
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 2}}))
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")

    started = service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    refund_effects = [
        entry for entry in task["applied_effects"] if entry["effect"] == "refund_consumed_input"
    ]
    assert refund_effects and refund_effects[0]["params"]["chance"] == 0.35
    assert repository.get(player.player_id).inventory.get("maple_wood") is None

    clock.advance(task["final_duration"])
    service.snapshot_by_sub("craft-sub")

    def force_refund(state):
        # 把冻结在快照里的概率抬到必中，让退料这一段有确定的断言。
        for entry in state.crafting_stations[0].task_snapshot.applied_effects:
            if entry.get("effect") == "refund_consumed_input":
                entry["params"]["chance"] = 1.0

    repository.update(player.player_id, force_refund)
    collected = service.collect_crafting("craft-sub", "town_workbench")

    refunded = collected["result"]["refunded_inputs"]
    assert [entry["item_id"] for entry in refunded] == ["maple_wood"]
    assert refunded[0]["trait_code"] == "primordial_return"
    inventory = repository.get(player.player_id).inventory
    assert inventory["maple_wood"][refunded[0]["quality"]] == refunded[0]["quantity"]


def test_input_refund_only_fires_when_the_snapshot_carries_the_effect(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 2}}))

    started = service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank")
    clock.advance(started["state"]["crafting_stations"][0]["task_snapshot"]["final_duration"])
    service.snapshot_by_sub("craft-sub")
    collected = service.collect_crafting("craft-sub", "town_workbench")

    assert collected["result"]["refunded_inputs"] == []
    assert repository.get(player.player_id).inventory.get("maple_wood") is None


def test_input_refund_returns_every_quality_stack_of_the_chosen_material(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    service.partner_catalog_loader().partner_map["artisan"].trait_codes = ["primordial_return"]
    # 混品质背包：枫木会被拆成「普通 1」和「上品 1」两条消耗记录。
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 1, 3: 2}}))
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")

    started = service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    assert task["consumed_inputs"] == [
        {"item_id": "maple_wood", "quality": 1, "quantity": 1},
        {"item_id": "maple_wood", "quality": 3, "quantity": 1},
    ]

    clock.advance(task["final_duration"])
    service.snapshot_by_sub("craft-sub")

    def force_refund(state):
        for entry in state.crafting_stations[0].task_snapshot.applied_effects:
            if entry.get("effect") == "refund_consumed_input":
                entry["params"]["chance"] = 1.0

    repository.update(player.player_id, force_refund)
    collected = service.collect_crafting("craft-sub", "town_workbench")

    # 退的是「枫木」这一种原料的全部消耗量，不是随机挑一条品质记录。
    assert [(entry["quality"], entry["quantity"]) for entry in collected["result"]["refunded_inputs"]] == [(1, 1), (3, 1)]
    assert repository.get(player.player_id).inventory["maple_wood"] == {1: 1, 3: 2}


def test_input_refund_returns_only_one_of_several_materials(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    service.partner_catalog_loader().partner_map["artisan"].trait_codes = ["primordial_return"]
    recipe = service.content.recipe_map["saw_maple_plank"]
    recipe.inputs = [
        entry.model_copy(update={"item_id": "maple_wood", "quantity": 2}) for entry in recipe.inputs
    ] + [recipe.inputs[0].model_copy(update={"item_id": "autumn_herb", "quantity": 2})]
    repository.update(player.player_id, lambda state: state.inventory.update({
        "maple_wood": {1: 2},
        "autumn_herb": {1: 2},
    }))
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")

    started = service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    clock.advance(task["final_duration"])
    service.snapshot_by_sub("craft-sub")

    def force_refund(state):
        for entry in state.crafting_stations[0].task_snapshot.applied_effects:
            if entry.get("effect") == "refund_consumed_input":
                entry["params"]["chance"] = 1.0

    repository.update(player.player_id, force_refund)
    collected = service.collect_crafting("craft-sub", "town_workbench")

    refunded = collected["result"]["refunded_inputs"]
    assert {entry["item_id"] for entry in refunded} != {"maple_wood", "autumn_herb"}
    assert sum(entry["quantity"] for entry in refunded) == 2
    inventory = repository.get(player.player_id).inventory
    returned = {
        item_id: sum(inventory.get(item_id, {}).values())
        for item_id in ("maple_wood", "autumn_herb")
    }
    assert sorted(returned.values()) == [0, 2]
