from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.economy import add_item
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import load_partner_catalog


class Clock:
    def __init__(self):
        self.now = 1_700_000_000

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


@pytest.fixture
def growth_game():
    content = load_content().model_copy(deep=True)
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    service = GameService(content, repository, clock=clock, rng=random.Random(24))
    player = service.ensure_player("growth-sub", "同行居民")
    repository.update(player.player_id, lambda state: setattr(state, "experience", content.levels[-1].total_xp))
    return service, repository, clock, player


def test_recruitment_is_atomic_and_request_id_is_idempotent(growth_game):
    service, repository, _, player = growth_game
    before = repository.get(player.player_id)
    first = service.recruit("growth-sub", 10, "recruit-request-1")
    after_first = repository.get(player.player_id)
    replay = service.recruit("growth-sub", 10, "recruit-request-1")
    after_replay = repository.get(player.player_id)

    assert first["result"]["results"] == replay["result"]["results"]
    assert replay["result"]["replayed"] is True
    assert after_first.guide_leaves < before.guide_leaves
    assert after_replay.guide_leaves == after_first.guide_leaves
    assert len({entry.partner_id for entry in after_replay.owned_partners}) == len(after_replay.owned_partners)


def test_duplicates_turn_into_marks_instead_of_duplicate_partners(growth_game):
    service, repository, _, player = growth_game
    catalog = load_partner_catalog()

    def own_pool(state):
        from red_leaf_town.domain import OwnedPartnerState

        state.owned_partners = [
            OwnedPartnerState(partner_id=entry.id, stars=entry.rarity, acquired_at=state.created_at)
            for entry in catalog.partners
        ]

    repository.update(player.player_id, own_pool)
    before = repository.get(player.player_id)
    pulled = service.recruit("growth-sub", 10, "recruit-request-2")
    after = repository.get(player.player_id)

    assert all(drop["duplicate"] for drop in pulled["result"]["results"] if drop["kind"] == "partner")
    assert after.companion_marks > before.companion_marks
    assert len(after.owned_partners) == len(before.owned_partners)


def test_golden_leaf_is_consumed_into_an_immutable_miracle_snapshot(growth_game):
    service, repository, _, player = growth_game

    def prepare(state):
        add_item(state, "carrot_seed", 1)
        state.task_items["golden_leaf"] = 1

    repository.update(player.player_id, prepare)
    started = service.plant("growth-sub", 0, "carrot", "golden_leaf")
    quality = started["state"]["plots"][0]["task_snapshot"]["quality_parameters"]

    assert quality["miracle_eligible"] is True
    assert quality["miracle_cap_ignored"] is True
    assert quality["miracle_width_multiplier"] > 1
    assert "golden_leaf" not in repository.get(player.player_id).task_items

    service.content.crop_map["carrot"].quality.miracle_eligible = False
    settled = service.snapshot_by_sub("growth-sub")["plots"][0]["task_snapshot"]["quality_parameters"]
    assert settled == quality


def test_active_task_item_finishes_an_eligible_running_task(growth_game):
    service, repository, clock, player = growth_game
    item = service.content.task_item_map["night_lamp_tea"]

    def prepare(state):
        add_item(state, "carrot_seed", 1)
        state.task_items[item.id] = 1

    repository.update(player.player_id, prepare)
    started = service.plant("growth-sub", 0, "carrot")["state"]["plots"][0]
    clock.advance(max(0, started["ready_at"] - clock.now - int(item.value)))
    finished = service.use_active_task_item("growth-sub", "farming", "0", item.id)

    assert finished["state"]["plots"][0]["ready"] is True
    assert item.id not in repository.get(player.player_id).task_items


def test_mining_ability_changes_yield_but_not_duration(growth_game):
    service, repository, _, first = growth_game
    second = service.ensure_player("growth-miner-sub", "矿工居民")
    repository.update(second.player_id, lambda state: setattr(state, "experience", service.content.levels[-1].total_xp))
    service.admin_grant_partner(second.player_id, "xiang_hanyang")
    service.snapshot_by_sub("growth-miner-sub")
    service.assign_mining_partner("growth-miner-sub", "copper_foothill", "xiang_hanyang")

    solo = service.start_mining("growth-sub", "copper_foothill", "mine_red_copper")["result"]
    assisted = service.start_mining("growth-miner-sub", "copper_foothill", "mine_red_copper")["state"]["mining_sites"][0]["task_snapshot"]
    solo_snapshot = service.snapshot_by_sub("growth-sub")["mining_sites"][0]["task_snapshot"]

    assert assisted["final_duration"] == solo["final_duration"] == solo_snapshot["base_duration"]
    assert assisted["yield_efficiency"] > solo_snapshot["yield_efficiency"]
    assert assisted["yield_min"] >= solo_snapshot["yield_min"]


def test_partner_books_star_up_and_unconfigured_breakthrough(growth_game):
    service, repository, _, player = growth_game
    service.admin_grant_partner(player.player_id, "xiang_hanyang")
    book_id = next(iter(service.content.partner_growth.experience_books))

    def prepare(state):
        add_item(state, book_id, 1)
        state.companion_marks = service.content.gacha.star_up_costs[3]

    repository.update(player.player_id, prepare)
    before = next(entry for entry in repository.get(player.player_id).owned_partners if entry.partner_id == "xiang_hanyang")
    trained = service.train_partner("growth-sub", "xiang_hanyang", book_id, 1)
    ranked = service.star_up_partner("growth-sub", "xiang_hanyang")

    assert trained["state"]["partners"][-1]["level"] > before.level
    assert ranked["state"]["partners"][-1]["stars"] > before.stars
    assert sum(repository.get(player.player_id).inventory.get(book_id, {}).values()) == 0
    with pytest.raises(GameError) as unavailable:
        service.breakthrough_partner("growth-sub", "xiang_hanyang")
    assert unavailable.value.code == "breakthrough_unavailable"
