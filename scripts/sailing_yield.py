"""远航与现有产业的体力收益；运行后输出可复现的 Markdown 表。"""
from __future__ import annotations

import sys
from collections import defaultdict
from itertools import permutations, product
from math import floor, perm
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from red_leaf_town.application.sailing import sailing_output_pool
from red_leaf_town.application.service import GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.production import draw_count
from red_leaf_town.domain.quality import quality_probabilities
from red_leaf_town.sailing_content import load_sailing_content


def quality_price(service, item, curve, ability):
    if not item.has_quality:
        return item.sell_price
    probabilities = quality_probabilities(ability, curve.thresholds, curve.width,
                                         curve.miracle_probability_cap, curve.miracle_eligible)
    return sum(p * service._quality_unit_price(item.sell_price, q)
               for q, p in enumerate(probabilities, 1))


def event_bonuses(route, modifier=0, protect=False):
    """枚举事件顺序与成功组合，包含风浪使额外抽取减少的实际规则。"""
    chance = sum(roll == 20 or (roll != 1 and roll + modifier >= 12) for roll in range(1, 21)) / 20
    result = defaultdict(float)
    for events in permutations(('shoal', 'fog', 'squall', 'drift'), route.events):
        for successes in product((False, True), repeat=route.events):
            bonus, probability = 0, 1 / perm(4, route.events)
            for event, success in zip(events, successes):
                probability *= chance if success else 1 - chance
                if success:
                    bonus += max(1, route.draws.base_draws // 8)
                elif event == 'squall' and not protect:
                    bonus = max(0, bonus - max(1, route.draws.base_draws // 8))
            result[bonus] += probability
    return result


def sailing_yield(service, route, ability=0, farming_ability=0, cargo=0, nets=0, supply='none', modifier=0):
    content = service.content
    supplies = {s.id: s for s in load_sailing_content().supplies}
    selected = supplies[supply]
    supply_cost = (selected.quantity * content.item_map[selected.item_id].sell_price) if selected.item_id else 0
    base = route.draws.base_draws
    draws = draw_count(ability, base, route.draws.ability_bonus, route.draws.difficulty)
    draws += round(base * (cargo * 0.1 + (0.2 if selected.effect == 'quantity' else 0)))
    crops = {c.seed_item_id: c for c in content.crops}
    curves = {o.item_id: o.quality for o in route.outputs}
    direct, grown, plant_stamina = 0., 0., 0.
    for bonus, chance in event_bonuses(route, modifier, selected.effect == 'protect').items():
        count = draws + bonus
        pool = sailing_output_pool(route, count, route.stamina, nets, selected.effect == 'rare')
        total = sum(o.weight for o in pool)
        for output in pool:
            amount = chance * count * output.weight / total * (output.quantity_min + output.quantity_max) / 2
            item = content.item_map[output.item_id]
            direct += amount * quality_price(service, item, curves[output.item_id], ability)
            if output.item_id in crops:
                crop = crops[output.item_id]
                produce = content.item_map[crop.produce_item_id]
                grown += amount * (crop.yield_min + crop.yield_max) / 2 * quality_price(service, produce, crop.quality, farming_ability)
                plant_stamina += amount * crop.stamina_cost
    net = direct - route.coins - supply_cost
    return net / route.stamina, (net + grown) / (route.stamina + plant_stamina)


def main():
    from fishing_yield import cast_yield
    service = GameService.__new__(GameService)
    service.content = load_content()
    print('# 远航体力收益验算\n')
    print('按当前配置精确枚举事件顺序与成功组合，抽取复用生产代码的次数和权重公式。单位均为红叶币/体力。\n')
    print('远航净收益扣除船费、补给普通品质的出售机会成本；直接收益计入远航物产品质售价，完整链计入树果品质售价与种植体力。装备按出售价值计入。基础事件调整值 0，满改装取 4；航海能力与农业能力按同档比较。不含天赋、特性、任务道具、造船与改装一次性成本和土地/伙伴占用的时间机会成本。\n')
    print('| 能力 | 航线 | 基础直接出售 | 基础含种植 | 满改装含种植 | 满改装最优补给含种植 |\n|---:|---|---:|---:|---:|---:|')
    for ability in (0, 40, 80, 120):
        for route in load_sailing_content().routes:
            direct, chain = sailing_yield(service, route, ability, ability)
            upgraded = sailing_yield(service, route, ability, ability, 3, 3, modifier=4)[1]
            best = max(sailing_yield(service, route, ability, ability, 3, 3, s.id, 4)[1] for s in load_sailing_content().supplies)
            print(f'| {ability} | {route.name} | {direct:.1f} | {chain:.1f} | {upgraded:.1f} | {best:.1f} |')
    print('\n| 能力 | 现有产业 | 基础收益 | 满聚鱼收益 |\n|---:|---|---:|---:|')
    for ability in (0, 40, 80, 120):
        for spot in service.content.fishing_spots:
            print(f'| {ability} | 钓鱼·{spot.name} | {cast_yield(service, spot, ability, 0)["per_stamina"]:.1f} | {cast_yield(service, spot, ability, service.content.fishing_combo.max_layers)["per_stamina"]:.1f} |')
        for task in service.content.mining_tasks:
            efficiency = 1 + task.yield_bonus * ability / (ability + task.yield_difficulty)
            quantity = (floor(task.yield_min * efficiency) + floor(task.yield_max * efficiency)) / 2
            price = quality_price(service, service.content.item_map[task.produce_item_id], task.quality, ability)
            print(f'| {ability} | 采矿·{task.name} | {quantity * price / task.stamina_cost:.1f} | — |')
    print('\n探秘灵果草甸历史模拟的含种植净收益约 75 币/体力，见 [探秘数值文档](delve-dungeon.md#这条链的收支)，属于有战斗风险的参考口径，本脚本不重新模拟其战斗。')
    print('\n| 压力场景（满改装、最优补给） | 芦苇海湾 | 白帆渔场 | 雾灯群岛 |\n|---|---:|---:|---:|')
    for label, ability, farming, modifier in (
        ('航海能力 0 / 农业 120 / 调整值 4', 0, 120, 4),
        ('双能力 240 / 调整值 8', 240, 240, 8),
        ('双能力趋于极限 / 调整值 20', 1_000_000, 1_000_000, 20),
    ):
        yields = [max(sailing_yield(service, route, ability, farming, 3, 3, supply.id, modifier)[1]
                      for supply in load_sailing_content().supplies) for route in load_sailing_content().routes]
        print('| ' + label + ' | ' + ' | '.join(f'{value:.1f}' for value in yields) + ' |')
    print('\n验收边界：能力 0/40/80/120 各档，基础完整链保持在红叶湖基础钓鱼的 0.65～1.3 倍内；满改装、所有补给选择不超过同档满聚鱼红叶湖的 1.7 倍。低能力满改装有一定投入回报，高能力不会取代钓鱼。自动化测试守住这两条边界。压力场景仅检查公式，不代表当前可达到的队伍。')
    print('\n装备：每航次至少出一件的概率为实际扣除体力 / 250。若最终抽取 n 次，则单抽装备概率 p = 1 − (1 − 体力 / 250)^(1/n)，装备权重 = 其余权重总和 × p / (1 − p)。全部产出统一加权抽取，没有额外独立装备骰。故重复同航线的首次获取期望为 250 体力；试航也按实际 1 体力校准。权重随本次抽数冻结，不随玩家未出货次数变化，无保底。')
    print('\n树果：千香果 8 体力、2 果、单价 1600；椰木果 12 体力、2 果、单价 2400。均为 24 小时生长、12 小时下限，与桃桃果/莓莓果同品质曲线，普通品质种植毛收益均为 400 币/体力；必须连同获取种子的远航成本评估。')


if __name__ == '__main__':
    main()
