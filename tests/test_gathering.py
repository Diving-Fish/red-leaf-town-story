from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition
from red_leaf_town.partner_traits import record_partner_trait_effect, register_partner_trait


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


class SequenceRandom:
    """按序列返回随机数；randint 取下界，方便断言加权抽取落在哪一项上。"""

    def __init__(self, draws: list[float]):
        self.draws = list(draws)
        self.index = 0

    def randint(self, lower: int, upper: int) -> int:
        return lower

    def random(self) -> float:
        value = self.draws[self.index % len(self.draws)]
        self.index += 1
        return value


class FixedRandom:
    def __init__(self, draw: float):
        self.draw = draw

    def randint(self, lower: int, upper: int) -> int:
        return lower

    def random(self) -> float:
        return self.draw


def partner(partner_id: str, industry: str = "gathering") -> PartnerDefinition:
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": partner_id,
        "rarity": 3,
        "growth_curve": "linear",
        "tendencies": [{"industry": industry, "level_1": 40, "level_60": 120}],
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def gathering_game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    catalog = PartnerCatalog(partners=[partner("gather_one"), partner("gather_two"), partner("farm_only", "farming")])
    service = GameService(
        content,
        repository,
        clock=clock,
        rng=random.Random(9),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("gather-sub", "采集居民")
    for partner_id in ("gather_one", "gather_two", "farm_only"):
        service.admin_grant_partner(player.player_id, partner_id)
    return service, repository, clock, player


def test_gathering_requires_partner_and_locks_it_until_ready(gathering_game):
    service, repository, clock, player = gathering_game
    state = service.snapshot_by_sub("gather-sub")
    assert [site["site_id"] for site in state["gathering_sites"]] == ["maple_forest"]

    with pytest.raises(GameError, match="必须先派"):
        service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    with pytest.raises(GameError, match="没有采集倾向"):
        service.assign_gathering_partner("gather-sub", "maple_forest", "farm_only")

    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    site = started["state"]["gathering_sites"][0]
    assert site["task_snapshot"]["industry"] == "gathering"
    assert site["task_snapshot"]["partner_snapshots"][0]["ability"] > 0
    assert site["task_snapshot"]["quality_parameters"]["ability"] == 40
    assert site["task_snapshot"]["minimum_duration"] == 8 * 3600
    assert site["task_snapshot"]["final_duration"] >= 8 * 3600
    assert len(site["task_snapshot"]["output_pool"]) == 4
    assert site["task_snapshot"]["draw_count"] == 8
    assert started["state"]["player"]["stamina"] == 20
    assert site["assignment_locked"] is True
    assert next(entry for entry in started["state"]["partners"] if entry["partner_id"] == "gather_one")["locked"] is True

    with pytest.raises(GameError, match="不能调整"):
        service.assign_gathering_partner("gather-sub", "maple_forest", "")
    with pytest.raises(GameError, match="暂时不能移动"):
        service.assign_partner("gather-sub", 0, "gather_one")

    clock.advance(site["task_snapshot"]["final_duration"])
    first_results = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_results"]
    second_results = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_results"]
    assert first_results == second_results
    assert first_results[0]["item_id"] == "maple_wood"
    assert all(1 <= result["quality"] <= 5 for result in first_results)
    collected = service.collect_gathering("gather-sub", "maple_forest")
    assert collected["result"]["drops"] == first_results
    assert collected["result"]["partner_experience"] == [{
        "partner_id": "gather_one",
        "experience_gained": site["task_snapshot"]["final_duration"] // (12 * 60),
        "previous_level": 1,
        "level": 2,
        "level_cap": 20,
    }]
    inventory = repository.get(player.player_id).inventory
    for result in first_results:
        assert inventory[result["item_id"]][result["quality"]] == result["quantity"]
    assert collected["state"]["gathering_sites"][0]["empty"] is True


def test_partner_trait_pipeline_modifies_and_freezes_a_task(gathering_game):
    service, _, _, _ = gathering_game
    code = "test_gathering_pipeline"

    @register_partner_trait(
        code,
        "采集管线测试",
        "验证开工与抽取阶段",
        phases=("task_prepare", "output_draw"),
    )
    def apply(context):
        if context["phase"] == "task_prepare":
            context["duration_multiplier"] *= 0.5
            context["draw_bonus"] += 1
            record_partner_trait_effect(context, "duration_multiplier", value=0.5)
        else:
            record_partner_trait_effect(context, "reroll_first_duplicate")

    service.partner_catalog_loader().partner_map["gather_one"].trait_codes = [code]
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    snapshot = started["state"]["gathering_sites"][0]["task_snapshot"]

    assert snapshot["final_duration"] == 15_840
    assert snapshot["draw_count"] == 9
    assert snapshot["world_day"] == started["state"]["world"]["day"]
    assert snapshot["weather_id"] == started["state"]["world"]["weather"]["id"]
    assert [entry["effect"] for entry in snapshot["applied_effects"]] == [
        "duration_multiplier",
        "reroll_first_duplicate",
    ]


def test_real_duration_trait_can_break_the_original_task_minimum(gathering_game):
    service, _, _, _ = gathering_game
    service.partner_catalog_loader().partner_map["gather_one"].trait_codes = ["swift_wind_work"]
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")

    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    snapshot = started["state"]["gathering_sites"][0]["task_snapshot"]

    assert snapshot["final_duration"] < service.content.gathering_task_map["collect_maple_wood"].minimum_duration_seconds
    assert snapshot["minimum_duration"] == snapshot["final_duration"]
    assert any(
        entry.get("trait_code") == "swift_wind_work"
        and entry.get("effect") == "duration_multiplier"
        for entry in snapshot["applied_effects"]
    )


def test_fein_varied_forage_is_frozen_into_the_gathering_task(gathering_game):
    service, _, _, _ = gathering_game
    service.partner_catalog_loader().partner_map["gather_one"].trait_codes = ["varied_forage"]
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")

    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    snapshot = started["state"]["gathering_sites"][0]["task_snapshot"]

    assert any(
        entry.get("trait_code") == "varied_forage"
        and entry.get("effect") == "reroll_first_duplicate"
        for entry in snapshot["applied_effects"]
    )


def test_luo_nali_freezes_the_current_medicine_candidates(gathering_game):
    service, repository, _, player = gathering_game
    service.partner_catalog_loader().partner_map["gather_one"].trait_codes = ["herb_lore"]
    repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    service.snapshot_by_sub("gather-sub")
    service.assign_gathering_partner("gather-sub", "dew_meadow", "gather_one")

    started = service.start_gathering("gather-sub", "dew_meadow", "collect_autumn_herb")
    snapshot = next(
        site["task_snapshot"]
        for site in started["state"]["gathering_sites"]
        if site["site_id"] == "dew_meadow"
    )
    effect = next(
        entry
        for entry in snapshot["applied_effects"]
        if entry.get("trait_code") == "herb_lore"
    )

    assert effect["effect"] == "guarantee_tagged_output"
    assert set(effect["params"]["eligible_item_ids"]) == {
        "autumn_herb",
        "morning_dew_flower",
        "silver_star_moss",
    }


def test_gathering_capacity_is_derived_from_talent_tree(gathering_game):
    service, repository, _, player = gathering_game
    service.snapshot_by_sub("gather-sub")
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")

    repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    level_two = service.snapshot_by_sub("gather-sub")
    assert level_two["player"]["level"] == 2
    assert level_two["talents"]["available_points"] == 1
    assert level_two["industry_rules"]["gathering"]["partner_capacity"] == 1
    with pytest.raises(GameError, match="编制已满"):
        service.assign_gathering_partner("gather-sub", "dew_meadow", "gather_two")

    unlocked = service.unlock_talent("gather-sub", "gathering_roster_1")
    assert unlocked["state"]["talents"]["available_points"] == 0
    assert unlocked["state"]["industry_rules"]["gathering"]["partner_capacity"] == 2
    assigned = service.assign_gathering_partner("gather-sub", "dew_meadow", "gather_two")
    assert len([site for site in assigned["state"]["gathering_sites"] if site["assigned_partner_ids"]]) == 2


@pytest.mark.parametrize(("draw", "expected_id"), [
    (0.0, "maple_wood"),
    (0.6, "woodland_mushroom"),
    (0.9, "maple_resin"),
    (0.99, "amber_beeswax"),
])
def test_每次抽取按权重命中池中的一项(gathering_game, draw, expected_id):
    service, _, clock, _ = gathering_game
    service.rng = FixedRandom(draw)
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")

    clock.advance(started["result"]["final_duration"])
    results = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_results"]

    assert [result["item_id"] for result in results] == [expected_id]
    assert sum(result["quantity"] for result in results) == started["result"]["draw_count"]


def test_exploration_draw_count_and_quality_both_scale_with_ability(gathering_game):
    service, repository, _, player = gathering_game

    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    weak = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")["result"]

    repository.update(player.player_id, lambda state: setattr(state.owned_partners[0], "level", 60))
    repository.update(player.player_id, lambda state: setattr(state.gathering_sites[0], "task_snapshot", None))
    strong = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")["result"]

    assert weak["total_ability"] == 40
    assert strong["total_ability"] == 66
    assert weak["draw_count"] == 8
    assert strong["draw_count"] == 9
    assert strong["quality_ability"] > weak["quality_ability"]


def test_gathering_draws_split_into_one_stack_per_item_and_quality(gathering_game):
    service, _, clock, _ = gathering_game
    service.rng = SequenceRandom([0.0, 0.6])
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")

    clock.advance(started["result"]["final_duration"])
    results = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_results"]

    stacks = [(result["item_id"], result["quality"]) for result in results]
    assert {item_id for item_id, _ in stacks} == {"maple_wood", "woodland_mushroom"}
    assert len(stacks) == len(set(stacks))
    assert sum(result["quantity"] for result in results) == started["result"]["draw_count"]


def test_quality_gathering_material_can_be_sold_by_exact_grade(gathering_game):
    service, repository, _, player = gathering_game
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {3: 2}}))
    sold = service.sell("gather-sub", "maple_wood", 1, 3)
    assert sold["result"]["quality_name"] == "上品"
    assert sold["result"]["unit_price"] == 9


def test_legacy_single_gathering_result_migrates_to_drop_list():
    player = PlayerState.model_validate({
        "schema_version": 11,
        "player_id": "legacy-gathering-result",
        "oauth_sub": "legacy-gathering-result-sub",
        "display_name": "旧采集居民",
        "stamina_updated_at": 1,
        "created_at": 1,
        "updated_at": 1,
        "gathering_sites": [{
            "site_id": "maple_forest",
            "task_result": {"item_id": "maple_wood", "quantity": 2, "quality": 3, "resolved_at": 1},
        }],
    })

    assert player.schema_version == PlayerState.model_fields["schema_version"].default
    assert [result.model_dump() for result in player.gathering_sites[0].task_results] == [
        {"item_id": "maple_wood", "quantity": 2, "quality": 3, "resolved_at": 1},
    ]


def test_legacy_running_gathering_task_without_pool_still_resolves(gathering_game):
    service, repository, clock, player = gathering_game
    service.rng = FixedRandom(0)
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")
    started = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    repository.update(player.player_id, lambda state: setattr(state.gathering_sites[0].task_snapshot, "output_pool", []))

    clock.advance(started["result"]["final_duration"])
    results = service.snapshot_by_sub("gather-sub")["gathering_sites"][0]["task_results"]

    assert [result["item_id"] for result in results] == ["maple_wood"]


def test_maple_wind_whistle_cuts_below_the_minimum_duration(gathering_game):
    service, repository, clock, player = gathering_game
    task = service.content.gathering_task_map["collect_maple_wood"]
    service.assign_gathering_partner("gather-sub", "maple_forest", "gather_one")

    def raise_partner(state):
        owned = next(entry for entry in state.owned_partners if entry.partner_id == "gather_one")
        owned.level = 60
        owned.breakthrough = 2

    repository.update(player.player_id, raise_partner)

    plain = service.start_gathering("gather-sub", "maple_forest", "collect_maple_wood")
    plain_duration = plain["state"]["gathering_sites"][0]["task_snapshot"]["final_duration"]
    assert plain_duration == task.minimum_duration_seconds
    service.cancel_task("gather-sub", "gathering", "maple_forest")

    repository.update(player.player_id, lambda state: state.task_items.update({"maple_wind_whistle": 1}))
    boosted = service.start_gathering(
        "gather-sub",
        "maple_forest",
        "collect_maple_wood",
        "maple_wind_whistle",
    )
    snapshot = boosted["state"]["gathering_sites"][0]["task_snapshot"]

    assert snapshot["final_duration"] == round(plain_duration * 0.7)
    assert snapshot["final_duration"] < task.minimum_duration_seconds
    assert snapshot["minimum_duration"] == snapshot["final_duration"]
    assert snapshot["applied_effects"][0]["task_item_id"] == "maple_wind_whistle"
    assert "maple_wind_whistle" not in repository.get(player.player_id).task_items

def test_player_rejects_partner_assigned_across_farm_and_gathering():
    with pytest.raises(ValidationError, match="more than one production slot"):
        PlayerState.model_validate({
            "player_id": "cross-industry",
            "oauth_sub": "cross-industry-sub",
            "display_name": "重复派驻",
            "stamina_updated_at": 1,
            "created_at": 1,
            "updated_at": 1,
            "owned_partners": [{"partner_id": "worker", "acquired_at": 1}],
            "plots": [{"slot": 0, "assigned_partner_ids": ["worker"]}],
            "gathering_sites": [{"site_id": "maple_forest", "assigned_partner_ids": ["worker"]}],
        })
