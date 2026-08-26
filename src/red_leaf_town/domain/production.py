from __future__ import annotations

from math import floor
from random import Random, SystemRandom
from typing import Any, Iterable

from .models import ProductionResultSnapshot, TaskOutputSnapshot
from .quality import roll_quality


def draw_count(
    ability: int | float,
    base_draws: int,
    ability_bonus: float,
    difficulty: int | float,
) -> int:
    """探索抽取次数：与时间效率同型的饱和曲线，能力越高抽得越多，但存在天然上限。"""

    if base_draws < 1:
        raise ValueError("base draws must be positive")
    if ability_bonus < 0:
        raise ValueError("ability bonus cannot be negative")
    if difficulty <= 0:
        raise ValueError("draw difficulty must be positive")
    ability = max(0.0, float(ability))
    multiplier = 1 + ability_bonus * ability / (ability + float(difficulty))
    return max(1, floor(base_draws * multiplier + 0.5))


def pick_weighted(rng: Random | SystemRandom, pool: list[TaskOutputSnapshot]) -> TaskOutputSnapshot:
    total = sum(entry.weight for entry in pool)
    if total <= 0:
        raise ValueError("weighted pool must contain at least one positive weight")
    draw = rng.random() * total
    cumulative = 0.0
    for entry in pool:
        cumulative += entry.weight
        if draw < cumulative:
            return entry
    return pool[-1]


def has_effect(applied_effects: Iterable[dict[str, Any]], effect: str) -> bool:
    return any(entry.get("effect") == effect for entry in applied_effects)


def draw_weighted_batches(
    rng: Random | SystemRandom,
    pool: list[TaskOutputSnapshot],
    count: int,
    applied_effects: Iterable[dict[str, Any]] = (),
) -> list[tuple[str, int]]:
    """按快照权重抽取批次，并在抽取阶段应用已经冻结的效果。"""

    effects = list(applied_effects)
    reroll_first_duplicate = has_effect(effects, "reroll_first_duplicate")
    reroll_used = False
    seen_item_ids: set[str] = set()
    batches: list[tuple[str, int]] = []
    for _ in range(max(0, count)):
        output = pick_weighted(rng, pool)
        if reroll_first_duplicate and not reroll_used and output.item_id in seen_item_ids:
            alternatives = [
                entry
                for entry in pool
                if entry.item_id not in seen_item_ids and entry.weight > 0
            ]
            if alternatives:
                output = pick_weighted(rng, alternatives)
                reroll_used = True
        seen_item_ids.add(output.item_id)
        batches.append((output.item_id, rng.randint(output.quantity_min, output.quantity_max)))
    for entry in effects:
        if entry.get("effect") != "guarantee_tagged_output":
            continue
        params = entry.get("params") or {}
        eligible_item_ids = {
            str(item_id)
            for item_id in params.get("eligible_item_ids", ())
            if str(item_id)
        }
        eligible_pool = [
            output
            for output in pool
            if output.item_id in eligible_item_ids and output.weight > 0
        ]
        if not eligible_pool:
            continue
        required = max(1, int(params.get("count", 1)))
        present = sum(item_id in eligible_item_ids for item_id, _ in batches)
        while present < required:
            replace_at = next(
                (
                    index
                    for index in range(len(batches) - 1, -1, -1)
                    if batches[index][0] not in eligible_item_ids
                ),
                None,
            )
            if replace_at is None:
                break
            output = pick_weighted(rng, eligible_pool)
            batches[replace_at] = (
                output.item_id,
                rng.randint(output.quantity_min, output.quantity_max),
            )
            present += 1
    return batches


def roll_unit_qualities(
    rng: Random | SystemRandom,
    quantity: int,
    probabilities: list[float],
) -> dict[int, int]:
    """每一件产物单独判定品质，返回品质到件数的映射。"""

    counts: dict[int, int] = {}
    for _ in range(max(0, quantity)):
        quality = roll_quality(rng, probabilities)
        counts[quality] = counts.get(quality, 0) + 1
    return counts


def build_results(
    rng: Random | SystemRandom,
    batches: list[tuple[str, int]],
    probabilities: list[float],
    resolved_at: int,
    applied_effects: Iterable[dict[str, Any]] = (),
) -> list[ProductionResultSnapshot]:
    """把批次按单件品质展开，并统一应用品质与最终产出阶段的快照效果。"""

    effects = list(applied_effects)
    best_of_two_remaining = sum(
        max(1, int((entry.get("params") or {}).get("count", 1)))
        for entry in effects
        if entry.get("effect") == "reroll_one_quality_take_higher"
    )
    order: list[str] = []
    tally: dict[str, dict[int, int]] = {}
    for item_id, quantity in batches:
        if item_id not in tally:
            order.append(item_id)
            tally[item_id] = {}
        counts = tally[item_id]
        for _ in range(max(0, quantity)):
            quality = roll_quality(rng, probabilities)
            if best_of_two_remaining > 0:
                quality = max(quality, roll_quality(rng, probabilities))
                best_of_two_remaining -= 1
            counts[quality] = counts.get(quality, 0) + 1
    results = [
        ProductionResultSnapshot(
            item_id=item_id,
            quantity=tally[item_id][quality],
            quality=quality,
            resolved_at=resolved_at,
        )
        for item_id in order
        for quality in sorted(tally[item_id])
    ]
    for entry in effects:
        if entry.get("effect") != "promote_lowest_quality":
            continue
        params = entry.get("params") or {}
        chance = float(params.get("chance", entry.get("value", 1)))
        if chance < 1 and rng.random() >= max(0.0, chance):
            continue
        eligible = [result for result in results if result.quality < 5 and result.quantity > 0]
        if not eligible:
            continue
        target = min(eligible, key=lambda result: (result.quality, order.index(result.item_id)))
        levels = max(1, int(params.get("levels", 1)))
        minimum = max(1, min(5, int(params.get("minimum", 1))))
        promoted_quality = min(5, max(target.quality + levels, minimum))
        target.quantity -= 1
        promoted = next(
            (
                result
                for result in results
                if result.item_id == target.item_id and result.quality == promoted_quality
            ),
            None,
        )
        if promoted is None:
            results.append(ProductionResultSnapshot(
                item_id=target.item_id,
                quantity=1,
                quality=promoted_quality,
                resolved_at=resolved_at,
            ))
        else:
            promoted.quantity += 1
        results = [result for result in results if result.quantity > 0]
        results.sort(key=lambda result: (order.index(result.item_id), result.quality))
    return results
