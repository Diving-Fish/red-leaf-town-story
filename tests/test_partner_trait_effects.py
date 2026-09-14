from __future__ import annotations

import pytest

from red_leaf_town.domain import TaskOutputSnapshot
from red_leaf_town.domain.production import build_results, draw_weighted_batches
from red_leaf_town.partner_traits import execute_partner_traits


class SequenceRandom:
    def __init__(self, draws: list[float]):
        self.draws = draws
        self.index = 0

    def random(self) -> float:
        value = self.draws[self.index % len(self.draws)]
        self.index += 1
        return value

    def randint(self, lower: int, upper: int) -> int:
        return lower


@pytest.mark.parametrize("quality", [1, 2, 3, 4, 5])
def test_azure_smelt_only_guarantees_fine_quality(quality):
    context = {
        "phase": "result_finalize",
        "industry": "crafting",
        "source_partner_id": "nuanyu_2",
        "applied_effects": [],
    }
    execute_partner_traits(["azure_smelt"], context)
    results = build_results(
        SequenceRandom([0]),
        [("maple_plank", 1)],
        [float(tier == quality) for tier in range(1, 6)],
        100,
        context["applied_effects"],
    )
    assert [(entry.quality, entry.quantity) for entry in results] == [(max(2, quality), 1)]


def test_quality_floor_only_promotes_one_unit_in_a_batch():
    results = build_results(
        SequenceRandom([0]),
        [("maple_plank", 3)],
        [1, 0, 0, 0, 0],
        100,
        [{"effect": "promote_lowest_quality", "params": {"levels": 0, "minimum": 2}}],
    )
    assert [(entry.quality, entry.quantity) for entry in results] == [(1, 2), (2, 1)]


@pytest.mark.parametrize("params", [{}, {"levels": 1, "minimum": 2}])
def test_existing_quality_promotion_snapshots_still_raise_one_level(params):
    results = build_results(
        SequenceRandom([0]),
        [("maple_plank", 1)],
        [0, 0, 0, 1, 0],
        100,
        [{"effect": "promote_lowest_quality", "params": params}],
    )
    assert [(entry.quality, entry.quantity) for entry in results] == [(5, 1)]


def output(item_id: str, weight: float) -> TaskOutputSnapshot:
    return TaskOutputSnapshot(
        item_id=item_id,
        weight=weight,
        quantity_min=1,
        quantity_max=1,
    )


def test_first_duplicate_draw_is_rerolled_with_frozen_pool_weights():
    pool = [output("common", 80), output("rare", 20)]
    effects = [{"effect": "reroll_first_duplicate"}]
    batches = draw_weighted_batches(SequenceRandom([0.0, 0.0, 0.5]), pool, 2, effects)
    assert batches == [("common", 1), ("rare", 1)]


def test_guaranteed_tagged_output_replaces_the_last_draw_from_frozen_candidates():
    pool = [
        output("tough_fodder", 50),
        output("autumn_herb", 30),
        output("morning_dew_flower", 15),
        output("silver_star_moss", 5),
    ]
    effects = [{
        "effect": "guarantee_tagged_output",
        "params": {
            "tag": "medicine",
            "count": 1,
            "eligible_item_ids": ["autumn_herb", "morning_dew_flower", "silver_star_moss"],
        },
    }]

    batches = draw_weighted_batches(SequenceRandom([0.0]), pool, 3, effects)

    assert batches[:2] == [("tough_fodder", 1), ("tough_fodder", 1)]
    assert batches[2][0] in {"autumn_herb", "morning_dew_flower", "silver_star_moss"}


def test_quality_and_result_effects_share_one_post_processing_pipeline():
    effects = [
        {"effect": "reroll_one_quality_take_higher", "params": {"count": 1}},
        {"effect": "promote_lowest_quality", "params": {"minimum": 3, "chance": 1}},
    ]
    results = build_results(
        SequenceRandom([0.25, 0.75]),
        [("maple_wood", 1)],
        [0.5, 0.5, 0, 0, 0],
        100,
        effects,
    )
    assert [(entry.item_id, entry.quantity, entry.quality) for entry in results] == [
        ("maple_wood", 1, 3),
    ]
