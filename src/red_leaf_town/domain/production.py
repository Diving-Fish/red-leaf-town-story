from __future__ import annotations

from math import floor
from random import Random, SystemRandom

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
) -> list[ProductionResultSnapshot]:
    """把若干 (物品, 数量) 批次按单件品质展开，并按物品出现顺序与品质档位合并。"""

    order: list[str] = []
    tally: dict[str, dict[int, int]] = {}
    for item_id, quantity in batches:
        if item_id not in tally:
            order.append(item_id)
            tally[item_id] = {}
        counts = tally[item_id]
        for quality, amount in roll_unit_qualities(rng, quantity, probabilities).items():
            counts[quality] = counts.get(quality, 0) + amount
    return [
        ProductionResultSnapshot(
            item_id=item_id,
            quantity=tally[item_id][quality],
            quality=quality,
            resolved_at=resolved_at,
        )
        for item_id in order
        for quality in sorted(tally[item_id])
    ]
