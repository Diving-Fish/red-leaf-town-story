from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from red_leaf_town.partner_content import (
    PartnerCatalog,
    PartnerDefinition,
    growth_progress,
    level_cap_for_breakthrough,
    load_partner_catalog,
    save_partner_catalog,
)
from red_leaf_town.partner_traits import (
    execute_partner_traits,
    record_partner_trait_effect,
    register_partner_trait,
)


def partner_payload():
    return {
        "id": "maple_sprite",
        "name": "枫糖",
        "rarity": 4,
        "description": "擅长照看作物的伙伴。",
        "growth_curve": "early",
        "tendencies": [
            {"industry": "farming", "level_1": 18, "level_60": 96},
            {"industry": "gathering", "level_1": 12, "level_60": 72},
        ],
        "trait_codes": ["1", "3"],
        "artworks": [],
        "avatar_crop": {"source_breakthrough": 0, "x": 0, "y": 0, "w": 128, "h": 128},
    }


def test_growth_curves_share_endpoints_and_have_expected_pacing():
    for curve in ("early", "linear", "late"):
        assert growth_progress(1, curve) == 0
        assert growth_progress(60, curve) == 1
    assert growth_progress(30, "early") > growth_progress(30, "linear")
    assert growth_progress(30, "linear") > growth_progress(30, "late")
    assert [level_cap_for_breakthrough(stage) for stage in range(3)] == [20, 40, 60]


def test_partner_ability_uses_selected_growth_curve():
    partner = PartnerDefinition.model_validate(partner_payload())
    assert partner.ability_at("farming", 1) == 18
    assert partner.ability_at("farming", 60) == 96
    assert partner.ability_at("farming", 20) > 43
    with pytest.raises(KeyError):
        partner.ability_at("mining", 20)


def test_legacy_avatar_crop_migrates_to_three_breakthrough_crops():
    partner = PartnerDefinition.model_validate(partner_payload())
    assert [crop.breakthrough for crop in partner.avatar_crops] == [0, 1, 2]
    assert partner.avatar_crops[0].model_dump() == {
        "breakthrough": 0,
        "x": 0,
        "y": 0,
        "w": 128,
        "h": 128,
    }
    assert partner.avatar_crops[1].w == partner.avatar_crops[2].w == 1


def test_avatar_crops_require_all_three_breakthrough_stages():
    payload = partner_payload()
    payload.pop("avatar_crop")
    payload["avatar_crops"] = [
        {"breakthrough": 0, "x": 0, "y": 0, "w": 1, "h": 1},
        {"breakthrough": 1, "x": 0, "y": 0, "w": 1, "h": 1},
        {"breakthrough": 1, "x": 0, "y": 0, "w": 1, "h": 1},
    ]
    with pytest.raises(ValidationError, match="stages 0, 1 and 2"):
        PartnerDefinition.model_validate(payload)


def test_partner_rejects_duplicate_tendencies_and_unknown_traits():
    payload = partner_payload()
    payload["tendencies"].append({"industry": "farming", "level_1": 1, "level_60": 2})
    with pytest.raises(ValidationError, match="unique industries"):
        PartnerDefinition.model_validate(payload)

    payload = partner_payload()
    payload["trait_codes"] = ["missing"]
    with pytest.raises(ValidationError, match="unknown partner trait"):
        PartnerDefinition.model_validate(payload)


def test_artwork_ratio_and_avatar_crop_are_validated():
    payload = partner_payload()
    payload["artworks"] = [{
        "breakthrough": 0,
        "asset_key": "red-leaf-town/partners/maple/base.webp",
        "width": 900,
        "height": 1600,
        "content_type": "image/webp",
    }]
    payload["avatar_crop"] = {"source_breakthrough": 0, "x": 800, "y": 0, "w": 128, "h": 128}
    with pytest.raises(ValidationError, match="avatar crop"):
        PartnerDefinition.model_validate(payload)

    payload["avatar_crop"] = {"source_breakthrough": 0, "x": 0, "y": 0, "w": 128, "h": 128}
    payload["artworks"][0]["height"] = 1500
    with pytest.raises(ValidationError, match="9:16"):
        PartnerDefinition.model_validate(payload)


def test_catalog_round_trip(tmp_path):
    path = tmp_path / "partners.json"
    catalog = PartnerCatalog(partners=[PartnerDefinition.model_validate(partner_payload())])
    save_partner_catalog(catalog, path)
    loaded = load_partner_catalog(path)
    assert loaded.partner_map["maple_sprite"].name == "枫糖"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 2


def test_legacy_spirit_catalog_field_migrates_to_partners():
    legacy = {"schema_version": 1, "spirits": [partner_payload()]}
    catalog = PartnerCatalog.model_validate(legacy)
    assert catalog.schema_version == 2
    assert catalog.partner_map["maple_sprite"].name == "枫糖"
    assert "spirits" not in catalog.model_dump()


def test_python_trait_registry_dispatches_handlers():
    code = "test_counter_trait"

    @register_partner_trait(code, "测试特性", "用于验证 Python 分发")
    def apply(context):
        context["quality"] += 2

    context = {"quality": 3}
    assert execute_partner_traits(["1", code], context) == [code]
    assert context["quality"] == 5


def test_trait_registry_filters_phases_and_records_frozen_effects():
    code = "test_phase_trait"

    @register_partner_trait(code, "阶段测试特性", "用于验证阶段与效果快照", phases=("output_draw",))
    def apply(context):
        record_partner_trait_effect(context, "reroll_first_duplicate", stacking_group="output_variety")

    skipped = {"phase": "task_prepare", "source_partner_id": "worker", "applied_effects": []}
    assert execute_partner_traits([code], skipped) == []
    assert skipped["applied_effects"] == []

    applied = {"phase": "output_draw", "source_partner_id": "worker", "applied_effects": []}
    assert execute_partner_traits([code], applied) == [code]
    assert applied["applied_effects"] == [{
        "source_type": "partner_trait",
        "trait_code": code,
        "source_partner_id": "worker",
        "phase": "output_draw",
        "effect": "reroll_first_duplicate",
        "stacking_group": "output_variety",
    }]


def test_recruitable_requires_a_breakthrough_zero_artwork():
    drafted = PartnerDefinition.model_validate(partner_payload())
    assert drafted.recruitable is False

    illustrated = PartnerDefinition.model_validate({
        **partner_payload(),
        "artworks": [{
            "breakthrough": 0,
            "asset_key": "red-leaf-town/partners/maple_sprite/breakthrough-0.webp",
            "width": 936,
            "height": 1664,
            "content_type": "image/webp",
        }],
    })
    assert illustrated.recruitable is True
