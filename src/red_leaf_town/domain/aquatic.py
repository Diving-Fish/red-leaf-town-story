"""资产轴生产格的纯逻辑：分段结算、槽的投料、聚鱼度衰减。

资产格与任务型生产格的区别在于它没有完成时间：鱼塘一直在跑，玩家随时会换伙伴、投料、
捞鱼。所以这里的入口只有一个 —— 任何变更之前，先用【旧参数】把状态推进到当前时刻，
再写入新参数。推进是纯函数，按周期离散进行，余数留在 settle_remainder 里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, floor

from .models import FryBatchState, PondState, SlotState


SECONDS_PER_HOUR = 3600
MAX_SETTLE_CYCLES = 100_000
MAX_FRY_BATCHES = 48


class SlotError(ValueError):
    pass


@dataclass
class PondParameters:
    """一口塘在这一段时间里生效的参数快照。"""

    cycle_seconds: int
    capacity: int
    growth_rate: float
    maturation_cycles: float
    steady_ratio: float
    generation_gain: float
    generation_decay: float
    generation_cap: float
    feed_per_cycle: float

    @property
    def steady_stock(self) -> int:
        """稳态门槛只数成鱼：鱼苗占容量，但不算数量稳定下来的鱼群。"""

        return max(1, ceil(self.capacity * self.steady_ratio))


@dataclass
class PondAdvance:
    cycles: int = 0
    paid_cycles: int = 0
    spawned: int = 0
    matured: int = 0
    generation_gained: float = 0.0
    generation_lost: float = 0.0
    fed_seconds: int = 0
    stalled: bool = False


@dataclass
class AquaticSettlement:
    consumed_units: float = 0.0
    stalled: bool = False
    ponds: dict[str, PondAdvance] = field(default_factory=dict)


def pond_cycle_seconds(base_cycle_seconds: int, ability: int | float, time_difficulty: int) -> int:
    """周期 T = 基础周期 / η，η = 1 + 2A/(A + 时间难度)，η 封顶 3。"""

    if base_cycle_seconds <= 0:
        raise ValueError("pond base cycle must be positive")
    if time_difficulty <= 0:
        raise ValueError("pond time difficulty must be positive")
    ability = max(0.0, float(ability))
    efficiency = min(3.0, 1 + 2 * ability / (ability + time_difficulty))
    return max(1, ceil(base_cycle_seconds / efficiency))


def add_fry(pond: PondState, count: int, cycles_left: float) -> None:
    """入池。同一时刻投入或者出生的鱼苗成熟时间相同，合成一批，避免批次无谓增长。"""

    if count <= 0 or cycles_left <= 0:
        return
    for batch in pond.fry:
        if abs(batch.cycles_left - cycles_left) < 1e-6:
            batch.count += count
            return
    pond.fry.append(FryBatchState(count=count, cycles_left=cycles_left))
    if len(pond.fry) > MAX_FRY_BATCHES:
        _compact_fry(pond)


def _compact_fry(pond: PondState) -> None:
    """批次上限只在配置离谱（成熟周期数远大于批次上限）时才会碰到，合并最接近的两批。"""

    pond.fry.sort(key=lambda batch: batch.cycles_left)
    index = min(
        range(len(pond.fry) - 1),
        key=lambda i: pond.fry[i + 1].cycles_left - pond.fry[i].cycles_left,
    )
    first, second = pond.fry[index], pond.fry[index + 1]
    total = first.count + second.count
    first.cycles_left = (first.cycles_left * first.count + second.cycles_left * second.count) / total
    first.count = total
    pond.fry.pop(index + 1)


def _mature_fry(pond: PondState, aged_cycles: float) -> int:
    """把所有批次推进 aged_cycles 个周期，长满的转成成鱼。鱼苗与成鱼总数不变。"""

    if aged_cycles <= 0 or not pond.fry:
        return 0
    matured = 0
    remaining = []
    for batch in pond.fry:
        batch.cycles_left -= aged_cycles
        if batch.cycles_left <= 1e-9:
            matured += batch.count
        else:
            remaining.append(batch)
    pond.fry = remaining
    pond.stock += matured
    return matured


def _breed(pond: PondState, parameters: PondParameters, advance: PondAdvance, breeding_stock: int) -> None:
    """每周期按成鱼数的 growth_rate 出鱼，小数留在 growth_remainder 里攒到 1 再出一尾。

    新出的鱼一样是鱼苗：自繁的鱼如果即时成年，买来的鱼苗就没有理由要等。用的是本周期
    【期初】的成鱼数，本周期末才成年的鱼从下一个周期开始参与繁殖。
    """

    if pond.population >= parameters.capacity:
        return
    pond.growth_remainder += breeding_stock * parameters.growth_rate
    whole = floor(pond.growth_remainder)
    if not whole:
        return
    pond.growth_remainder -= whole
    spawned = min(whole, parameters.capacity - pond.population)
    if spawned <= 0:
        return
    add_fry(pond, spawned, parameters.maturation_cycles)
    advance.spawned += spawned


def _drift_generation(pond: PondState, parameters: PondParameters, advance: PondAdvance) -> None:
    """世代加值只在鱼群稳定的周期里涨，低于门槛就往回掉。

    这样"捞多少"的代价是连续的、由塘的状态决定的，而不是捞鱼那一瞬间的一次性判定 ——
    卡着门槛捞一半就永远不掉分的做法自然失效。
    """

    if pond.stock >= parameters.steady_stock:
        gained = min(max(0.0, parameters.generation_cap - pond.generation_score), parameters.generation_gain)
        pond.generation_score += gained
        advance.generation_gained += gained
        return
    lost = min(pond.generation_score, parameters.generation_decay)
    pond.generation_score -= lost
    advance.generation_lost += lost


def _is_stationary(pond: PondState, parameters: PondParameters) -> bool:
    """满塘、没有鱼苗在长、加值到顶：之后每个周期都一模一样，可以直接跳出。"""

    return (
        not pond.fry
        and pond.stock >= parameters.capacity
        and pond.generation_score >= parameters.generation_cap
    )


def advance_pond(pond: PondState, parameters: PondParameters, seconds: int) -> PondAdvance:
    """把一口塘按整周期推进 seconds 秒。不足一个周期的部分留在 settle_remainder 里。

    鱼苗的计时是连续的（按周期折算），繁殖与世代加值只在周期边界发生，所以这一段时间要
    切成"补齐当前周期 + 若干整周期 + 尾巴"三部分，三部分的折算周期数之和正好是 seconds / T。
    """

    advance = PondAdvance(fed_seconds=max(0, int(seconds)))
    cycle_seconds = parameters.cycle_seconds
    if cycle_seconds <= 0:
        return advance
    elapsed = pond.settle_remainder + max(0, int(seconds))
    cycles = elapsed // cycle_seconds
    leading = (cycle_seconds - pond.settle_remainder) / cycle_seconds if cycles else 0.0
    trailing = (elapsed % cycle_seconds) / cycle_seconds
    pond.settle_remainder = elapsed % cycle_seconds
    if pond.empty:
        # 空塘不繁殖，也不该攒着周期等投苗之后一次性爆发。
        pond.settle_remainder = 0
        return advance
    for index in range(min(cycles, MAX_SETTLE_CYCLES)):
        advance.cycles += 1
        breeding_stock = pond.stock
        # 先让鱼苗长大再繁殖，新生的这批才不会被本周期的计时顺带扣掉一个周期。
        advance.matured += _mature_fry(pond, leading if index == 0 else 1.0)
        _breed(pond, parameters, advance, breeding_stock)
        _drift_generation(pond, parameters, advance)
        if _is_stationary(pond, parameters):
            break
    advance.matured += _mature_fry(pond, trailing)
    return advance


def pending_cycles(pond: PondState, parameters: PondParameters, seconds: int) -> int:
    """这一段时间够跑几个完整周期。饲料按周期扣，所以先要知道打算跑几个周期。"""

    if parameters.cycle_seconds <= 0 or pond.empty:
        return 0
    return (pond.settle_remainder + max(0, int(seconds))) // parameters.cycle_seconds


def settle_ponds(
    ponds: list[PondState],
    feed_slot: SlotState,
    parameters: dict[str, PondParameters],
    now: int,
) -> AquaticSettlement:
    """把所有鱼塘一起推进到 now。

    饲料【按周期】扣：一个周期一份，跟周期有多长无关，所以水产能力加快的是产出速度，
    不会顺带摊薄料耗。槽是共享的，不够时按各塘想跑的周期数比例分摊，买不起的周期不跑。
    """

    settlement = AquaticSettlement()
    elapsed = {pond.pond_id: max(0, now - pond.last_settled_at) for pond in ponds}
    wanted: dict[str, int] = {}
    demand = 0.0
    for pond in ponds:
        entry = parameters.get(pond.pond_id)
        if entry is None:
            continue
        cycles = pending_cycles(pond, entry, elapsed[pond.pond_id])
        wanted[pond.pond_id] = cycles
        demand += cycles * entry.feed_per_cycle
    ratio = 1.0
    if demand > 0:
        available = min(feed_slot.units, demand)
        ratio = available / demand
        settlement.stalled = ratio < 1
    consumed = 0.0
    for pond in ponds:
        entry = parameters.get(pond.pond_id)
        if entry is None:
            pond.last_settled_at = now
            continue
        want = wanted.get(pond.pond_id, 0)
        afford = want if ratio >= 1 else floor(want * ratio)
        if afford >= want:
            fed_seconds = elapsed[pond.pond_id]
        else:
            # 买不起的周期直接不跑：停在最后一个付得起的周期末尾，剩下的时间不补发。
            fed_seconds = max(0, afford * entry.cycle_seconds - pond.settle_remainder)
        advance = advance_pond(pond, entry, fed_seconds)
        # 按买下的周期数扣，不按实际推进的周期数：满塘到顶之后会提前跳出循环，但鱼照吃。
        advance.paid_cycles = afford
        consumed += afford * entry.feed_per_cycle
        # 停摆期间没有额外惩罚：存量、世代加值、余数都原样留着，投料之后从停摆点继续。
        advance.stalled = bool(not pond.empty and afford < want)
        pond.stalled = advance.stalled
        pond.cycle_seconds = entry.cycle_seconds
        pond.last_settled_at = now
        settlement.ponds[pond.pond_id] = advance
    feed_slot.units = max(0.0, feed_slot.units - consumed)
    settlement.consumed_units = consumed
    feed_slot.updated_at = now
    if not feed_slot.units:
        feed_slot.quality_score = 0.0
    return settlement


def deposit_into_slot(slot: SlotState, add_units: float, unit_score: float, capacity: int) -> None:
    """投料：quality_score 是存量加权平均，超出容量整笔拒绝，不做部分收敛。"""

    if add_units <= 0:
        raise SlotError("投入份数必须为正数")
    if slot.units + add_units > capacity:
        raise SlotError("饲料槽装不下这一批，先喂掉一些或者倒空再来")
    total = slot.units + add_units
    slot.quality_score = (slot.units * slot.quality_score + add_units * unit_score) / total
    slot.units = total


def preview_slot_score(slot: SlotState, add_units: float, unit_score: float) -> float:
    """前端要显示“投进去之后分数变成多少”，把加权平均单独暴露出来。"""

    total = slot.units + max(0.0, add_units)
    if total <= 0:
        return 0.0
    return (slot.units * slot.quality_score + max(0.0, add_units) * unit_score) / total


def slot_runtime_seconds(slot: SlotState, hourly_rate: float) -> int:
    if hourly_rate <= 0:
        return 0
    return int(slot.units / hourly_rate * SECONDS_PER_HOUR)


def decayed_combo(combo: int, combo_updated_at: int, now: int, grace_seconds: int, decay_seconds: int) -> int:
    """超过 grace 没抛竿就开始逐层掉。返回衰减之后的层数。"""

    if combo <= 0:
        return 0
    idle = max(0, now - combo_updated_at)
    if idle <= grace_seconds:
        return combo
    lost = (idle - grace_seconds) // max(1, decay_seconds)
    return max(0, combo - int(lost))
