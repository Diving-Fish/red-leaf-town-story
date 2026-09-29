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
    assert pools["vanessa-up-1"]["featured_partner_id"] == "vanessa"
    assert pools["vanessa-up-1"]["featured_rate"] == pytest.approx(0.8)
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


def test_non_standard_partner_only_appears_in_explicit_pool_rosters(growth_game):
    service, *_ = growth_game
    catalog = load_partner_catalog().model_copy(deep=True)
    limited = catalog.partner_map["guqi"]
    limited.standard_recruitable = False

    standard = load_gacha_pools()["standard-1"]
    standard_candidates = service._pool_partner_candidates(standard, catalog)
    assert limited.id not in {entry.id for entry in standard_candidates[limited.rarity]}

    explicit = standard.model_copy(update={"pool_id": "limited-test", "partner_ids": [limited.id]})
    limited_candidates = service._pool_partner_candidates(explicit, catalog)
    assert [entry.id for entry in limited_candidates[limited.rarity]] == [limited.id]


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


NEWCOMER_POOL_IDS = ["newcomers-1", "newcomers-2"]


@pytest.mark.parametrize("pool_id", NEWCOMER_POOL_IDS)
def test_newcomer_pool_stays_hidden_while_its_partners_have_no_artwork(growth_game, pool_id):
    service, repository, _, player = growth_game
    pool = load_gacha_pools()[pool_id]
    catalog = load_partner_catalog().model_copy(deep=True)
    for partner in catalog.partners:
        if partner.id in set(pool.partner_ids):
            partner.artworks = []
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 10))

    snapshot = service.snapshot_by_sub("growth-sub")

    assert not any(entry["pool_id"] == pool_id for entry in snapshot["gacha_pools"])
    assert any(entry["pool_id"] == "standard-1" for entry in snapshot["gacha_pools"])

    with pytest.raises(GameError) as closed:
        service.recruit("growth-sub", 10, "newcomer-closed", pool_id)
    assert closed.value.code == "gacha_pool_invalid"
    assert repository.get(player.player_id).guide_leaves == 10


@pytest.mark.parametrize("pool_id", NEWCOMER_POOL_IDS)
def test_newcomer_pool_draws_only_its_own_partners_and_guarantees_a_five_star(growth_game, pool_id):
    service, repository, _, player = growth_game
    pool = load_gacha_pools()[pool_id]
    catalog = load_partner_catalog().model_copy(deep=True)
    for partner in catalog.partners:
        if partner.id in set(pool.partner_ids):
            illustrate(partner)
    service.partner_catalog_loader = lambda: catalog
    repository.update(player.player_id, lambda state: setattr(state, "guide_leaves", 20))

    listed = next(entry for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"] if entry["pool_id"] == pool_id)
    assert {entry["partner_id"] for entry in listed["catalog"]} == set(pool.partner_ids)
    assert listed["remaining_pulls"] == 10

    pulled = service.recruit("growth-sub", 10, "newcomer-request-1", pool_id)
    results = pulled["result"]["results"]

    assert len(results) == 10
    assert all(drop["kind"] == "partner" for drop in results)
    assert {drop["content_id"] for drop in results} <= set(pool.partner_ids)
    assert any(drop["rarity"] == 5 for drop in results)

    with pytest.raises(GameError) as exhausted:
        service.recruit("growth-sub", 1, "newcomer-request-2", pool_id)
    assert exhausted.value.code == "gacha_pool_exhausted"
    assert not any(
        entry["pool_id"] == pool_id
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
    catalog = load_partner_catalog().model_copy(deep=True)
    catalog.partner_map["xiang_hanyang"].ascensions = []
    service.partner_catalog_loader = lambda: catalog
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


def test_every_limited_pool_lists_known_partners_and_can_fill_all_three_rarities():
    catalog = load_partner_catalog().partner_map
    for pool in load_gacha_pools().values():
        if not pool.partner_ids:
            continue
        unknown = [partner_id for partner_id in pool.partner_ids if partner_id not in catalog]
        assert unknown == [], f"{pool.pool_id} 名单里有不存在的伙伴：{unknown}"
        rarities = {catalog[partner_id].rarity for partner_id in pool.partner_ids}
        assert rarities == {3, 4, 5}, f"{pool.pool_id} 缺少 {sorted({3, 4, 5} - rarities)} 星，保底会抽空"


def test_baili_up_pool_features_the_limited_partner_and_keeps_the_standard_roster(growth_game):
    service, repository, _, player = growth_game
    catalog = load_partner_catalog()
    pool = load_gacha_pools()["baili-up-1"]

    assert pool.featured_partner_id == "bai_li"
    assert pool.featured_rate == pytest.approx(0.8)
    assert pool.background_asset_id == "baili_gacha"
    assert not catalog.partner_map["bai_li"].standard_recruitable

    candidates = service._pool_partner_candidates(pool, catalog)
    standard = service._pool_partner_candidates(load_gacha_pools()["standard-1"], catalog)
    assert "bai_li" in {entry.id for entry in candidates[5]}
    assert {entry.id for entry in standard[5]} < {entry.id for entry in candidates[5]}
    for rarity in (3, 4):
        assert {entry.id for entry in candidates[rarity]} == {entry.id for entry in standard[rarity]}

    listed = next(
        entry
        for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"]
        if entry["pool_id"] == "baili-up-1"
    )
    assert listed["featured_partner_id"] == "bai_li"
    assert listed["background"]["asset_key"]
    assert "bai_li" in {entry["partner_id"] for entry in listed["catalog"]}

    service.rng = random.Random(11)
    picks = [service._pick_gacha_partner(pool, candidates[5], 5).id for _ in range(4000)]
    assert 0.76 < picks.count("bai_li") / len(picks) < 0.84


def test_vanessa_up_pool_features_only_vanessa_and_standard_partners(growth_game):
    service, repository, _, player = growth_game
    catalog = load_partner_catalog()
    pool = load_gacha_pools()["vanessa-up-1"]

    assert pool.featured_partner_id == "vanessa"
    assert pool.featured_rate == pytest.approx(0.8)
    assert pool.background_asset_id == "vanessa_gacha"
    assert not catalog.partner_map["vanessa"].standard_recruitable

    candidates = service._pool_partner_candidates(pool, catalog)
    standard = service._pool_partner_candidates(load_gacha_pools()["standard-1"], catalog)
    assert "vanessa" in {entry.id for entry in candidates[5]}
    assert {entry.id for entry in standard[5]} < {entry.id for entry in candidates[5]}
    assert {entry.id for entries in candidates.values() for entry in entries} == {
        entry.id for entries in standard.values() for entry in entries
    } | {'vanessa'}
    assert 'vanessa' not in {entry.id for entries in standard.values() for entry in entries}
    for rarity in (3, 4):
        assert {entry.id for entry in candidates[rarity]} == {entry.id for entry in standard[rarity]}

    listed = next(
        entry
        for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"]
        if entry["pool_id"] == "vanessa-up-1"
    )
    assert listed["featured_partner_id"] == "vanessa"
    assert listed["background"]["asset_key"]
    assert "vanessa" in {entry["partner_id"] for entry in listed["catalog"]}

    service.rng = random.Random(11)
    picks = [service._pick_gacha_partner(pool, candidates[5], 5).id for _ in range(4000)]
    assert 0.76 < picks.count("vanessa") / len(picks) < 0.84


def test_bai_tiantian_is_first_and_retired_guqi_pool_cannot_be_pulled(growth_game):
    service, repository, _, player = growth_game
    snapshot = service.snapshot_by_sub("growth-sub")
    assert snapshot["gacha_pools"][0]["pool_id"] == "bai-tiantian-up-1"
    assert "guqi-up-1" not in {pool["pool_id"] for pool in snapshot["gacha_pools"]}
    before = repository.get(player.player_id).model_dump()
    with pytest.raises(GameError, match="招募池不存在"):
        service.recruit("growth-sub", 1, "retired-pool-pull", "guqi-up-1")
    assert repository.get(player.player_id).model_dump() == before


def test_up_guarantee_applies_within_ten_pull_and_resets(growth_game, monkeypatch):
    service, repository, _, player = growth_game
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 5)
    monkeypatch.setattr(service.rng, "random", lambda: 0.99)
    result = service.recruit("growth-sub", 10, "up-ten-guarantee", "vanessa-up-1")
    ids = [drop["content_id"] for drop in result["result"]["results"]]
    assert all(partner_id != "vanessa" for partner_id in ids[::2])
    assert ids[1::2] == ["vanessa"] * 5
    pools = {pool["pool_id"]: pool for pool in result["state"]["gacha_pools"]}
    assert pools["vanessa-up-1"]["featured_guaranteed"] is False


@pytest.mark.parametrize("hard_pity", [False, True])
def test_up_guarantee_survives_other_drops_reload_and_replay(growth_game, monkeypatch, hard_pity):
    from red_leaf_town.domain.models import PlayerState

    service, repository, _, player = growth_game
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 5)
    monkeypatch.setattr(service.rng, "random", lambda: 0.99)
    first = service.recruit("growth-sub", 1, "up-first-miss", "vanessa-up-1")
    assert first["result"]["results"][0]["content_id"] != "vanessa"
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 3)
    service.recruit("growth-sub", 1, "up-three-star", "vanessa-up-1")
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: None)
    service.recruit("growth-sub", 1, "up-item-drop", "vanessa-up-1")
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 5)
    service.recruit("growth-sub", 1, "up-other-pool", "standard-1")

    # 历史即依据：旧存档无需新增标记，序列化重载后仍能恢复大保底。
    restored = PlayerState.model_validate_json(repository.get(player.player_id).model_dump_json())
    gacha = service.gacha_pool_loader()["vanessa-up-1"]
    assert service._gacha_featured_guaranteed(restored, gacha) is True
    pools = {pool["pool_id"]: pool for pool in service.snapshot_by_sub("growth-sub")["gacha_pools"]}
    assert pools["vanessa-up-1"]["featured_guaranteed"] is True
    assert pools["standard-1"]["featured_guaranteed"] is False
    assert pools["baili-up-1"]["featured_guaranteed"] is False
    if hard_pity:
        repository.update(player.player_id, lambda state: setattr(
            state.gacha_progress["vanessa-up-1"], "five_pity", gacha.five_star_pity - 1,
        ))
        monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 3)
    second = service.recruit("growth-sub", 1, "up-next-five", "vanessa-up-1")
    assert second["result"]["results"][0]["content_id"] == "vanessa"
    replay = service.recruit("growth-sub", 1, "up-first-miss", "vanessa-up-1")
    assert replay["result"]["replayed"] is True
    assert replay["result"]["results"] == first["result"]["results"]
    assert service._gacha_featured_guaranteed(repository.get(player.player_id), gacha) is False


def test_new_partner_experience_curve_and_existing_progress(growth_game):
    service, repository, _, player = growth_game
    growth = service.content.partner_growth
    assert sum(growth.experience_for_next_level(level) for level in range(1, 20)) == 3325
    assert sum(growth.experience_for_next_level(level) for level in range(20, 40)) == 33600
    assert [growth.experience_for_next_level(level) for level in (19, 20, 39)] == [310, 350, 3010]
    service.admin_grant_partner(player.player_id, "bai_li")

    def prepare(state):
        owned = next(p for p in state.owned_partners if p.partner_id == "bai_li")
        owned.level, owned.experience = 20, 500
    repository.update(player.player_id, prepare)
    restored = service.snapshot_by_sub("growth-sub")
    owned = next(p for p in restored["partners"] if p["partner_id"] == "bai_li")
    assert (owned["level"], owned["experience"]) == (20, 500)


def _prepare_ascension(service, repository, player, *, level=20, resident=15, material_quality=3):
    service.admin_grant_partner(player.player_id, "bai_li")
    definition = service.partner_catalog_loader().partner_map["bai_li"].ascensions[0]
    def prepare(state):
        state.level = resident
        state.experience = service.content.level_definition(resident).total_xp
        state.coins = 50_000
        owned = next(p for p in state.owned_partners if p.partner_id == "bai_li")
        owned.level, owned.experience = level, 500 if level == 20 else 0
        for item in definition.items:
            add_item(state, item.item_id, item.quantity, material_quality if item.min_quality else 0 if not service.content.item_map[item.item_id].has_quality else 1)
    repository.update(player.player_id, prepare)
    return definition


@pytest.mark.parametrize("level,resident,quality,code", [
    (19, 15, 3, "breakthrough_partner_level"),
    (20, 14, 3, "breakthrough_player_level"),
    (20, 15, 2, "resource_insufficient"),
])
def test_ascension_guards_are_atomic(growth_game, level, resident, quality, code):
    service, repository, _, player = growth_game
    _prepare_ascension(service, repository, player, level=level, resident=resident, material_quality=quality)
    before = repository.get(player.player_id)
    snapshot = service.snapshot_by_sub("growth-sub")
    preview = next(p for p in snapshot["partners"] if p["partner_id"] == "bai_li")
    assert not preview["breakthrough_available"]
    with pytest.raises(GameError) as error:
        service.breakthrough_partner("growth-sub", "bai_li")
    assert error.value.code == code
    after = repository.get(player.player_id)
    assert (after.coins, after.inventory, after.owned_partners) == (before.coins, before.inventory, before.owned_partners)


def test_ascension_consumes_lowest_eligible_quality_and_unlocks_effective_levels(growth_game):
    service, repository, _, player = growth_game
    definition = _prepare_ascension(service, repository, player)
    def extra(state):
        add_item(state, "pumpkin", 7, 2)
        add_item(state, "pumpkin", 4, 4)
        add_item(state, "carrot_seed", 1)
    repository.update(player.player_id, extra)
    service.assign_partner("growth-sub", 0, "bai_li")
    started = service.plant("growth-sub", 0, "carrot")
    frozen = started["state"]["plots"][0]["task_snapshot"]
    preview = next(p for p in started["state"]["partners"] if p["partner_id"] == "bai_li")
    assert preview["ascension"]["artwork"]["breakthrough"] == 1
    assert preview["ascension"]["items"][1]["owned"] == 12
    result = service.breakthrough_partner("growth-sub", "bai_li")
    owned = next(p for p in result["state"]["partners"] if p["partner_id"] == "bai_li")
    assert (owned["level"], owned["experience"], owned["level_cap"], owned["breakthrough"]) == (21, 150, 40, 1)
    assert owned["tendencies"][0]["effective_level"] == 21
    assert owned["artwork"]["breakthrough"] == 1
    assert result["state"]["plots"][0]["task_snapshot"] == frozen
    saved = repository.get(player.player_id)
    assert saved.inventory["pumpkin"] == {2: 7, 4: 4}
    assert saved.coins == 50_000 - definition.coins
    assert "miracle_crystal" not in saved.inventory
    with pytest.raises(GameError) as repeated:
        service.breakthrough_partner("growth-sub", "bai_li")
    assert repeated.value.code == "breakthrough_unavailable"
    assert repository.get(player.player_id).coins == saved.coins


def test_all_live_partner_ascensions_match_review_and_use_original_rarity():
    import csv
    from pathlib import Path
    content = load_content()
    catalog = load_partner_catalog()
    rows = {row["partner_id"]: row for row in csv.DictReader(
        (Path(__file__).parents[1] / "docs/partner-ascension-review.tsv").open(), delimiter="\t",
    )}
    assert set(rows) == set(catalog.partner_map)
    for partner in catalog.partners:
        entry = partner.ascensions[0]
        assert entry.min_player_level == 15
        assert entry.items[0].quantity == {3: 12, 4: 15, 5: 18}[partner.rarity]
        assert entry.coins == int(rows[partner.id]["突破币"])
        assert entry.items[1].min_quality == 3
        assert entry.items[1].item_id == rows[partner.id]["产业物品ID"]
        assert entry.items[1].quantity == int(rows[partner.id]["数量"])
        assert entry.items[2].item_id == rows[partner.id]["特色物品ID"]
        assert entry.items[2].quantity == int(rows[partner.id]["特色数量"])
        assert all(item.item_id in content.item_map for item in entry.items)


@pytest.mark.parametrize("level, breakthrough, quantity", [(1, 0, 10), (19, 0, 99), (20, 1, 20), (39, 1, 99)])
def test_batch_training_matches_snapshot_experience_costs(growth_game, level, breakthrough, quantity):
    service, repository, _, player = growth_game
    service.admin_grant_partner(player.player_id, "xiang_hanyang")
    book_id, book_xp = next(iter(service.content.partner_growth.experience_books.items()))

    def prepare(state):
        partner = next(p for p in state.owned_partners if p.partner_id == "xiang_hanyang")
        partner.level = level
        partner.breakthrough = breakthrough
        partner.experience = 30
        add_item(state, book_id, quantity)

    repository.update(player.player_id, prepare)
    snapshot = service.snapshot_by_sub("growth-sub")
    partner = next(p for p in snapshot["partners"] if p["partner_id"] == "xiang_hanyang")
    costs = snapshot["partner_growth"]["level_experience_costs"]
    expected_level, expected_xp = level, partner["experience"] + book_xp * quantity
    while expected_level < partner["level_cap"] and expected_xp >= costs[expected_level]:
        expected_xp -= costs[expected_level]
        expected_level += 1

    trained = service.train_partner("growth-sub", "xiang_hanyang", book_id, quantity)
    result = next(p for p in trained["state"]["partners"] if p["partner_id"] == "xiang_hanyang")
    assert (result["level"], result["experience"]) == (expected_level, expected_xp)
    assert sum(repository.get(player.player_id).inventory.get(book_id, {}).values()) == 0


def test_partner_artwork_choice_persists_and_is_account_scoped(growth_game):
    service, repository, _, player = growth_game
    _prepare_ascension(service, repository, player)
    service.breakthrough_partner("growth-sub", "bai_li")
    other = service.ensure_player("artwork-other", "另一位居民")
    service.admin_grant_partner(other.player_id, "bai_li")
    result = service.select_partner_artwork("growth-sub", "bai_li", 0)
    owned = next(p for p in result["state"]["partners"] if p["partner_id"] == "bai_li")
    assert owned["breakthrough"] == 1
    assert owned["artwork_stage"] == owned["artwork"]["breakthrough"] == owned["avatar_crop"]["breakthrough"] == 0
    assert [art["breakthrough"] for art in owned["available_artworks"]] == [0, 1]
    # Recreate the service to ensure the selection comes from the account save.
    restored = GameService(service.content, repository, clock=service.clock)
    saved = next(p for p in restored.snapshot_by_sub("growth-sub")["partners"] if p["partner_id"] == "bai_li")
    assert saved["artwork_stage"] == 0
    result = service.select_partner_artwork("growth-sub", "bai_li", 1)
    owned = next(p for p in result["state"]["partners"] if p["partner_id"] == "bai_li")
    assert owned["artwork"]["breakthrough"] == owned["avatar_crop"]["breakthrough"] == 1
    other_saved = next(p for p in service.snapshot_by_sub("artwork-other")["partners"] if p["partner_id"] == "bai_li")
    assert other_saved["artwork_stage"] == 0


@pytest.mark.parametrize("stage", [1, 2, -1, None, True, "0", 0.5])
def test_partner_artwork_rejects_locked_or_invalid_stage(growth_game, stage):
    service, repository, _, player = growth_game
    service.admin_grant_partner(player.player_id, "bai_li")
    before = repository.get(player.player_id)
    with pytest.raises(GameError) as error:
        service.select_partner_artwork("growth-sub", "bai_li", stage)
    assert error.value.code == "partner_artwork_locked"
    assert repository.get(player.player_id).owned_partners == before.owned_partners


def test_partner_artwork_requires_ownership_and_configured_art(growth_game):
    service, repository, _, player = growth_game
    with pytest.raises(GameError):
        service.select_partner_artwork("growth-sub", "bai_li", 0)
    service.admin_grant_partner(player.player_id, "bai_li")
    catalog = service.partner_catalog_loader().model_copy(deep=True)
    catalog.partner_map["bai_li"].artworks = []
    service.partner_catalog_loader = lambda: catalog
    with pytest.raises(GameError) as error:
        service.select_partner_artwork("growth-sub", "bai_li", 0)
    assert error.value.code == "partner_artwork_missing"


def test_bai_tiantian_up_pool_roster_metadata_and_featured_rate(growth_game):
    service, _, _, _ = growth_game
    catalog = load_partner_catalog()
    pool = load_gacha_pools()["bai-tiantian-up-1"]
    assert pool.featured_partner_id == "bai_tiantian"
    assert pool.featured_rate == pytest.approx(0.8)
    assert pool.rarity_probabilities[5] == pytest.approx(0.025)
    assert pool.four_star_guarantee == 10
    assert pool.five_star_pity == 50
    candidates = service._pool_partner_candidates(pool, catalog)
    standard = service._pool_partner_candidates(load_gacha_pools()["standard-1"], catalog)
    for rarity in (3, 4, 5):
        assert {entry.id for entry in candidates[rarity]} == {entry.id for entry in standard[rarity]}
    listed = service.snapshot_by_sub("growth-sub")["gacha_pools"][0]
    assert listed["title"] == "万物归元"
    assert listed["featured_partner_id"] == "bai_tiantian"
    assert listed["background"]["asset_key"].startswith("red-leaf-town/story/background/bai_tiantian_gacha-")
    service.rng = random.Random(11)
    picks = [service._pick_gacha_partner(pool, candidates[5], 5).id for _ in range(4000)]
    assert 0.76 < picks.count("bai_tiantian") / len(picks) < 0.84


def test_bai_tiantian_up_guarantee_and_independent_progress(growth_game, monkeypatch):
    service, _, _, _ = growth_game
    monkeypatch.setattr(service, "_roll_gacha_rarity", lambda *args: 5)
    monkeypatch.setattr(service.rng, "random", lambda: 0.99)
    first = service.recruit("growth-sub", 1, "tiantian-miss", "bai-tiantian-up-1")
    assert first["result"]["results"][0]["content_id"] != "bai_tiantian"
    pools = {pool["pool_id"]: pool for pool in first["state"]["gacha_pools"]}
    assert pools["bai-tiantian-up-1"]["featured_guaranteed"] is True
    assert pools["vanessa-up-1"]["featured_guaranteed"] is False
    second = service.recruit("growth-sub", 1, "tiantian-guarantee", "bai-tiantian-up-1")
    assert second["result"]["results"][0]["content_id"] == "bai_tiantian"
    pools = {pool["pool_id"]: pool for pool in second["state"]["gacha_pools"]}
    assert pools["bai-tiantian-up-1"]["featured_guaranteed"] is False


def test_four_star_up_takes_its_share_of_four_star_draws_without_touching_five_stars(growth_game):
    service, *_ = growth_game
    catalog = load_partner_catalog()
    four_star_candidates = [entry for entry in catalog.partners if entry.rarity == 4]
    five_star_candidates = [entry for entry in catalog.partners if entry.rarity == 5]
    gacha = GachaDefinition(
        pool_id="test-four-up",
        title="测试四星 UP 池",
        rarity_probabilities={3: 0, 4: 1, 5: 0},
        item_probability=0,
        four_star_guarantee=999,
        five_star_pity=999,
        featured_four_star_partner_id="ai_xinyu",
        featured_four_star_rate=0.8,
    )
    service.rng = random.Random(11)

    picks = [service._pick_gacha_partner(gacha, four_star_candidates, 4).id for _ in range(4000)]
    assert 0.77 < picks.count("ai_xinyu") / len(picks) < 0.83
    others = [pick for pick in picks if pick != "ai_xinyu"]
    assert len(set(others)) == len(four_star_candidates) - 1

    five_picks = [service._pick_gacha_partner(gacha, five_star_candidates, 5).id for _ in range(400)]
    assert "ai_xinyu" not in five_picks


def test_four_star_up_must_be_set_together_and_stay_inside_the_roster():
    base = dict(
        title="四星 UP 校验",
        rarity_probabilities={3: 0.7, 4: 0.25, 5: 0.05},
        item_probability=0,
        four_star_guarantee=10,
        five_star_pity=10,
    )
    with pytest.raises(ValueError):
        GachaDefinition(pool_id="half-set", featured_four_star_partner_id="ai_xinyu", **base)
    with pytest.raises(ValueError):
        GachaDefinition(
            pool_id="off-roster",
            partner_ids=["babi", "leilei"],
            featured_four_star_partner_id="ai_xinyu",
            featured_four_star_rate=0.8,
            **base,
        )


@pytest.mark.parametrize("pool_id", ["guqi-sp-up-1", "fein-sp-up-1"])
def test_summer_pools_feature_ai_xinyu_at_ten_percent(growth_game, pool_id):
    service, *_ = growth_game
    pool = load_gacha_pools()[pool_id]
    assert pool.featured_four_star_partner_id == "ai_xinyu"
    assert pool.rarity_probabilities[4] * pool.featured_four_star_rate == pytest.approx(0.10)
    assert pool.rarity_probabilities[4] * (1 - pool.featured_four_star_rate) == pytest.approx(0.025)
    listed = {entry["pool_id"]: entry for entry in service.snapshot_by_sub("growth-sub")["gacha_pools"]}
    if pool_id in listed:
        assert listed[pool_id]["featured_four_star_partner_id"] == "ai_xinyu"
        assert listed[pool_id]["featured_four_star_rate"] == pytest.approx(0.8)
