from __future__ import annotations

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import FishCodexEntry, OwnedPartnerState, PortalProgressState
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import load_partner_catalog


NOW = 1_700_000_000


def build_game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    service = GameService(content, repository, clock=lambda: NOW)
    player = service.ensure_player("achievement-sub", "成就居民")
    return service, repository, player


def test_first_achievement_batch_has_fixed_tier_rewards():
    achievements = load_content().achievements

    assert len(achievements) == 22
    assert sum(entry.reward_maple_flame for entry in achievements) == 2100
    assert {entry.reward_maple_flame for entry in achievements if entry.tier == "blue"} == {50}
    assert {entry.reward_maple_flame for entry in achievements if entry.tier == "purple"} == {100}
    assert {entry.reward_maple_flame for entry in achievements if entry.tier == "gold"} == {200}


def test_persistent_progress_is_completed_retroactively_but_rewards_wait_for_claim():
    service, repository, player = build_game()
    catalog = load_partner_catalog()
    partners = catalog.partners[:20]
    fish_ids = [
        "trash_fish",
        "stream_fish",
        "whitebait",
        "stone_loach",
        "redfin",
        "lake_fish",
        "deep_fish",
        "giant_stream_carp",
        "giant_maple_perch",
    ]

    def prepare(state):
        state.experience = service.content.levels[14].total_xp
        state.seen_story_ids.append("opening_arrival")
        state.owned_partners = [
            OwnedPartnerState(partner_id=entry.id, stars=entry.rarity, acquired_at=NOW + index)
            for index, entry in enumerate(partners)
        ]
        state.talent_nodes = [entry.id for entry in service.content.talents[:8]]
        state.fish_codex.entries = [
            FishCodexEntry(item_id=item_id, caught=1, first_caught_at=NOW)
            for item_id in fish_ids
        ]
        state.portals = [PortalProgressState(portal_id="first_gate", completed_at=NOW)]

    repository.update(player.player_id, prepare)
    first = service.snapshot_by_sub("achievement-sub")
    completed = {entry["achievement_id"] for entry in first["achievements"]["entries"] if entry["completed"]}

    assert {
        "arrival_from_beyond",
        "first_fish",
        "two_partners",
        "resident_level_5",
        "resident_level_10",
        "resident_level_15",
        "eight_partners",
        "eight_talents",
        "fish_codex_9",
        "first_big_catch",
        "first_portal_completed",
        "twenty_partners",
    } <= completed
    assert "first_harvest" not in completed
    assert first["player"]["maple_flame"] == 0
    assert first["achievements"]["maple_flame_earned"] == 0
    assert first["achievements"]["claimable"] == len(completed)

    second = service.snapshot_by_sub("achievement-sub")
    assert second["player"]["maple_flame"] == first["player"]["maple_flame"]
    assert second["achievements"] == first["achievements"]

    claimed = service.claim_all_achievements("achievement-sub")
    assert len(claimed["result"]["claimed"]) == len(completed)
    assert claimed["state"]["player"]["maple_flame"] == claimed["result"]["maple_flame"]
    assert claimed["state"]["achievements"]["claimable"] == 0
    assert claimed["state"]["achievements"]["maple_flame_earned"] == claimed["result"]["maple_flame"]

    replayed = service.claim_all_achievements("achievement-sub")
    assert replayed["result"] == {"claimed": [], "maple_flame": 0}
    with pytest.raises(GameError) as error:
        service.claim_achievement("achievement-sub", "first_harvest")
    assert error.value.code == "achievement_incomplete"


def test_legacy_commission_history_seeds_only_provable_counts():
    service, repository, player = build_game()
    payload = repository.get(player.player_id).model_dump()
    payload["schema_version"] = 21
    payload.pop("achievement_stats", None)
    payload.pop("achievements", None)
    payload["commission"] = {
        "day": "2026-08-27",
        "commission_id": "commission-own",
        "npc_id": "keli",
        "npc_name": "柯莉",
        "item_id": "carrot",
        "quantity": 1,
        "tier": 1,
        "lucky": False,
        "reward_maple_flame": 100,
        "status": "completed",
        "completed_at": NOW,
        "completed_by_name": "成就居民",
    }

    migrated = type(player).model_validate(payload)

    assert migrated.schema_version == 24
    assert migrated.achievement_stats.own_commissions_completed == 1
    assert migrated.achievement_stats.commissions_completed == 1
    assert migrated.achievement_stats.production_collections == {}


def test_schema_twenty_three_retracts_v22_auto_rewards_before_allowing_claims():
    service, repository, player = build_game()
    payload = repository.get(player.player_id).model_dump()
    payload.update({
        "schema_version": 22,
        "maple_flame": 150,
        "achievements": [
            {"achievement_id": "arrival_from_beyond", "completed_at": NOW},
            {"achievement_id": "first_harvest", "completed_at": NOW},
        ],
    })
    payload.pop("achievement_auto_rewards_reconciled", None)
    migrated = type(player).model_validate(payload)
    repository.players[player.player_id] = migrated

    retracted = service.snapshot_by_sub("achievement-sub")

    assert retracted["player"]["maple_flame"] == 50
    assert retracted["achievements"]["claimable"] == 2
    assert repository.get(player.player_id).achievement_auto_rewards_reconciled is True

    claimed = service.claim_all_achievements("achievement-sub")
    assert claimed["result"]["maple_flame"] == 100
    assert claimed["state"]["player"]["maple_flame"] == 150
