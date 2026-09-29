from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import CropDefinition, load_content
from red_leaf_town.domain.quality import quality_probabilities
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import load_partner_catalog


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


@pytest.fixture
def game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    service = GameService(content, repository, clock=clock, rng=random.Random(7))
    player = service.ensure_player("oauth-sub-1", "枫糖")
    return service, repository, clock, player


def grant_seed(repository, player, seed_item_id: str, count: int = 1):
    repository.update(player.player_id, lambda state: state.inventory.update({seed_item_id: {0: count}}))


@pytest.mark.parametrize(
    ("crop_id", "seed_item_id", "stamina_cost", "sell_price", "plant_xp", "harvest_xp"),
    [
        ("peach_berry", "peach_berry_seed", 8, 1600, 6, 40),
        ("berry_berry", "berry_berry_seed", 12, 2400, 9, 60),
    ],
)
def test_premium_crop_balance_numbers(game, crop_id, seed_item_id, stamina_cost, sell_price, plant_xp, harvest_xp):
    service, _, _, _ = game
    crop = service.content.crop_map[crop_id]

    assert crop.seed_item_id == seed_item_id
    assert crop.growth_seconds == 86_400
    assert crop.minimum_duration_seconds == 43_200
    assert crop.time_difficulty == 300
    assert (crop.yield_min, crop.yield_max) == (2, 2)
    assert crop.stamina_cost == stamina_cost
    assert (crop.plant_xp, crop.harvest_xp) == (plant_xp, harvest_xp)
    assert crop.min_level == 1
    assert crop.quality.thresholds == [70.0, 130.0, 220.0, 320.0]
    assert crop.quality.width == 50.0
    assert service.content.item_map[crop.produce_item_id].sell_price == sell_price
    assert service.content.item_map[seed_item_id].sell_price == 0


def test_premium_crop_seeds_are_not_sold_in_the_shop(game):
    service, _, _, _ = game
    shop_items = {entry.item_id for entry in service.content.shop}
    assert "peach_berry_seed" not in shop_items
    assert "berry_berry_seed" not in shop_items

    for seed_item_id in ("peach_berry_seed", "berry_berry_seed"):
        with pytest.raises(GameError, match="商品不存在"):
            service.buy("oauth-sub-1", seed_item_id, 1)


@pytest.mark.parametrize(
    ("crop_id", "seed_item_id", "stamina_cost"),
    [("peach_berry", "peach_berry_seed", 8), ("berry_berry", "berry_berry_seed", 12)],
)
def test_plant_and_harvest_premium_crop(game, crop_id, seed_item_id, stamina_cost):
    service, repository, clock, player = game
    grant_seed(repository, player, seed_item_id)

    planted = service.plant("oauth-sub-1", 0, crop_id)
    result = planted["result"]
    # 1 级角色没有农业能力，时间效率为 1，24 小时原样成熟。
    assert result["base_duration"] == 86_400
    assert result["final_duration"] == 86_400
    assert result["total_ability"] == 0
    assert planted["state"]["player"]["stamina"] == 20 - stamina_cost
    assert repository.get(player.player_id).inventory.get(seed_item_id) is None

    clock.advance(86_400)
    harvested = service.harvest("oauth-sub-1", 0)
    reward = harvested["result"]
    assert reward["item_id"] == crop_id
    assert reward["quantity"] == 2
    assert harvested["state"]["plots"][0]["empty"] is True


@pytest.mark.parametrize("crop_id", ["peach_berry", "berry_berry"])
def test_premium_crop_needs_a_seed_in_the_bag(game, crop_id):
    service, _, _, _ = game
    with pytest.raises(GameError, match="resource_insufficient|不足|没有"):
        service.plant("oauth-sub-1", 0, crop_id)


def test_premium_crop_is_gated_by_stamina_not_level(game):
    service, repository, _, player = game
    grant_seed(repository, player, "berry_berry_seed")
    repository.update(player.player_id, lambda state: setattr(state, "stamina", 11))

    with pytest.raises(GameError, match="resource_insufficient|体力"):
        service.plant("oauth-sub-1", 0, "berry_berry")

    repository.update(player.player_id, lambda state: setattr(state, "stamina", 12))
    assert service.plant("oauth-sub-1", 0, "berry_berry")["result"]["crop_id"] == "berry_berry"


def test_minimum_duration_clamps_the_growth_time():
    # 难度 300 下现有农业能力上限压不到 12 小时，用低难度副本确认下限真的会截断。
    content = load_content().model_copy(deep=True)
    crop = next(entry for entry in content.crops if entry.id == "peach_berry")
    content.crops.append(CropDefinition.model_validate({
        **crop.model_dump(),
        "id": "peach_berry_fast",
        "time_difficulty": 1,
    }))
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    service = GameService(content, repository, clock=clock, rng=random.Random(7))
    player = service.ensure_player("oauth-sub-fast", "枫糖")
    grant_seed(repository, player, "peach_berry_seed")
    repository.update(player.player_id, lambda state: setattr(
        state, "talent_nodes", ["farming_roster_1", "farming_ability_1", "farming_roster_2", "farming_ability_2"],
    ))

    planted = service.plant("oauth-sub-fast", 0, "peach_berry_fast")
    assert planted["result"]["time_efficiency"] > 2
    assert planted["result"]["final_duration"] == 43_200


def test_minimum_duration_cannot_exceed_growth_time():
    crop = load_content().crop_map["peach_berry"]
    with pytest.raises(ValueError, match="minimum_duration_seconds"):
        CropDefinition.model_validate({**crop.model_dump(), "minimum_duration_seconds": 86_401})


def test_premium_crop_quality_spread_at_the_farming_ability_ceiling():
    crop = load_content().crop_map["berry_berry"]
    # 天赋 +20 与满级 5★ 农业伙伴（约 114）构成当前农业能力上限。
    probabilities = quality_probabilities(
        134,
        crop.quality.thresholds,
        crop.quality.width,
        crop.quality.miracle_probability_cap,
        crop.quality.miracle_eligible,
    )
    normal, fine, superior, exquisite, miracle = probabilities
    assert normal == pytest.approx(0.218, abs=0.005)
    assert fine == pytest.approx(0.263, abs=0.005)
    assert superior == pytest.approx(0.368, abs=0.005)
    assert exquisite == pytest.approx(0.152, abs=0.005)
    # T5=320 远高于能力上限，奇迹在当前版本几乎不可能出现。
    assert miracle < 0.001


def own_and_assign_bai_li(service, repository, player, slot: int = 0, level: int = 1):
    service.admin_grant_partner(player.player_id, "bai_li")
    if level != 1:
        def raise_level(state):
            next(owned for owned in state.owned_partners if owned.partner_id == "bai_li").level = level
        repository.update(player.player_id, raise_level)
    service.assign_partner("oauth-sub-1", slot, "bai_li")


def trait_effects(planted: dict) -> list[dict]:
    return [
        entry
        for entry in planted["state"]["plots"][0]["task_snapshot"]["applied_effects"]
        if entry.get("trait_code") == "orchard_tending"
    ]


def test_bai_li_is_a_five_star_limited_farming_and_exploration_partner():
    partner = load_partner_catalog().partner_map["bai_li"]
    assert partner.name == "白璃"
    assert partner.rarity == 5
    # 限定角色不进常驻池，只能靠 baili-up-1 这种显式名单的 up 池抽到。
    assert partner.standard_recruitable is False
    assert partner.recruitable is True
    assert partner.trait_codes == ["orchard_tending"]
    assert [entry.industry for entry in partner.tendencies] == ["farming", "exploration"]
    assert partner.ability_at("farming", 20, 5) == 114
    assert sum(partner.exploration_stats.model_dump().values()) == 48


@pytest.mark.parametrize("crop_id", ["peach_berry", "berry_berry"])
def test_orchard_tending_cuts_the_time_and_adds_one_harvest(game, crop_id):
    service, repository, clock, player = game
    grant_seed(repository, player, f"{crop_id}_seed")
    own_and_assign_bai_li(service, repository, player)

    planted = service.plant("oauth-sub-1", 0, crop_id)
    # 1 级白璃（5★）农业能力 41 → 时间效率 1.2405，86400 秒先压到 69652 秒，再吃 -20%。
    assert planted["result"]["total_ability"] == 41
    assert planted["result"]["final_duration"] == 55_722
    assert {entry["effect"] for entry in trait_effects(planted)} == {"duration_multiplier", "yield_bonus"}

    clock.advance(planted["result"]["final_duration"])
    harvested = service.harvest("oauth-sub-1", 0)
    assert harvested["result"]["quantity"] == 3


def test_orchard_tending_ignores_crops_without_the_tree_fruit_tag(game):
    service, repository, _, player = game
    own_and_assign_bai_li(service, repository, player)
    service.buy("oauth-sub-1", "carrot_seed", 1)

    planted = service.plant("oauth-sub-1", 0, "carrot")
    assert trait_effects(planted) == []
    # 胡萝卜的时间难度是 120，效率 1.5093，10800 秒压到 7156 秒，没有额外的 -20%。
    assert planted["result"]["final_duration"] == 7_156


def test_orchard_tending_can_push_the_duration_below_the_twelve_hour_floor(game):
    service, repository, _, player = game
    grant_seed(repository, player, "berry_berry_seed")
    repository.update(player.player_id, lambda state: setattr(
        state, "talent_nodes", ["farming_roster_1", "farming_ability_1", "farming_roster_2", "farming_ability_2"],
    ))
    own_and_assign_bai_li(service, repository, player, level=20)

    planted = service.plant("oauth-sub-1", 0, "berry_berry")
    # 天赋 20 + 满级白璃 114 = 当前农业能力上限，86400/1.6175 = 53416 秒仍高于 12 小时下限，
    # -20% 压在下限之后结算，最终跌破下限（约 11.87 小时）。
    assert planted["result"]["total_ability"] == 134
    assert planted["result"]["final_duration"] == 42_733
    assert planted["result"]["final_duration"] < service.content.crop_map["berry_berry"].minimum_duration_seconds


def expected_sale_multiplier(content, quality, ability: int = 0) -> float:
    """按品质曲线算出的期望售价倍率。无伙伴加成时能力为 0。"""
    from red_leaf_town.domain.quality import quality_probabilities

    grades = {grade.level: grade.sale_multiplier for grade in content.quality.grades}
    probabilities = quality_probabilities(
        ability, quality.thresholds, quality.width,
        quality.miracle_probability_cap, quality.miracle_eligible,
    )
    return sum(probabilities[index] * grades[index + 1] for index in range(5))


def test_tree_fruit_pays_for_the_stamina_it_costs(game):
    """树果是唯一收体力的作物，所以它每点体力的回报必须明显高于零风险的采矿。

    这条不是抄数据文件里的价格，而是守住「体力的去处之间不能倒挂」：树果的种子只能从
    探秘副本掉，那趟本身还要 2500 入场费和三十多点体力，如果种植环节的回报还不如挖矿，
    整条链就没有人会走。
    """
    service, _, _, _ = game
    content = service.content

    mining_rates = []
    for task in content.mining_tasks:
        item = content.item_map[task.produce_item_id]
        average_yield = (task.yield_min + task.yield_max) / 2
        gross = average_yield * item.sell_price * expected_sale_multiplier(content, task.quality)
        mining_rates.append(gross / task.stamina_cost)
    best_mining = max(mining_rates)

    for crop_id in ("peach_berry", "berry_berry"):
        crop = content.crop_map[crop_id]
        item = content.item_map[crop.produce_item_id]
        average_yield = (crop.yield_min + crop.yield_max) / 2
        gross = average_yield * item.sell_price * expected_sale_multiplier(content, crop.quality)

        assert crop.stamina_cost > 0, "树果是唯一收体力的作物"
        assert gross / crop.stamina_cost > best_mining * 2


def test_only_tree_fruit_charges_stamina_to_plant(game):
    service, _, _, _ = game
    charging = {crop.id for crop in service.content.crops if crop.stamina_cost > 0}
    assert charging == {"peach_berry", "berry_berry", "passho_berry", "pamtre_berry", "ribbed_berry"}
