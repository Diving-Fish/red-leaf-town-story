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
    # 提示语要用得上的展示字段，缺一个前端就只能显示 item_id。
    assert refunded[0]["trait_name"] == "万物归元"
    assert refunded[0]["item"]["name"] == "枫木"
    assert refunded[0]["quality_name"]
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


def test_forging_a_weapon_lands_in_the_quality_free_slot(crafting_game):
    """装备不进五档品质：加工出来的武器必须落在 0 号格，能直接带进副本。"""
    service, repository, clock, player = crafting_game
    level_ten = next(entry.total_xp for entry in service.content.levels if entry.level == 10)
    reach_level(repository, player.player_id, level_ten)
    service.snapshot_by_sub("craft-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"red_copper_ore": {1: 12, 3: 10}}))

    started = service.start_crafting("craft-sub", "town_workbench", "forge_red_copper_greatsword")
    task = started["state"]["crafting_stations"][0]["task_snapshot"]

    # 20 个矿从最低品质开始扣，臻品留在仓库里。
    assert task["consumed_inputs"] == [
        {"item_id": "red_copper_ore", "quality": 1, "quantity": 12},
        {"item_id": "red_copper_ore", "quality": 3, "quantity": 8},
    ]
    assert repository.get(player.player_id).inventory["red_copper_ore"] == {3: 2}
    assert started["state"]["player"]["stamina"] == service.snapshot_by_sub("craft-sub")["player"]["stamina"]

    clock.advance(task["final_duration"])
    results = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]["task_results"]

    assert [(entry["item_id"], entry["quantity"], entry["quality"]) for entry in results] == [
        ("red_copper_greatsword", 1, 0),
    ]
    assert results[0]["quality_name"] is None

    collected = service.collect_crafting("craft-sub", "town_workbench")

    assert collected["result"]["item_id"] == "red_copper_greatsword"
    assert repository.get(player.player_id).inventory["red_copper_greatsword"] == {0: 1}


def test_weapon_recipes_unlock_at_the_level_the_meadow_opens(crafting_game):
    service, repository, _, player = crafting_game
    reach_level(repository, player.player_id, 60)
    station = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]
    recipes = {recipe["id"]: recipe for recipe in station["recipes"]}

    assert recipes["forge_moon_silver_dagger"]["unlocked"] is False
    assert recipes["forge_moon_silver_dagger"]["unlock_description"] == "居民等级达到 10 级"
    with pytest.raises(GameError, match="配方尚未解锁"):
        service.start_crafting("craft-sub", "town_workbench", "bind_maple_flame_tome")

    level_ten = next(entry.total_xp for entry in service.content.levels if entry.level == 10)
    reach_level(repository, player.player_id, level_ten)
    unlocked = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]["recipes"]

    assert all(
        recipe["unlocked"] is True
        for recipe in unlocked
        if recipe["id"].startswith(("forge_", "bind_"))
    )


def test_forging_costs_five_stamina_and_refuses_when_short(crafting_game):
    service, repository, _, player = crafting_game
    level_ten = next(entry.total_xp for entry in service.content.levels if entry.level == 10)
    reach_level(repository, player.player_id, level_ten)
    service.snapshot_by_sub("craft-sub")

    def prepare(state):
        add_item(state, "moon_silver_ore", 10, 1)
        state.stamina = 4

    repository.update(player.player_id, prepare)
    with pytest.raises(GameError, match="体力"):
        service.start_crafting("craft-sub", "town_workbench", "forge_moon_silver_dagger")
    # 开工失败不能吃掉原料。
    assert repository.get(player.player_id).inventory["moon_silver_ore"] == {1: 10}

    repository.update(player.player_id, lambda state: setattr(state, "stamina", 5))
    before = service.snapshot_by_sub("craft-sub")["player"]["stamina"]
    started = service.start_crafting("craft-sub", "town_workbench", "forge_moon_silver_dagger")

    assert started["state"]["player"]["stamina"] == before - 5
    assert not repository.get(player.player_id).inventory.get("moon_silver_ore")


def test_batch_crafting_scales_costs_results_and_duration(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 3, 3: 3}}))
    before = service.snapshot_by_sub("craft-sub")["player"]["stamina"]
    recipe = service.content.recipe_map["saw_maple_plank"]
    started = service.start_crafting("craft-sub", "town_workbench", recipe.id, quantity=3)
    task = started["state"]["crafting_stations"][0]["task_snapshot"]
    assert started["state"]["player"]["stamina"] == before - recipe.stamina_cost * 3
    assert sum(entry["quantity"] for entry in task["consumed_inputs"]) == 2
    assert task["base_duration"] == recipe.duration_seconds
    assert recipe.produce_quantity == 1
    clock.advance(task["final_duration"] * 3)
    results = service.collect_crafting("craft-sub", "town_workbench")["result"]["drops"]
    assert sum(entry["quantity"] for entry in results) == 3


@pytest.mark.parametrize("quantity", [0, -1, 100, 1.5, True, "3", None])
def test_batch_crafting_rejects_invalid_quantity(crafting_game, quantity):
    service, _, _, _ = crafting_game
    with pytest.raises(GameError, match="加工次数"):
        service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank", quantity=quantity)


@pytest.mark.parametrize("stamina,wood", [(1, 6), (100, 5)])
def test_batch_crafting_failure_preserves_resources(crafting_game, stamina, wood):
    service, repository, _, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")

    def prepare(state):
        state.stamina = stamina
        state.inventory["maple_wood"] = {1: wood}

    repository.update(player.player_id, prepare)
    with pytest.raises(GameError):
        service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank", quantity=3)
    state = repository.get(player.player_id)
    assert state.stamina == stamina
    assert state.inventory["maple_wood"] == {1: wood}
    assert state.crafting_stations[0].empty


def prepare_queue(crafting_game, quantity=3, item_id="", item_count=0):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")

    def prepare(state):
        state.inventory["maple_wood"] = {1: quantity, 3: quantity}
        state.stamina = 250
        if item_id:
            state.task_items[item_id] = item_count

    repository.update(player.player_id, prepare)
    return service.start_crafting(
        "craft-sub", "town_workbench", "saw_maple_plank", item_id, quantity=quantity,
    )


@pytest.mark.parametrize("owned", [0, 1, 2, 3, 5])
def test_queue_items_apply_once_to_first_available_tasks(crafting_game, owned):
    service, repository, clock, player = crafting_game
    started = prepare_queue(crafting_game, item_id="harvest_knot", item_count=owned)
    station = repository.get(player.player_id).crafting_stations[0]
    tasks = [station.task_snapshot, *station.queued_tasks]
    assert [task.yield_min for task in tasks] == [2 if index < owned else 1 for index in range(3)]
    assert repository.get(player.player_id).task_items.get("harvest_knot", 0) == max(0, owned - 3)
    assert started["result"]["task_items_reserved"] == min(owned, 3)
    clock.advance(sum(task.final_duration for task in tasks))
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["quantity"] == 3 + min(owned, 3)
    assert collected["result"]["completed_count"] == 3
    assert collected["state"]["crafting_stations"][0]["empty"]


def test_queue_partial_collection_continues_without_duplicate_rewards(crafting_game):
    service, repository, clock, player = crafting_game
    started = prepare_queue(crafting_game)
    first = started["state"]["crafting_stations"][0]["task_snapshot"]
    clock.advance(first["final_duration"])
    state = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]
    assert state["completed_count"] == 1
    assert state["queued_count"] == 1
    assert state["task_snapshot"]["started_at"] == first["ready_at"]
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["quantity"] == 1
    assert collected["state"]["crafting_stations"][0]["collected_count"] == 1
    assert not collected["state"]["crafting_stations"][0]["empty"]
    with pytest.raises(GameError, match="还没有完成"):
        service.collect_crafting("craft-sub", "town_workbench")
    clock.advance(first["final_duration"] * 2)
    rest = service.collect_crafting("craft-sub", "town_workbench")
    assert rest["result"]["quantity"] == 2
    assert sum(repository.get(player.player_id).inventory["maple_plank"].values()) == 3


def test_queue_cancel_refunds_only_pending_and_keeps_completed(crafting_game):
    service, repository, clock, player = crafting_game
    started = prepare_queue(crafting_game, quantity=4, item_id="harvest_knot", item_count=4)
    first = started["state"]["crafting_stations"][0]["task_snapshot"]
    clock.advance(first["final_duration"])
    cancelled = service.cancel_task("craft-sub", "crafting", "town_workbench")
    assert cancelled["result"]["refunded_stamina"] == 4
    assert cancelled["result"]["refunded_task_items"] == {"harvest_knot": 2}
    assert sum(entry["quantity"] for entry in cancelled["result"]["refunded_inputs"]) == 4
    assert repository.get(player.player_id).inventory["maple_wood"] == {3: 4}
    station = cancelled["state"]["crafting_stations"][0]
    assert station["completed_count"] == 1 and station["ready"]
    assert station["queued_count"] == 0
    with pytest.raises(GameError):
        service.cancel_task("craft-sub", "crafting", "town_workbench")
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["quantity"] == 2
    assert collected["state"]["crafting_stations"][0]["empty"]


def test_queue_duration_items_and_active_acceleration_are_per_task(crafting_game):
    service, repository, clock, player = crafting_game
    prepare_queue(crafting_game, item_id="maple_wind_whistle", item_count=1)
    station = repository.get(player.player_id).crafting_stations[0]
    assert station.task_snapshot.final_duration < station.queued_tasks[0].final_duration
    second_duration = station.queued_tasks[0].final_duration
    repository.update(player.player_id, lambda state: state.task_items.update({"night_lamp_tea": 1}))
    clock.advance(1)
    sped = service.use_active_task_item("craft-sub", "crafting", "town_workbench", "night_lamp_tea")
    station = sped["state"]["crafting_stations"][0]
    assert station["completed_count"] == 1
    assert station["task_snapshot"]["started_at"] == clock.now
    assert station["task_snapshot"]["final_duration"] == second_duration
    clock.advance(second_duration)
    station = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]
    assert station["completed_count"] == 2
    assert station["task_snapshot"]["started_at"] == clock.now


def test_queue_freezes_independent_quality_and_survives_serialization(crafting_game):
    from red_leaf_town.domain import PlayerState
    service, repository, clock, player = crafting_game
    prepare_queue(crafting_game)

    def freeze(state):
        station = state.crafting_stations[0]
        for index, task in enumerate([station.task_snapshot, *station.queued_tasks]):
            task.quality_parameters.probabilities = [int(quality == index) for quality in range(5)]

    repository.update(player.player_id, freeze)
    restored = PlayerState.model_validate_json(repository.get(player.player_id).model_dump_json())
    repository.players[player.player_id] = restored
    station = restored.crafting_stations[0]
    clock.advance(sum(task.final_duration for task in [station.task_snapshot, *station.queued_tasks]))
    result = service.collect_crafting("craft-sub", "town_workbench")["result"]
    assert [(drop["quality"], drop["quantity"]) for drop in result["drops"]] == [(1, 1), (2, 1), (3, 1)]


def test_queue_failure_rolls_back_reserved_special_items(crafting_game):
    service, repository, _, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")

    def prepare(state):
        state.inventory["maple_wood"] = {1: 3}
        state.task_items["harvest_knot"] = 3

    repository.update(player.player_id, prepare)
    before = repository.get(player.player_id)
    with pytest.raises(GameError):
        service.start_crafting("craft-sub", "town_workbench", "saw_maple_plank", "harvest_knot", quantity=3)
    after = repository.get(player.player_id)
    assert after.task_items == before.task_items
    assert after.inventory == before.inventory
    assert after.stamina == before.stamina


def test_queue_reserves_partner_for_later_tasks_without_release_item(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")
    started = prepare_queue(crafting_game, item_id="handover_order", item_count=1)
    station = started["state"]["crafting_stations"][0]
    assert station["assignment_locked"]
    with pytest.raises(GameError):
        service.assign_gathering_partner("craft-sub", "maple_forest", "artisan")
    clock.advance(station["queue_remaining_seconds"])
    service.collect_crafting("craft-sub", "town_workbench")
    service.assign_gathering_partner("craft-sub", "maple_forest", "artisan")


def test_queue_rewards_partner_and_refunds_trait_inputs_per_completed_task(crafting_game):
    service, repository, clock, player = crafting_game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("craft-sub")
    service.partner_catalog_loader().partner_map["artisan"].trait_codes = ["primordial_return"]
    service.assign_crafting_partner("craft-sub", "town_workbench", "artisan")
    prepare_queue(crafting_game)

    def force_refunds(state):
        station = state.crafting_stations[0]
        for task in [station.task_snapshot, *station.queued_tasks]:
            for effect in task.applied_effects:
                if effect.get("effect") == "refund_consumed_input":
                    effect["params"]["chance"] = 1.0

    repository.update(player.player_id, force_refunds)
    station = repository.get(player.player_id).crafting_stations[0]
    clock.advance(sum(task.final_duration for task in [station.task_snapshot, *station.queued_tasks]))
    result = service.collect_crafting("craft-sub", "town_workbench")["result"]
    assert len(result["partner_experience"]) == 3
    assert result["experience"] == service.content.recipe_map["saw_maple_plank"].collect_xp * 3
    assert sum(entry["quantity"] for entry in result["refunded_inputs"]) == 6


def test_max_queue_offline_settlement_and_collection(crafting_game):
    service, _, clock, _ = crafting_game
    started = prepare_queue(crafting_game, quantity=99)
    clock.advance(started["state"]["crafting_stations"][0]["queue_remaining_seconds"])
    state = service.snapshot_by_sub("craft-sub")["crafting_stations"][0]
    assert state["completed_count"] == 99
    result = service.collect_crafting("craft-sub", "town_workbench")
    assert result["result"]["completed_count"] == 99
    assert result["result"]["quantity"] == 99
    assert result["state"]["crafting_stations"][0]["empty"]


def test_legacy_task_without_queue_fields_remains_collectible(crafting_game):
    from red_leaf_town.domain import PlayerState
    service, repository, clock, player = crafting_game
    started = prepare_queue(crafting_game, quantity=1)
    payload = repository.get(player.player_id).model_dump()
    station = payload["crafting_stations"][0]
    for key in ("queued_tasks", "completed_tasks", "queue_total", "collected_count"):
        station.pop(key)
    repository.players[player.player_id] = PlayerState.model_validate(payload)
    clock.advance(started["result"]["final_duration"])
    collected = service.collect_crafting("craft-sub", "town_workbench")
    assert collected["result"]["quantity"] == 1
    assert collected["state"]["crafting_stations"][0]["empty"]
