from __future__ import annotations

from math import exp
from random import Random, SystemRandom


QUALITY_NAMES = {
    1: "普通",
    2: "良品",
    3: "上品",
    4: "臻品",
    5: "奇迹",
}


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = exp(-value)
        return 1 / (1 + inverse)
    direct = exp(value)
    return direct / (1 + direct)


def quality_probabilities(
    ability: int | float,
    thresholds: list[int | float],
    width: int | float,
    miracle_probability_cap: float,
    miracle_eligible: bool,
    *,
    miracle_width_multiplier: float = 1,
    ignore_miracle_cap: bool = False,
) -> list[float]:
    if len(thresholds) != 4:
        raise ValueError("quality thresholds must contain T2 through T5")
    if list(thresholds) != sorted(thresholds) or len(set(thresholds)) != 4:
        raise ValueError("quality thresholds must be strictly increasing")
    if width <= 0:
        raise ValueError("quality width must be positive")
    if not 0 <= miracle_probability_cap <= 0.01:
        raise ValueError("miracle probability cap must be between 0 and 0.01")
    if miracle_width_multiplier < 1:
        raise ValueError("miracle width multiplier must be at least one")

    g2, g3, g4 = [
        _sigmoid((float(ability) - float(threshold)) / float(width))
        for threshold in thresholds[:3]
    ]
    g5 = 0.0
    if miracle_eligible:
        curve = _sigmoid(
            (float(ability) - float(thresholds[3]))
            / (float(width) * miracle_width_multiplier)
        )
        g5 = min(g4, curve if ignore_miracle_cap else miracle_probability_cap * curve)
    probabilities = [1 - g2, g2 - g3, g3 - g4, g4 - g5, g5]
    return [max(0.0, min(1.0, probability)) for probability in probabilities]


def roll_quality(rng: Random | SystemRandom, probabilities: list[float]) -> int:
    if len(probabilities) != 5 or abs(sum(probabilities) - 1.0) > 1e-8:
        raise ValueError("quality probabilities must contain five values summing to one")
    draw = rng.random()
    cumulative = 0.0
    for quality, probability in enumerate(probabilities, start=1):
        cumulative += probability
        if draw < cumulative:
            return quality
    return 5
