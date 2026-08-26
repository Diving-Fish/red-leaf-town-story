from __future__ import annotations

import json

import pytest

from red_leaf_town.partner_content import load_partner_catalog
from red_leaf_town.partner_traits import execute_partner_traits, partner_trait_catalog


PARTNER_TRAITS = {
    "ai_xinyu": "flow_treasure",
    "aiweier": "fodder_fields",
    "aorui_jin": "golden_line",
    "babi": "steady_craft",
    "banniang": "dream_forage",
    "bufeng_zhuoying": "ore_chaser",
    "daian_zeer": "rain_garden",
    "fein": "varied_forage",
    "guidengdeng": "ghostfire_refinement",
    "gujian_bu": "deep_soil_edge",
    "guqi": "listen_to_rock",
    "guyu_yu": "ancient_formula",
    "hei_yuchuan": "overcast_worker",
    "luo_nali": "herb_lore",
    "mami": "meticulous_farming",
    "nuanyu": "warm_soil",
    "sunfeng_liya": "swift_wind_work",
    "xiang_hanyang": "ore_heart",
    "xiao_xingyun": "falling_star",
    "xiyue_kanna": "moonlit_selection",
    "ye_huanan": "peaceful_cooking",
    "ye_lvsu": "seasonal_rhythm",
    "ze_feiyang": "fodder_artisan",
}

PENDING_PARTNERS = {
    "aishen",
    "gujian_miao",
    "hongkai",
    "leilei",
    "lengyue",
    "manlong",
    "manlong_2",
    "wujian",
    "xiang_hanyuan",
    "xiaoha",
    "xixi",
    "xuanyuan",
    "zhuoyan",
}


def trait_context(phase: str, **overrides):
    context = {
        "phase": phase,
        "source_partner_id": "test_partner",
        "industry": "farming",
        "action": "",
        "content_tags": [],
        "output_items": [],
        "world": {"weather": {"id": "sunny"}},
        "duration_multiplier": 1.0,
        "quality_ability_bonus": 0.0,
        "quality_ability_multiplier": 1.0,
        "yield_bonus": 0,
        "draw_bonus": 0,
        "rare_weight_multiplier": 1.0,
        "feed_multiplier": 1.0,
        "quality_bonus": 0.0,
        "applied_effects": [],
    }
    context.update(overrides)
    return context


TRAIT_CASES = [
    ("flow_treasure", "instant_action", {"industry": "aquatic", "action": "fishing_cast"}, "rare_weight_multiplier", "increase"),
    ("fodder_fields", "task_prepare", {"industry": "farming", "content_tags": ["fodder"]}, "yield_bonus", "increase"),
    ("golden_line", "instant_action", {"industry": "aquatic", "action": "fishing_cast"}, "rare_weight_multiplier", "increase"),
    ("steady_craft", "task_prepare", {"industry": "crafting"}, "quality_ability_bonus", "increase"),
    ("dream_forage", "output_draw", {"industry": "gathering"}, "draw_bonus", "increase"),
    ("ore_chaser", "task_prepare", {"industry": "mining"}, "yield_bonus", "increase"),
    ("rain_garden", "task_prepare", {"industry": "farming", "world": {"weather": {"id": "rain"}}}, "quality_ability_bonus", "increase"),
    ("varied_forage", "output_draw", {"industry": "gathering"}, None, "effect"),
    ("ghostfire_refinement", "result_finalize", {"industry": "crafting"}, None, "effect"),
    ("deep_soil_edge", "task_prepare", {"industry": "farming"}, "quality_ability_multiplier", "increase"),
    ("listen_to_rock", "task_prepare", {"industry": "mining"}, "quality_ability_multiplier", "increase"),
    ("ancient_formula", "quality_roll", {"industry": "crafting", "content_tags": ["medicine"]}, None, "effect"),
    ("overcast_worker", "task_prepare", {"industry": "gathering", "world": {"weather": {"id": "cloudy"}}}, "duration_multiplier", "decrease"),
    ("herb_lore", "output_draw", {"industry": "gathering", "output_items": [{"item_id": "autumn_herb", "tags": ["forage", "medicine"]}]}, None, "effect"),
    ("meticulous_farming", "quality_roll", {"industry": "farming"}, None, "effect"),
    ("warm_soil", "task_prepare", {"industry": "farming", "world": {"weather": {"id": "sunny"}}}, "duration_multiplier", "decrease"),
    ("swift_wind_work", "task_prepare", {"industry": "mining"}, "duration_multiplier", "decrease"),
    ("ore_heart", "task_prepare", {"industry": "mining"}, "quality_ability_bonus", "increase"),
    ("falling_star", "result_finalize", {"industry": "gathering"}, None, "effect"),
    ("moonlit_selection", "quality_roll", {"industry": "crafting"}, None, "effect"),
    ("peaceful_cooking", "result_finalize", {"industry": "crafting", "content_tags": ["food"]}, None, "effect"),
    ("seasonal_rhythm", "task_prepare", {"industry": "gathering", "world": {"weather": {"id": "rain"}}}, "quality_ability_bonus", "increase"),
    ("fodder_artisan", "task_prepare", {"industry": "crafting", "content_tags": ["fodder"]}, "yield_bonus", "increase"),
]

SECONDARY_TRAIT_CASES = [
    ("moonlit_selection", "instant_action", {"industry": "aquatic", "action": "fishing_cast"}, None, "effect"),
]


def test_only_partners_with_an_implemented_primary_industry_have_traits():
    catalog = load_partner_catalog()
    definitions = {entry.code: entry for entry in partner_trait_catalog()}

    assert len(PARTNER_TRAITS) == 23
    for partner_id, trait_code in PARTNER_TRAITS.items():
        assert catalog.partner_map[partner_id].trait_codes == [trait_code]
        assert definitions[trait_code].implemented is True
    assert {partner_id for partner_id, partner in catalog.partner_map.items() if not partner.trait_codes} == PENDING_PARTNERS


def test_no_two_bound_traits_have_identical_behavior():
    scenarios = [(phase, overrides) for _, phase, overrides, _, _ in [*TRAIT_CASES, *SECONDARY_TRAIT_CASES]]
    signatures: dict[tuple[str, ...], list[str]] = {}
    for code in PARTNER_TRAITS.values():
        observations = []
        for phase, overrides in scenarios:
            context = trait_context(phase, **overrides)
            execute_partner_traits([code], context)
            effects = [
                {
                    key: value
                    for key, value in effect.items()
                    if key not in {"trait_code", "source_partner_id"}
                }
                for effect in context["applied_effects"]
            ]
            observations.append(json.dumps(effects, ensure_ascii=False, sort_keys=True))
        signatures.setdefault(tuple(observations), []).append(code)

    assert [codes for codes in signatures.values() if len(codes) > 1] == []


@pytest.mark.parametrize(("code", "phase", "overrides", "field", "direction"), TRAIT_CASES)
def test_each_partner_trait_reaches_its_effect(
    code: str,
    phase: str,
    overrides: dict,
    field: str | None,
    direction: str,
):
    context = trait_context(phase, **overrides)
    before = context.get(field) if field else None

    assert execute_partner_traits([code], context) == [code]
    assert context["applied_effects"]
    assert context["applied_effects"][0]["trait_code"] == code
    assert context["applied_effects"][0]["phase"] == phase
    if direction == "increase":
        assert context[field] > before
    elif direction == "decrease":
        assert context[field] < before


@pytest.mark.parametrize(("code", "phase", "overrides", "field", "direction"), SECONDARY_TRAIT_CASES)
def test_multi_phase_traits_reach_their_secondary_path(
    code: str,
    phase: str,
    overrides: dict,
    field: str | None,
    direction: str,
):
    context = trait_context(phase, **overrides)
    before = context.get(field) if field else None

    execute_partner_traits([code], context)

    assert context["applied_effects"]
    if direction == "decrease":
        assert context[field] < before
