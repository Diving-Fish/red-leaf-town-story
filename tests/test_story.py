from __future__ import annotations

import json

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition
from red_leaf_town.story_assets import StoryAsset, StoryAssetCatalog
from red_leaf_town.story_content import (
    StoryCatalog,
    StoryScript,
    load_story_catalog,
    serialize_script,
    validate_story_references,
)
from red_leaf_town.story_triggers import StoryContext, evaluate_story_trigger, validate_story_cue


def background_asset(asset_id="autumn_gate"):
    return StoryAsset(
        id=asset_id,
        kind="background",
        name="镇口",
        asset_key=f"red-leaf-town/story/background/{asset_id}.webp",
        width=1920,
        height=1080,
        content_type="image/webp",
    )


def portrait_asset(asset_id="maple_smile", **layout):
    return StoryAsset(
        id=asset_id,
        kind="portrait",
        name="枫糖 微笑",
        asset_key=f"red-leaf-town/story/portrait/{asset_id}.webp",
        width=900,
        height=1600,
        content_type="image/webp",
        **layout,
    )


def inline_script(script_id="hello", cue="view:farm", **trigger):
    return StoryScript.model_validate({
        "id": script_id,
        "title": "打个招呼",
        "trigger": {"hook": "cue", "params": {"cue": cue}, **trigger},
        "steps": [{"type": "dialogue", "speaker": "枫糖", "text": "早上好。"}],
    })


def stage_script(script_id="opening"):
    return StoryScript.model_validate({
        "id": script_id,
        "title": "抵达红叶镇",
        "trigger": {"hook": "player_level", "params": {"level": 2}},
        "steps": [
            {"type": "background", "asset_id": "autumn_gate"},
            {"type": "portrait", "slot": "left", "asset_id": "maple_smile"},
            {"type": "dialogue", "speaker": "枫糖", "text": "欢迎来到红叶镇。", "focus": "left"},
            {"type": "portrait", "slot": "left", "visible": False},
        ],
    })


def partner_definition(partner_id="fein", name="绯恩"):
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": name,
        "rarity": 4,
        "tendencies": [{"industry": "gathering", "level_1": 40, "level_60": 300}],
    })


def reward_script(script_id="joining", partner_id="fein", **trigger):
    return StoryScript.model_validate({
        "id": script_id,
        "title": "她跟上来了",
        "trigger": {"hook": "cue", "params": {"cue": "view:dashboard"}, **trigger},
        "rewards": {"partner_ids": [partner_id]},
        "steps": [{"type": "dialogue", "speaker": "绯恩", "text": "明天早上我来找你。"}],
    })


@pytest.fixture
def service(tmp_path):
    content = load_content()
    assets = StoryAssetCatalog(assets=[background_asset(), portrait_asset()])
    catalog = StoryCatalog(scripts=[inline_script(), stage_script()])
    game = GameService(
        content,
        InMemoryPlayerRepository(content),
        clock=lambda: 1_700_000_000,
        partner_catalog_loader=lambda: PartnerCatalog(partners=[partner_definition()]),
        story_catalog_loader=lambda: catalog,
        story_asset_loader=lambda: assets,
    )
    game.ensure_player("story-sub", "小枫")
    return game


def test_inline_and_stage_modes():
    assert inline_script().mode == "inline"
    assert stage_script().mode == "stage"


def test_script_requires_dialogue():
    with pytest.raises(ValueError):
        StoryScript.model_validate({
            "id": "silent",
            "title": "没有对话",
            "trigger": {"hook": "cue", "params": {"cue": "view:farm"}},
            "steps": [{"type": "background", "asset_id": "autumn_gate"}],
        })


def test_visible_portrait_needs_exactly_one_source():
    for portrait in ({}, {"asset_id": "maple_smile", "partner_id": "maple"}):
        with pytest.raises(ValueError):
            StoryScript.model_validate({
                "id": "broken",
                "title": "立绘来源不明",
                "trigger": {"hook": "cue", "params": {"cue": "view:farm"}},
                "steps": [
                    {"type": "portrait", "slot": "left", **portrait},
                    {"type": "dialogue", "text": "……"},
                ],
            })


def test_unknown_trigger_hook_is_rejected():
    with pytest.raises(ValueError):
        StoryScript.model_validate({
            "id": "broken",
            "title": "未知条件",
            "trigger": {"hook": "when_i_feel_like_it", "params": {}},
            "steps": [{"type": "dialogue", "text": "……"}],
        })


def test_invalid_trigger_params_are_rejected():
    with pytest.raises(ValueError):
        StoryScript.model_validate({
            "id": "broken",
            "title": "等级不合法",
            "trigger": {"hook": "player_level", "params": {"level": 0}},
            "steps": [{"type": "dialogue", "text": "……"}],
        })


def test_unknown_asset_reference_is_rejected():
    catalog = StoryCatalog(scripts=[stage_script()])
    with pytest.raises(ValueError):
        validate_story_references(catalog, StoryAssetCatalog(), PartnerCatalog())


def test_asset_kind_must_match_step():
    catalog = StoryCatalog(scripts=[stage_script()])
    swapped = StoryAssetCatalog(assets=[
        background_asset("maple_smile"),
        portrait_asset("autumn_gate"),
    ])
    with pytest.raises(ValueError):
        validate_story_references(catalog, swapped, PartnerCatalog())


def test_cue_validation():
    assert validate_story_cue("action:collect_mining") == "action:collect_mining"
    for invalid in ("", "View:Farm", "view farm", "view:" + "x" * 80):
        with pytest.raises(ValueError):
            validate_story_cue(invalid)


def test_composite_trigger_hooks(service):
    player = service.repository.get_by_sub("story-sub")
    player.level = 4
    context = StoryContext(player=player, cue="view:farm", now=0)
    params = {"conditions": [
        {"hook": "cue", "params": {"cue": "view:farm"}},
        {"hook": "player_level", "params": {"level": 3}},
    ]}
    assert evaluate_story_trigger(context, "all_of", params) is True
    assert evaluate_story_trigger(context, "none_of", params) is False
    assert evaluate_story_trigger(context, "any_of", {"conditions": [
        {"hook": "cue", "params": {"cue": "view:mining"}},
        {"hook": "player_level", "params": {"level": 3}},
    ]}) is True


def test_cue_returns_matching_story_once(service):
    first = service.story_cue("story-sub", "view:farm")
    assert [entry["id"] for entry in first["stories"]] == ["hello"]
    assert first["stories"][0]["mode"] == "inline"

    service.mark_story_seen("story-sub", "hello")
    assert service.story_cue("story-sub", "view:farm")["stories"] == []


def test_repeatable_story_keeps_returning(service, tmp_path):
    catalog = StoryCatalog(scripts=[inline_script("daily", repeatable=True)])
    service.story_catalog_loader = lambda: catalog
    service.story_cue("story-sub", "view:farm")
    service.mark_story_seen("story-sub", "daily")
    assert [entry["id"] for entry in service.story_cue("story-sub", "view:farm")["stories"]] == ["daily"]


def test_state_triggers_do_not_need_a_cue(service):
    player, _ = service.repository.update(
        service.repository.get_by_sub("story-sub").player_id,
        lambda state: setattr(state, "experience", 10_000),
    )
    service._settled_snapshot(player.player_id)
    stories = service.story_cue("story-sub", "view:dashboard")["stories"]
    assert "opening" in [entry["id"] for entry in stories]


def test_cue_rejects_malformed_codes(service):
    with pytest.raises(GameError) as error:
        service.story_cue("story-sub", "VIEW FARM")
    assert error.value.code == "invalid_story_cue"


def test_mark_unknown_story_fails(service):
    with pytest.raises(GameError) as error:
        service.mark_story_seen("story-sub", "nope")
    assert error.value.code == "story_not_found"


def test_seen_story_is_recorded_once(service):
    service.mark_story_seen("story-sub", "hello")
    service.mark_story_seen("story-sub", "hello")
    player = service.repository.get_by_sub("story-sub")
    assert player.seen_story_ids == ["hello"]


def test_portrait_layout_parameters_have_bounds():
    invalid_layouts = (
        {"inline_layout": {"scale": 4.5}},
        {"inline_layout": {"scale": 0.2}},
        {"stage_layout": {"offset_x": 0.9}},
        {"stage_layout": {"offset_y": -0.9}},
    )
    for invalid in invalid_layouts:
        with pytest.raises(ValueError):
            StoryAsset.model_validate({**portrait_asset().model_dump(), **invalid})
    assert StoryAsset.model_validate({
        **portrait_asset().model_dump(),
        "inline_layout": {"scale": 4.0},
    }).inline_layout.scale == 4.0


def test_background_asset_rejects_layout_parameters():
    with pytest.raises(ValueError):
        StoryAsset.model_validate({**background_asset().model_dump(), "stage_layout": {"scale": 1.4}})


def test_legacy_shared_layout_migrates_to_both_modes():
    asset = StoryAsset.model_validate({
        "id": "maple_smile",
        "kind": "portrait",
        "name": "枫糖",
        "asset_key": "red-leaf-town/story/portrait/maple.webp",
        "width": 900,
        "height": 1600,
        "content_type": "image/webp",
        "scale": 1.4,
        "offset_y": 0.1,
    })
    assert asset.inline_layout.scale == asset.stage_layout.scale == 1.4
    assert asset.inline_layout.offset_y == asset.stage_layout.offset_y == 0.1


def test_portrait_layout_follows_the_asset_per_mode():
    assets = StoryAssetCatalog(assets=[
        background_asset(),
        portrait_asset(
            inline_layout={"scale": 1.3, "offset_x": -0.1, "offset_y": 0.05},
            stage_layout={"scale": 2.4, "offset_x": 0.08, "offset_y": 0},
        ),
    ])
    payload = serialize_script(stage_script(), assets, PartnerCatalog())
    layouts = payload["steps"][1]["asset"]["layouts"]
    assert (layouts["inline"]["scale"], layouts["inline"]["offset_x"]) == (1.3, -0.1)
    assert (layouts["stage"]["scale"], layouts["stage"]["offset_x"]) == (2.4, 0.08)


def test_serialized_step_carries_asset_and_layout():
    assets = StoryAssetCatalog(assets=[background_asset(), portrait_asset()])
    payload = serialize_script(stage_script(), assets, PartnerCatalog())
    background, portrait, dialogue, hide = payload["steps"]
    assert background["asset"]["asset_key"].endswith("autumn_gate.webp")
    assert portrait["asset"]["width"] == 900
    assert portrait["asset"]["layouts"] == {
        "inline": {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        "stage": {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
    }
    assert dialogue["focus"] == "left"
    assert hide["asset"] is None


def test_partner_portrait_resolves_to_artwork():
    partner = PartnerDefinition.model_validate({
        "id": "maple",
        "name": "枫糖",
        "rarity": 4,
        "tendencies": [{"industry": "farming", "level_1": 10, "level_60": 60}],
        "artworks": [{
            "breakthrough": 1,
            "asset_key": "red-leaf-town/partners/maple/breakthrough-1.webp",
            "width": 900,
            "height": 1600,
            "content_type": "image/webp",
        }],
    })
    script = StoryScript.model_validate({
        "id": "partner_talk",
        "title": "伙伴插话",
        "trigger": {"hook": "cue", "params": {"cue": "action:harvest"}},
        "steps": [
            {"type": "portrait", "slot": "right", "partner_id": "maple", "breakthrough": 1},
            {"type": "dialogue", "speaker": "枫糖", "text": "收成不错。", "focus": "right"},
        ],
    })
    catalog = PartnerCatalog(partners=[partner])
    validate_story_references(StoryCatalog(scripts=[script]), StoryAssetCatalog(), catalog)
    payload = serialize_script(script, StoryAssetCatalog(), catalog)
    assert payload["steps"][0]["asset"]["asset_key"].endswith("breakthrough-1.webp")
    assert payload["steps"][0]["asset"]["layouts"]["stage"]["scale"] == 1.0


def test_missing_partner_artwork_degrades_to_no_portrait():
    partner = PartnerDefinition.model_validate({
        "id": "maple",
        "name": "枫糖",
        "rarity": 4,
        "tendencies": [{"industry": "farming", "level_1": 10, "level_60": 60}],
        "artworks": [],
    })
    script = StoryScript.model_validate({
        "id": "partner_talk",
        "title": "伙伴插话",
        "trigger": {"hook": "cue", "params": {"cue": "action:harvest"}},
        "steps": [
            {"type": "portrait", "slot": "right", "partner_id": "maple"},
            {"type": "dialogue", "speaker": "枫糖", "text": "收成不错。"},
        ],
    })
    payload = serialize_script(script, StoryAssetCatalog(), PartnerCatalog(partners=[partner]))
    assert payload["steps"][0]["asset"] is None


def test_legacy_save_migrates_to_schema_nine():
    player = PlayerState.model_validate({
        "schema_version": 8,
        "player_id": "player-1",
        "oauth_sub": "sub-1",
        "display_name": "小枫",
        "stamina_updated_at": 0,
        "created_at": 0,
        "updated_at": 0,
    })
    assert player.schema_version == 10
    assert player.seen_story_ids == []


def test_duplicate_seen_story_is_rejected():
    with pytest.raises(ValueError):
        PlayerState.model_validate({
            "schema_version": 9,
            "player_id": "player-1",
            "oauth_sub": "sub-1",
            "display_name": "小枫",
            "stamina_updated_at": 0,
            "created_at": 0,
            "updated_at": 0,
            "seen_story_ids": ["hello", "hello"],
        })


def test_repository_round_trips_seen_stories(service):
    service.mark_story_seen("story-sub", "hello")
    player = service.repository.get_by_sub("story-sub")
    restored = PlayerState.model_validate(json.loads(player.model_dump_json()))
    assert restored.seen_story_ids == ["hello"]


def test_story_reward_grants_the_partner_when_it_is_first_finished(service):
    service.story_catalog_loader = lambda: StoryCatalog(scripts=[reward_script()])
    result = service.mark_story_seen("story-sub", "joining")

    assert result["result"]["granted_partners"] == [{"partner_id": "fein", "name": "绯恩"}]
    player = service.repository.get_by_sub("story-sub")
    assert [owned.partner_id for owned in player.owned_partners] == ["fein"]
    assert player.owned_partners[0].acquired_at == 1_700_000_000
    assert [entry["partner_id"] for entry in result["state"]["partners"]] == ["fein"]


def test_story_reward_is_not_granted_twice(service):
    service.story_catalog_loader = lambda: StoryCatalog(scripts=[reward_script()])
    service.mark_story_seen("story-sub", "joining")
    repeated = service.mark_story_seen("story-sub", "joining")

    assert repeated["result"]["granted_partners"] == []
    player = service.repository.get_by_sub("story-sub")
    assert [owned.partner_id for owned in player.owned_partners] == ["fein"]


def test_story_reward_skips_a_partner_the_player_already_owns(service):
    player = service.repository.get_by_sub("story-sub")
    service.admin_grant_partner(player.player_id, "fein")
    service.story_catalog_loader = lambda: StoryCatalog(scripts=[reward_script()])

    result = service.mark_story_seen("story-sub", "joining")
    assert result["result"]["granted_partners"] == []
    assert len(service.repository.get_by_sub("story-sub").owned_partners) == 1


def test_repeatable_story_cannot_carry_rewards():
    with pytest.raises(ValueError):
        reward_script(repeatable=True)


def test_reward_partner_must_exist():
    catalog = StoryCatalog(scripts=[reward_script(partner_id="ghost")])
    with pytest.raises(ValueError):
        validate_story_references(catalog, StoryAssetCatalog(), PartnerCatalog(partners=[partner_definition()]))
    validate_story_references(
        StoryCatalog(scripts=[reward_script()]),
        StoryAssetCatalog(),
        PartnerCatalog(partners=[partner_definition()]),
    )


def test_serialized_script_names_the_partners_it_grants():
    payload = serialize_script(
        reward_script(),
        StoryAssetCatalog(),
        PartnerCatalog(partners=[partner_definition()]),
    )
    assert payload["rewards"] == {"partner_ids": ["fein"], "partner_names": ["绯恩"]}


def test_placeholder_asset_carries_no_image():
    asset = StoryAsset.model_validate({"id": "portal_hollow", "kind": "background", "name": "TODO 传送门空地"})
    assert asset.pending is True
    assert asset.asset_key == ""
    assert background_asset().pending is False


def test_uploaded_asset_still_needs_its_dimensions():
    with pytest.raises(ValueError):
        StoryAsset.model_validate({
            "id": "portal_hollow",
            "kind": "background",
            "name": "传送门空地",
            "asset_key": "red-leaf-town/story/background/portal_hollow.webp",
        })


def test_shipped_opening_hands_over_the_farm_and_fein():
    load_story_catalog.cache_clear()
    script = load_story_catalog().script_map["opening_arrival"]

    assert script.mode == "stage"
    assert script.rewards.partner_ids == ["fein"]
    assert script.trigger.description == "同时满足：收到信号 view:dashboard、均不满足：已经拥有伙伴 fein"
    assert [step.text for step in script.steps if step.type == "dialogue"][-1] == "【伙伴「绯恩」加入了你的队伍】"
    load_story_catalog.cache_clear()


def test_renamed_partner_id_migrates_everywhere():
    player = PlayerState.model_validate({
        "schema_version": 9,
        "player_id": "player-1",
        "oauth_sub": "sub-1",
        "display_name": "小枫",
        "stamina_updated_at": 0,
        "created_at": 0,
        "updated_at": 0,
        "owned_partners": [{"partner_id": "sprite_001", "acquired_at": 0}],
        "gathering_sites": [{
            "site_id": "maple_forest",
            "assigned_partner_ids": ["sprite_001"],
            "task_snapshot": {
                "industry": "gathering",
                "content_id": "collect_maple_wood",
                "production_slot_id": "maple_forest",
                "started_at": 0,
                "ready_at": 600,
                "assigned_partner_ids": ["sprite_001"],
                "support_partner_ids": ["sprite_001"],
                "partner_snapshots": [{
                    "partner_id": "sprite_001",
                    "level": 1,
                    "effective_level": 1,
                    "breakthrough": 0,
                    "ability": 40,
                }],
                "character_ability": 10,
                "total_ability": 50,
                "time_efficiency": 1.0,
                "base_duration": 600,
                "final_duration": 600,
                "produce_item_id": "maple_wood",
                "yield_min": 1,
                "yield_max": 2,
                "harvest_xp": 5,
            },
        }],
    })

    assert player.schema_version == 10
    assert [owned.partner_id for owned in player.owned_partners] == ["fein"]
    site = player.gathering_sites[0]
    assert site.assigned_partner_ids == ["fein"]
    assert site.task_snapshot.assigned_partner_ids == ["fein"]
    assert site.task_snapshot.support_partner_ids == ["fein"]
    assert [entry.partner_id for entry in site.task_snapshot.partner_snapshots] == ["fein"]
