from red_leaf_town.gacha_pools import load_gacha_pools
from red_leaf_town.partner_content import load_partner_catalog


def test_bai_lin_is_a_limited_four_star_exploration_specialist_with_exceptional_stats():
    partner = load_partner_catalog().partner_map["bai_lin"]

    assert partner.name == "白凛"
    assert partner.rarity == 4
    assert partner.standard_recruitable is False
    assert [(entry.industry, entry.level_1, entry.level_60) for entry in partner.tendencies] == [
        ("exploration", 37, 235),
    ]
    assert partner.exploration_stats.model_dump() == {
        "strength": 18,
        "agility": 16,
        "intelligence": 13,
        "luck": 10,
    }
    assert sum(partner.exploration_stats.model_dump().values()) == 57
    assert partner.trait_codes == ["full_health_advantage", "strength_weapon_tradeoff"]


def test_bai_lin_is_not_listed_in_any_gacha_pool():
    assert all("bai_lin" not in pool.partner_ids for pool in load_gacha_pools().values())
