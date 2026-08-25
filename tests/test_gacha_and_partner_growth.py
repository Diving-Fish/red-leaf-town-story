from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.economy import add_item
from red_leaf_town.gacha_pools import GachaDefinition, load_gacha_pools
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import (
    PartnerArtwork,
    PartnerDefinition,
    PartnerTendency,
    load_partner_catalog,
)


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
    first = service.recruit("growth-sub", 10, "recruit-request-1", "standard-1")
    after_first = repository.get(player.player_id)
    replay = service.recruit("growth-sub", 10, "recruit-request-1", "standard-1")
    after_replay = repository.get(player.player_id)

    assert first["result"]["results"] == replay["result"]["results"]
    assert replay["result"]["replayed"] is True
    assert after_first.guide_leaves < before.guide_leaves
    assert after_replay.guide_leaves == after_first.guide_leaves
    assert len({entry.partner_id for entry in after_replay.owned_partners}) == len(after_replay.owned_partners)


def test_beginner_pool_guarantees_a_five_star_and_has_no_item_drops(growth_game):
    service, repository, _, player = growth_game
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 10))

    pulled = service.recruit("growth-sub", 10, "beginner-request-1", "beginner-1")
    results = pulled["result"]["results"]

    assert len(results) == 10
    assert all(drop["kind"] == "partner" for drop in results)
    assert any(drop["rarity"] == 5 for drop in results)


def test_gacha_pool_max_pulls_is_enforced(growth_game):
    service, repository, _, player = growth_game
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 20))

    service.recruit("growth-sub", 10, "beginner-request-2", "beginner-1")
    with pytest.raises(GameError) as exhausted:
        service.recruit("growth-sub", 1, "beginner-request-3", "beginner-1")
    assert exhausted.value.code == "gacha_pool_exhausted"


def test_gacha_pool_pity_is_tracked_independently_per_pool(growth_game):
    service, repository, _, player = growth_game
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 20))

    before = service.snapshot_by_sub("growth-sub")
    standard_before = next(pool for pool in before["gacha_pools"] if pool["pool_id"] == "standard-1")

    service.recruit("growth-sub", 10, "beginner-request-4", "beginner-1")

    after = service.snapshot_by_sub("growth-sub")
    standard_after = next(pool for pool in after["gacha_pools"] if pool["pool_id"] == "standard-1")

    assert standard_after["pulls_until_five_star"] == standard_before["pulls_until_five_star"]
    assert standard_after["remaining_pulls"] is None
    assert not [pool for pool in after["gacha_pools"] if pool["pool_id"] == "beginner-1"]


def test_exhausted_limited_pools_disappear_from_the_snapshot(growth_game):
    service, repository, _, player = growth_game
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 20))

    before = service.snapshot_by_sub("growth-sub")
    assert any(pool["pool_id"] == "beginner-1" for pool in before["gacha_pools"])

    service.recruit("growth-sub", 10, "beginner-request-5", "beginner-1")

    after = service.snapshot_by_sub("growth-sub")
    assert not any(pool["pool_id"] == "beginner-1" for pool in after["gacha_pools"])
    assert any(pool["pool_id"] == "standard-1" for pool in after["gacha_pools"])


def test_unknown_gacha_pool_is_rejected(growth_game):
    service, repository, _, player = growth_game
    with pytest.raises(GameError) as missing:
        service.recruit("growth-sub", 1, "bad-pool-request", "does-not-exist")
    assert missing.value.code == "gacha_pool_not_found"


def test_guqi_up_pool_skews_five_star_draws_toward_the_featured_partner(growth_game):
    service, *_ = growth_game
    catalog = load_partner_catalog()
    five_star_candidates = [entry for entry in catalog.partners if entry.rarity == 5]
    gacha = GachaDefinition(
        pool_id="test-up",
        title="测试 UP 池",
        rarity_probabilities={3: 0, 4: 0, 5: 1},
        item_probability=0,
        four_star_guarantee=999,
        five_star_pity=999,
        featured_partner_id="guqi",
        featured_rate=0.8,
    )
    service.rng = random.Random(7)

    picks = [service._pick_gacha_partner(gacha, five_star_candidates, 5).id for _ in range(4000)]
    featured_share = picks.count("guqi") / len(picks)

    assert 0.74 < featured_share < 0.86
    assert set(picks) <= {entry.id for entry in five_star_candidates}


def test_gacha_pools_snapshot_carries_background_and_featured_metadata(growth_game):
    service, repository, _, player = growth_game
    snapshot = service.snapshot_by_sub("growth-sub")
    pools = {pool["pool_id"]: pool for pool in snapshot["gacha_pools"]}

    assert pools["beginner-1"]["background"]["asset_key"]
    assert pools["standard-1"]["background"]["asset_key"]
    assert pools["guqi-up-1"]["featured_partner_id"] == "guqi"
    assert pools["guqi-up-1"]["featured_rate"] == pytest.approx(0.8)
    assert pools["standard-1"]["featured_partner_id"] is None


def test_partners_without_a_first_artwork_never_drop_and_stay_out_of_the_pool_catalog(growth_game):
    service, repository, _, player = growth_game
    catalog = load_partner_catalog().model_copy(deep=True)
    drafted_ids = set()
    for rarity in (3, 4, 5):
        drafted = PartnerDefinition(
            id=f"drafted_{rarity}_star",
            name=f"未完成的{rarity}星",
            rarity=rarity,
            tendencies=[PartnerTendency(industry="farming", level_1=36, level_60=223)],
        )
        catalog.partners.append(drafted)
        drafted_ids.add(drafted.id)
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 500))

    dropped: set[str] = set()
    for index in range(50):
        pulled = service.recruit("growth-sub", 10, f"draft-request-{index}", "standard-1")
        dropped |= {drop["content_id"] for drop in pulled["result"]["results"] if drop["kind"] == "partner"}

    snapshot = service.snapshot_by_sub("growth-sub")
    pool = next(entry for entry in snapshot["gacha_pools"] if entry["pool_id"] == "standard-1")

    assert dropped and not dropped & drafted_ids
    assert not {entry["partner_id"] for entry in pool["catalog"]} & drafted_ids
    assert all(entry["artwork"] for entry in pool["catalog"])


def test_recruitment_reports_a_broken_pool_when_a_rarity_has_no_illustrated_partner(growth_game):
    service, repository, _, player = growth_game
    catalog = load_partner_catalog().model_copy(deep=True)
    for partner in catalog.partners:
        if partner.rarity == 5:
            partner.artworks = []
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 10))

    with pytest.raises(GameError) as invalid:
        service.recruit("growth-sub", 10, "no-five-star-artwork", "beginner-1")

    assert invalid.value.code == "gacha_pool_invalid"


def illustrate(partner: PartnerDefinition) -> None:
    partner.artworks = [PartnerArtwork(
        breakthrough=0,
        asset_key=f"red-leaf-town/partners/{partner.id}/breakthrough-0-test.webp",
        width=936,
        height=1664,
        content_type="image/webp",
    )]


def test_newcomer_pool_stays_hidden_while_its_partners_have_no_artwork(growth_game):
    service, repository, _, player = growth_game
    pool = load_gacha_pools()["newcomers-1"]
    catalog = load_partner_catalog().model_copy(deep=True)
    for partner in catalog.partners:
        if partner.id in set(pool.partner_ids):
            partner.artworks = []
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 10))

    snapshot = service.snapshot_by_sub("growth-sub")

    assert not any(entry["pool_id"] == "newcomers-1" for entry in snapshot["gacha_pools"])
    assert any(entry["pool_id"] == "standard-1" for entry in snapshot["gacha_pools"])

    with pytest.raises(GameError) as closed:
        service.recruit("growth-sub", 10, "newcomer-closed", "newcomers-1")
    assert closed.value.code == "gacha_pool_invalid"
    assert repository.get(player.player_id).guide_leaves == 10


def test_newcomer_pool_draws_only_its_own_partners_and_guarantees_a_five_star(growth_game):
    service, repository, _, player = growth_game
    pool = load_gacha_pools()["newcomers-1"]
    catalog = load_partner_catalog().model_copy(deep=True)
    for partner in catalog.partners:
        if partner.id in set(pool.partner_ids):
            illustrate(partner)
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 20))

    listed = next(entry for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"] if entry["pool_id"] == "newcomers-1")
    assert {entry["partner_id"] for entry in listed["catalog"]} == set(pool.partner_ids)
    assert listed["remaining_pulls"] == 10

    pulled = service.recruit("growth-sub", 10, "newcomer-request-1", "newcomers-1")
    results = pulled["result"]["results"]

    assert len(results) == 10
    assert all(drop["kind"] == "partner" for drop in results)
    assert {drop["content_id"] for drop in results} <= set(pool.partner_ids)
    assert any(drop["rarity"] == 5 for drop in results)

    with pytest.raises(GameError) as exhausted:
        service.recruit("growth-sub", 1, "newcomer-request-2", "newcomers-1")
    assert exhausted.value.code == "gacha_pool_exhausted"
    assert not any(
        entry["pool_id"] == "newcomers-1"
        for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"]
    )


def test_limited_pool_rejects_a_featured_partner_outside_its_roster():
    with pytest.raises(ValueError):
        GachaDefinition(
            pool_id="bad-limited",
            title="名单外的 UP",
            rarity_probabilities={3: 0.7, 4: 0.25, 5: 0.05},
            item_probability=0,
            four_star_guarantee=10,
            five_star_pity=10,
            partner_ids=["babi", "leilei"],
            featured_partner_id="guqi",
            featured_rate=0.5,
        )


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
    pulled = service.recruit("growth-sub", 10, "recruit-request-2", "standard-1")
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
        state.companion_marks = service.content.gacha_economy.star_up_costs[3]

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
