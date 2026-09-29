"""Seasonal quantity bonuses, rounded once across the entire reward batch."""

from math import floor


def scale_quantities(quantities: list[int], multiplier: float) -> list[int]:
    result = list(quantities)
    if not result or multiplier <= 1:
        return result
    extra = max(0, floor(sum(result) * multiplier + 0.5) - sum(result))
    order = sorted(range(len(result)), key=lambda i: (-result[i], i))
    for index in range(extra):
        result[order[index % len(order)]] += 1
    return result
