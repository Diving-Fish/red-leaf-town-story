from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition
from red_leaf_town.partner_traits import record_partner_trait_effect, register_partner_trait


def partner(partner_id: str, exploration: int | None) -> PartnerDefinition:
    tendencies = [{"industry": "farming", "level_1": 10, "level_60": 10}]
    if exploration is not None:
        tendencies.insert(0, {
            "industry": "exploration",
            "level_1": exploration,
            "level_60": exploration,
        })
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": partner_id,
        "rarity": 3,
        "tendencies": tendencies,
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def exploration_game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    catalog = PartnerCatalog(partners=[
        partner("leader", 40),
        partner("scout", 20),
        partner("helper", None),
    ])
    service = GameService(
        content,
        repository,
        clock=lambda: 1_700_000_000,
        rng=random.Random(4),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("exploration-sub", "采运测试员")
    for partner_id in ("leader", "scout", "helper"):
        service.admin_grant_partner(player.player_id, partner_id)

    def prepare(state):
        state.experience = next(entry.total_xp for entry in content.levels if entry.level == 16)
        state.coins = 10_000
        state.stamina = 50

    repository.update(player.player_id, prepare)
    return service, repository, player


def test_transport_expedition_requires_an_exploration_leader_and_charges_entry(exploration_game):
    service, _, _ = exploration_game

    with pytest.raises(GameError, match="领队必须具有探索倾向"):
        service.start_exploration(
            "exploration-sub",
            "red_maple_hinterland",
            ["helper", "leader"],
            "helper",
        )

    started = service.start_exploration(
        "exploration-sub",
        "red_maple_hinterland",
        ["leader", "scout", "helper"],
        "leader",
    )
    run = started["state"]["exploration"]["active_run"]

    assert started["state"]["player"]["coins"] == 9000
    assert run["exploration_ability"] == 45
    assert run["current_event"]["id"] == "windfallen_timber"
    assert run["current_event"]["choices"][0]["stamina_cost_min"] == 5
    assert run["party"][0]["partner_id"] == "leader"


def test_transport_event_spends_stamina_freezes_loot_and_withdraws_to_inventory(exploration_game):
    service, repository, player = exploration_game
    service.start_exploration(
        "exploration-sub",
        "red_maple_hinterland",
        ["leader", "scout", "helper"],
        "leader",
    )

    resolved = service.resolve_exploration_event("exploration-sub", "clear_edges")
    run = resolved["state"]["exploration"]["active_run"]

    assert resolved["result"]["success"] is True
    assert resolved["result"]["stamina_cost"] == 5
    assert resolved["state"]["player"]["stamina"] == 45
    assert run["depth"] == 1
    assert sum(drop["quantity"] for drop in run["pending_rewards"] if drop["item_id"] == "maple_wood") >= 8
    assert repository.get(player.player_id).inventory.get("maple_wood") is None

    withdrawn = service.withdraw_exploration("exploration-sub")
    assert withdrawn["result"]["depth"] == 1
    assert withdrawn["state"]["exploration"]["active_run"] is None
    assert sum(repository.get(player.player_id).inventory["maple_wood"].values()) >= 8


def test_checked_exploration_choice_can_select_any_party_actor(exploration_game):
    service, _, _ = exploration_game
    started = service.start_exploration(
        "exploration-sub",
        "red_maple_hinterland",
        ["leader", "scout", "helper"],
        "leader",
    )
    choice = started["state"]["exploration"]["active_run"]["current_event"]["choices"][1]
    assert {entry["partner_id"] for entry in choice["actor_options"]} == {"leader", "scout", "helper"}

    resolved = service.resolve_exploration_event("exploration-sub", choice["id"], "helper")
    assert resolved["result"]["actor_partner_ids"] == ["helper"]


def test_checked_exploration_choice_rejects_actor_outside_party(exploration_game):
    service, _, _ = exploration_game
    started = service.start_exploration("exploration-sub", "red_maple_hinterland", ["leader"], "leader")
    choice = started["state"]["exploration"]["active_run"]["current_event"]["choices"][1]
    with pytest.raises(GameError, match="不在当前探索队伍"):
        service.resolve_exploration_event("exploration-sub", choice["id"], "missing")


def test_full_high_yield_route_uses_about_one_stamina_bar(exploration_game):
    service, _, _ = exploration_game
    service.start_exploration(
        "exploration-sub",
        "red_maple_hinterland",
        ["leader", "scout"],
        "leader",
    )

    while True:
        run = service.snapshot_by_sub("exploration-sub")["exploration"]["active_run"]
        if run["status"] == "completed":
            break
        event_id = run["current_event"]["id"]
        choice_id = {
            "windfallen_timber": "recover_trunks",
            "mossy_slope": "detour",
            "hollow_ancient_maple": "fell_trunk",
        }[event_id]
        service.resolve_exploration_event("exploration-sub", choice_id)

    run = service.snapshot_by_sub("exploration-sub")["exploration"]["active_run"]
    assert run["depth"] == 7
    assert 40 <= run["stamina_spent"] <= 50
    assert run["current_event"] is None


def test_player_schema_29_adds_an_empty_exploration_run():
    from red_leaf_town.domain import PlayerState

    migrated = PlayerState.model_validate({
        "schema_version": 26,
        "player_id": "legacy",
        "oauth_sub": "legacy-sub",
        "display_name": "旧居民",
        "stamina_updated_at": 1,
        "created_at": 1,
        "updated_at": 1,
    })

    assert migrated.schema_version == 29
    assert migrated.exploration_run is None


def test_exploration_trait_can_target_transport_without_affecting_other_types(exploration_game):
    service, _, _ = exploration_game
    code = "test_transport_route_skill"

    @register_partner_trait(
        code,
        "采运脚程测试",
        "只减少采运路线消耗。",
        phases=("exploration_event",),
        replace=True,
    )
    def apply(context):
        if context.get("exploration_type") != "transport":
            return
        context["route_stamina_multiplier"] *= 0.5
        record_partner_trait_effect(context, "route_stamina_multiplier", value=0.5)

    service.partner_catalog_loader().partner_map["leader"].trait_codes = [code]
    started = service.start_exploration(
        "exploration-sub",
        "red_maple_hinterland",
        ["leader"],
        "leader",
    )
    choice = started["state"]["exploration"]["active_run"]["current_event"]["choices"][0]

    assert choice["stamina_cost_min"] == 4
    assert choice["applied_effects"][0]["effect"] == "route_stamina_multiplier"
