from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


def partner(partner_id: str, industry: str = "gathering") -> PartnerDefinition:
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": partner_id,
        "rarity": 3,
        "growth_curve": "linear",
        "tendencies": [{"industry": industry, "level_1": 40, "level_60": 120}],
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def gathering_game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    catalog = PartnerCatalog(partners=[partner("gather_one"), partner("gather_two"), partner("farm_only", "farming")])
    service = GameService(
        content,
        repository,
        clock=clock,
        rng=random.Random(9),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("gather-sub", "采集居民")
    for partner_id in ("gather_one", "gather_two", "farm_only"):
        service.admin_grant_partner(player.player_id, partner_id)
    return service, repository, clock, player


def test_gathering_requires_partner_and_locks_it_until_ready(gathering_game):
    service, repository, clock, player = gathering_game
    state = service.snapshot_by_sub("gather-sub")
    assert [site["site_id"] for site in state["gathering_sites"]] == ["maple_forest"]

    with pytest.raises(GameError, match="必须先派"):
        service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    with pytest.raises(GameError, match="没有采集倾向"):
        service.assign_gathering_partner("gather-sub", "maple_forest", "farm_only")

    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    site = started["state"]["gathering_sites"][0]
    assert site["task_snapshot"]["industry"] == "gathering"
    assert site["task_snapshot"]["partner_snapshots"][0]["ability"] == 40
    assert site["task_snapshot"]["quality_parameters"]["ability"] == 40
    assert site["assignment_locked"] is True
    assert next(entry for entry in started["state"]["partners"] if entry["partner_id"] == "gather_one")["locked"] is True

    with pytest.raises(GameError, match="不能调整"):
        service.assign_gathering_partner("gather-sub", "maple_forest", "")
    with pytest.raises(GameError, match="暂时不能移动"):
        service.assign_partner("gather-sub", 0, "gather_one")

    clock.advance(site["task_snapshot"]["final_duration"])
    first_result = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_result"]
    second_result = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_result"]
    assert first_result == second_result
    assert 1 <= first_result["quality"] <= 4
    collected = service.collect_gathering("gather-sub", "maple_forest")
    assert collected["result"]["quality"] == first_result["quality"]
    assert repository.get(player.player_id).inventory["maple_wood"][first_result["quality"]] == first_result["quantity"]
    assert collected["state"]["gathering_sites"][0]["empty"] is True


def test_gathering_capacity_is_derived_from_talent_tree(gathering_game):
    service, repository, _, player = gathering_game
    service.snapshot_by_sub("gather-sub")
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")

    repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    level_two = service.snapshot_by_sub("gather-sub")
    assert level_two["player"]["level"] == 2
    assert level_two["talents"]["available_points"] == 1
    assert level_two["industry_rules"]["gathering"]["partner_capacity"] == 1
    with pytest.raises(GameError, match="编制已满"):
        service.assign_gathering_partner("gather-sub", "dew_meadow", "gather_two")

    unlocked = service.unlock_talent("gather-sub", "gathering_roster_1")
    assert unlocked["state"]["talents"]["available_points"] == 0
    assert unlocked["state"]["industry_rules"]["gathering"]["partner_capacity"] == 2
    assigned = service.assign_gathering_partner("gather-sub", "dew_meadow", "gather_two")
    assert len([site for site in assigned["state"]["gathering_sites"] if site["assigned_partner_ids"]]) == 2


def test_quality_gathering_material_can_be_sold_by_exact_grade(gathering_game):
    service, repository, _, player = gathering_game
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {3: 2}}))
    sold = service.sell("gather-sub", "maple_wood", 1, 3)
    assert sold["result"]["quality_name"] == "上品"
    assert sold["result"]["unit_price"] == 11


def test_player_rejects_partner_assigned_across_farm_and_gathering():
    with pytest.raises(ValidationError, match="more than one production slot"):
        PlayerState.model_validate({
            "player_id": "cross-industry",
            "oauth_sub": "cross-industry-sub",
            "display_name": "重复派驻",
            "stamina_updated_at": 1,
            "created_at": 1,
            "updated_at": 1,
            "owned_partners": [{"partner_id": "worker", "acquired_at": 1}],
            "plots": [{"slot": 0, "assigned_partner_ids": ["worker"]}],
            "gathering_sites": [{"site_id": "maple_forest", "assigned_partner_ids": ["worker"]}],
        })
