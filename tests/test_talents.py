from __future__ import annotations

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository


EXPECTED_TALENT_PATHS = {
    "farming": [
        ("farming_roster_1", 2, 1, 0),
        ("farming_ability_1", 4, 0, 10),
        ("farming_roster_2", 6, 1, 0),
        ("farming_ability_2", 8, 0, 10),
    ],
    "gathering": [
        ("gathering_roster_1", 2, 1, 0),
        ("gathering_ability_1", 4, 0, 10),
        ("gathering_roster_2", 6, 1, 0),
        ("gathering_ability_2", 8, 0, 10),
    ],
    "mining": [
        ("mining_ability_1", 2, 0, 10),
        ("mining_roster_1", 4, 1, 0),
        ("mining_ability_2", 6, 0, 10),
        ("mining_ability_3", 8, 0, 10),
    ],
}


@pytest.fixture
def talent_game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    service = GameService(content, repository, clock=lambda: 1_700_000_000)
    player = service.ensure_player("talent-sub", "天赋居民")
    return service, repository, player


def test_industry_talent_paths_have_expected_levels_prerequisites_and_effects():
    content = load_content()

    for industry, expected in EXPECTED_TALENT_PATHS.items():
        nodes = [node for node in content.talents if node.industry == industry]
        assert [
            (node.id, node.min_level, node.partner_capacity_bonus, node.global_ability_bonus)
            for node in nodes
        ] == expected
        assert [node.prerequisites for node in nodes] == [
            [],
            [nodes[0].id],
            [nodes[1].id],
            [nodes[2].id],
        ]


def test_talent_unlock_requires_each_previous_node(talent_game):
    service, repository, player = talent_game
    level_eight_xp = next(entry.total_xp for entry in service.content.levels if entry.level == 8)
    repository.update(player.player_id, lambda state: setattr(state, "experience", level_eight_xp))

    with pytest.raises(GameError, match="前置天赋"):
        service.unlock_talent("talent-sub", "farming_ability_1")

    for node_id, *_ in EXPECTED_TALENT_PATHS["farming"]:
        service.unlock_talent("talent-sub", node_id)

    state = service.snapshot_by_sub("talent-sub")
    assert state["industry_rules"]["farming"]["partner_capacity"] == 3
    assert state["industry_rules"]["farming"]["global_ability_bonus"] == 20
    assert state["industry_rules"]["farming"]["character_base_ability"] == 20


@pytest.mark.parametrize(("industry", "node_ids", "expected_bonus"), [
    ("farming", ["farming_ability_1", "farming_ability_2"], 20),
    ("gathering", ["gathering_ability_1", "gathering_ability_2"], 20),
    ("mining", ["mining_ability_1", "mining_ability_2", "mining_ability_3"], 30),
])
def test_global_ability_talents_contribute_to_production_ability(
    talent_game,
    industry,
    node_ids,
    expected_bonus,
):
    service, repository, player = talent_game
    repository.update(player.player_id, lambda state: setattr(state, "talent_nodes", node_ids))
    updated = repository.get(player.player_id)

    total_ability, character_ability, partners = service._production_ability(updated, [], industry)

    assert total_ability == expected_bonus
    assert character_ability == expected_bonus
    assert partners == []


def test_farming_global_ability_changes_both_speed_and_quality(talent_game):
    service, repository, player = talent_game

    def prepare(state):
        state.talent_nodes = ["farming_ability_1", "farming_ability_2"]
        state.inventory = {"carrot_seed": {0: 1}}

    repository.update(player.player_id, prepare)
    started = service.plant("talent-sub", 0, "carrot")["result"]

    assert started["total_ability"] == 20
    assert started["quality_ability"] == 20
    assert started["final_duration"] < started["base_duration"]
