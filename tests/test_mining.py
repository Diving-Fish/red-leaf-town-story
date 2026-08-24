from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


def partner(partner_id: str, industry: str) -> PartnerDefinition:
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": partner_id,
        "rarity": 4,
        "growth_curve": "linear",
        "tendencies": [{"industry": industry, "level_1": 55, "level_60": 180}],
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def mining_game():
    content = load_content().model_copy(deep=True)
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    catalog = PartnerCatalog(partners=[partner("miner", "mining"), partner("farmer", "farming")])
    service = GameService(
        content,
        repository,
        clock=clock,
        rng=random.Random(16),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("mining-sub", "矿山居民")
    service.admin_grant_partner(player.player_id, "miner")
    service.admin_grant_partner(player.player_id, "farmer")
    return service, repository, clock, player


def reach_level_two(repository, player_id: str):
    repository.update(player_id, lambda state: setattr(state, "experience", 20))


def test_mining_unlocks_at_level_two_and_player_can_mine_alone(mining_game):
    service, repository, clock, player = mining_game
    level_one = service.snapshot_by_sub("mining-sub")
    assert level_one["mining_sites"] == []
    assert level_one["next_mining_site_level"] == 2

    reach_level_two(repository, player.player_id)
    state = service.snapshot_by_sub("mining-sub")
    assert [site["site_id"] for site in state["mining_sites"]] == ["copper_foothill"]
    started = service.start_mining("mining-sub", "copper_foothill", "mine_red_copper")
    task = started["state"]["mining_sites"][0]["task_snapshot"]
    assert task["industry"] == "mining"
    assert task["assigned_partner_ids"] == []
    assert task["quality_parameters"]["ability"] == 0

    service.content.mining_task_map["mine_red_copper"].yield_min = 99
    service.content.mining_task_map["mine_red_copper"].yield_max = 99
    clock.advance(task["final_duration"])
    first_results = service.snapshot_by_sub("mining-sub")["mining_sites"][0]["task_results"]
    second_results = service.snapshot_by_sub("mining-sub")["mining_sites"][0]["task_results"]
    assert first_results == second_results
    assert task["yield_min"] <= sum(entry["quantity"] for entry in first_results) <= task["yield_max"]
    assert all(1 <= entry["quality"] <= 4 for entry in first_results)
    assert [entry["item_id"] for entry in first_results] == ["red_copper_ore"] * len(first_results)

    collected = service.collect_mining("mining-sub", "copper_foothill")
    assert collected["result"]["drops"] == first_results
    inventory = repository.get(player.player_id).inventory
    for entry in first_results:
        assert inventory["red_copper_ore"][entry["quality"]] == entry["quantity"]
    assert collected["state"]["mining_sites"][0]["empty"] is True


def test_optional_mining_partner_contributes_locks_and_reports_assignment(mining_game):
    service, repository, _, player = mining_game
    reach_level_two(repository, player.player_id)
    service.snapshot_by_sub("mining-sub")

    with pytest.raises(GameError, match="没有矿产倾向"):
        service.assign_mining_partner("mining-sub", "copper_foothill", "farmer")

    assigned = service.assign_mining_partner("mining-sub", "copper_foothill", "miner")
    miner = next(entry for entry in assigned["state"]["partners"] if entry["partner_id"] == "miner")
    assert miner["assigned_mining_site_id"] == "copper_foothill"
    started = service.start_mining("mining-sub", "copper_foothill", "mine_red_copper")
    task = started["state"]["mining_sites"][0]["task_snapshot"]
    assert task["partner_snapshots"][0]["ability"] > 0
    assert task["quality_parameters"]["ability"] == task["total_ability"]
    assert next(entry for entry in started["state"]["partners"] if entry["partner_id"] == "miner")["locked"] is True

    with pytest.raises(GameError, match="暂时不能移动"):
        service.assign_partner("mining-sub", 0, "miner")
