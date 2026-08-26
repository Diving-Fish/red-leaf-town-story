"""算钓点的体力→金币期望，供数值调参参考。

用的是线上那套内容与公式：抽取次数、聚鱼度权重、品质曲线、售价倍率全部走 GameContent
和 GameService 的同一段代码，改了数据重跑这个脚本就是新表。

    venv/bin/python scripts/fishing_yield.py
"""

from __future__ import annotations

import sys
from math import floor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from red_leaf_town.application.service import GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.quality import quality_probabilities


ABILITIES = (0, 40, 80, 120)


def unit_price(service, base_price: int, probabilities: list[float], has_quality: bool) -> float:
    """probabilities 是 5 项，第 i 项对应品质 i+1。无品质物品按标价算。"""
    if not has_quality:
        return float(base_price)
    return sum(
        probability * service._quality_unit_price(base_price, quality)
        for quality, probability in enumerate(probabilities, start=1)
        if probability
    )


def cast_yield(service, spot, ability: int, combo: int) -> dict:
    items = service.content.item_map
    draws = service._fishing_draw_count(spot, ability, combo)
    pool = service._fishing_pool(spot, combo)
    total_weight = sum(weight for _, weight, _ in pool)
    probabilities = quality_probabilities(
        ability,
        spot.quality.thresholds,
        spot.quality.width,
        spot.quality.miracle_probability_cap,
        spot.quality.miracle_eligible,
    )

    per_draw = 0.0
    hook_probability = 0.0
    for entry, weight, is_big in pool:
        share = weight / total_weight
        if is_big:
            hook_probability = share
            continue
        item = items[entry.item_id]
        quantity = (entry.quantity_min + entry.quantity_max) / 2
        per_draw += share * quantity * unit_price(service, item.sell_price, probabilities, item.has_quality)

    coins = draws * per_draw
    fallback = items[spot.big_catch.fallback_item_id] if spot.big_catch else None
    hooked = 1 - (1 - hook_probability) ** draws if spot.big_catch else 0.0
    if spot.big_catch:
        # 一竿只挂一条大物，多抽到的按退回的普通鱼发放。
        extra = draws * hook_probability - hooked
        coins += extra * unit_price(service, fallback.sell_price, probabilities, fallback.has_quality)
    return {
        "draws": draws,
        "coins": coins,
        "per_stamina": coins / spot.stamina_cost,
        "hooked": hooked,
        "probabilities": probabilities,
    }


def fight_yield(service, spot, ability: int, probabilities: list[float]) -> dict:
    big = spot.big_catch
    items = service.content.item_map
    chance = big.success_chance(ability)
    giant = items[big.item_id]
    fallback = items[big.fallback_item_id]
    # 大物保底 min_quality：低于保底的那几档全部并到保底那一档上。
    forced = [
        probability if quality > big.min_quality else 0.0
        for quality, probability in enumerate(probabilities, start=1)
    ]
    forced[big.min_quality - 1] = sum(probabilities[: big.min_quality])
    win = unit_price(service, giant.sell_price, forced, giant.has_quality)
    lose = unit_price(service, fallback.sell_price, probabilities, fallback.has_quality)
    gain = chance * (win - lose)
    return {
        "chance": chance,
        "win": win,
        "lose": lose,
        "gain": gain,
        "per_stamina": gain / big.stamina_cost,
    }


def main() -> None:
    content = load_content()
    service = GameService.__new__(GameService)
    service.content = content
    cap = content.fishing_combo.max_layers

    for spot in content.fishing_spots:
        print(f"== {spot.name}（{spot.min_level} 级，{spot.stamina_cost} 体力/轮，{spot.cast_xp} 经验）")
        print(f"{'能力':>4} {'聚鱼度':>6} {'抽取':>4} {'每轮金币':>9} {'每体力':>7} {'咬钩率':>7}")
        for ability in ABILITIES:
            for combo in (0, cap):
                result = cast_yield(service, spot, ability, combo)
                print(
                    f"{ability:>4} {combo:>6} {result['draws']:>4} "
                    f"{result['coins']:>9.1f} {result['per_stamina']:>7.1f} {result['hooked'] * 100:>6.1f}%"
                )
        if spot.big_catch:
            print(f"   大物 {content.item_map[spot.big_catch.item_id].name}（{spot.big_catch.stamina_cost} 体力）")
            for ability in ABILITIES:
                base = cast_yield(service, spot, ability, 0)
                fight = fight_yield(service, spot, ability, base["probabilities"])
                print(
                    f"   能力 {ability:>3}：成功率 {fight['chance'] * 100:>4.1f}% · "
                    f"搏中 {fight['win']:>7.1f} · 放线 {fight['lose']:>5.1f} · "
                    f"净期望 {fight['gain']:>7.1f} · 每体力 {fight['per_stamina']:>6.1f}"
                )
        print()


if __name__ == "__main__":
    main()
