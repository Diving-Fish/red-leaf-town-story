from __future__ import annotations

import pytest

from red_leaf_town.application import GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.domain.economy import add_item
from red_leaf_town.domain.quality import quality_probabilities, roll_quality
from red_leaf_town.infrastructure import InMemoryPlayerRepository


class FixedRandom:
    def __init__(self, draw: float):
        self.draw = draw

    def randint(self, lower: int, upper: int) -> int:
        return lower

    def random(self) -> float:
        return self.draw


def test_quality_probabilities_are_exact_and_miracle_is_gated():
    without_miracle = quality_probabilities(100, [40, 80, 140, 220], 15, 0.003, False)
    with_miracle = quality_probabilities(1000, [40, 80, 140, 220], 15, 0.003, True)

    assert sum(without_miracle) == pytest.approx(1)
    assert all(probability >= 0 for probability in without_miracle)
    assert without_miracle[4] == 0
    assert sum(with_miracle) == pytest.approx(1)
    assert 0 < with_miracle[4] <= 0.003


def test_quality_roll_uses_one_draw_across_five_exact_buckets():
    probabilities = [0.1, 0.2, 0.3, 0.25, 0.15]
    assert roll_quality(FixedRandom(0.00), probabilities) == 1
    assert roll_quality(FixedRandom(0.10), probabilities) == 2
    assert roll_quality(FixedRandom(0.31), probabilities) == 3
    assert roll_quality(FixedRandom(0.61), probabilities) == 4
    assert roll_quality(FixedRandom(0.90), probabilities) == 5


def test_flat_legacy_inventory_migrates_and_produce_becomes_normal():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    player = PlayerState.model_validate({
        "schema_version": 4,
        "player_id": "legacy-quality",
        "oauth_sub": "legacy-quality-sub",
        "display_name": "旧仓库居民",
        "stamina_updated_at": 1,
        "inventory": {"carrot_seed": 2, "carrot": 3},
        "created_at": 1,
        "updated_at": 1,
    })
    assert player.schema_version == 8
    assert player.inventory == {"carrot_seed": {0: 2}, "carrot": {0: 3}}
    repository.players[player.player_id] = player
    repository.oauth_index[player.oauth_sub] = player.player_id

    state = GameService(content, repository, clock=lambda: 1).snapshot_by_sub(player.oauth_sub)
    inventory = {entry["inventory_key"]: entry for entry in state["inventory"]}
    assert inventory["carrot_seed:0"]["quality"] is None
    assert inventory["carrot:1"]["quality_name"] == "普通"
    assert repository.get(player.player_id).inventory["carrot"] == {1: 3}


def test_task_freezes_quality_probabilities_and_harvest_stacks_one_quality():
    content = load_content().model_copy(deep=True)
    content.crop_map["carrot"].quality.thresholds = [-100, -50, 0, 50]
    content.crop_map["carrot"].quality.width = 1
    repository = InMemoryPlayerRepository(content)
    service = GameService(content, repository, clock=lambda: 100, rng=FixedRandom(0.75))
    player = service.ensure_player("quality-sub", "品质居民")
    service.buy("quality-sub", "carrot_seed", 1)
    planted = service.plant("quality-sub", 0, "carrot")
    frozen = planted["state"]["plots"][0]["task_snapshot"]["quality_parameters"]["probabilities"]
    assert frozen[2] == pytest.approx(0.5)
    assert frozen[3] == pytest.approx(0.5)

    repository.update(player.player_id, lambda state: setattr(state.plots[0], "ready_at", 100))
    content.crop_map["carrot"].quality.thresholds = [100, 200, 300, 400]
    first_read = service.snapshot_by_sub("quality-sub")["plots"][0]["task_result"]
    second_read = service.snapshot_by_sub("quality-sub")["plots"][0]["task_result"]
    assert first_read == second_read
    assert first_read["quality"] == 4
    harvested = service.harvest("quality-sub", 0)
    assert harvested["result"]["quality"] == 4
    assert harvested["result"]["quality_name"] == "臻品"
    assert repository.get(player.player_id).inventory["carrot"] == {4: 2}


def test_quality_sale_uses_grade_multiplier_and_exact_inventory_bucket():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    service = GameService(content, repository, clock=lambda: 100)
    player = service.ensure_player("sale-sub", "商人")
    repository.update(player.player_id, lambda state: add_item(state, "carrot", 3, 3))

    sold = service.sell("sale-sub", "carrot", 2, 3)
    assert sold["result"]["unit_price"] == 8
    assert sold["result"]["coins"] == 16
    assert sold["state"]["player"]["coins"] == 96
    assert repository.get(player.player_id).inventory["carrot"] == {3: 1}
