"""灵果草甸的快速模拟器。

战斗全部走 red_leaf_town.domain.delve_battle 的真实函数，节点抽取照抄 service
的 _pick_exploration_event；被替换掉的只有 PlayerState / 仓库 / 快照那一层——
服务层每个战斗行动要 6.8ms（仓库对整份存档 deepcopy 三次），领域层是 0.007ms。

用法：
    from scripts.delve_sim import Sim, BASELINE_GEAR, five_star_party, fmt
    print(fmt("带装备", Sim(partner_level=20, gear=BASELINE_GEAR, salves=4).run_many(3000)))

boss_attacks_per_turn 之类的覆盖项只改内存里的内容对象，不会写回 data/game.json。
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from red_leaf_town.content import load_content
from red_leaf_town.domain import delve_battle
from red_leaf_town.domain.models import (
    DelveBattleState,
    DelveEnemyState,
    DelveLoadoutSnapshot,
    DelveMemberState,
)
from red_leaf_town.partner_content import load_partner_catalog

EXPEDITION_ID = "spiritfruit_meadow"


@dataclass
class Fighter:
    """一名出战伙伴的输入。stats 是 (力, 敏, 智, 运)。"""

    name: str
    stats: tuple[int, int, int, int]
    weapon: str = ""
    accessory: str = ""


# 文档验收基线用的那三人（合成属性），以及五星探索伙伴。
BASELINE_PARTY = [
    Fighter("leader", (15, 12, 12, 13)),
    Fighter("scout", (11, 15, 12, 12)),
    Fighter("guard", (14, 10, 11, 10)),
]

BASELINE_GEAR = {
    "leader": ("red_copper_greatsword", "hunters_charm"),
    "scout": ("moon_silver_dagger", ""),
    "guard": ("red_copper_greatsword", ""),
}


def five_star_party(*partner_ids: str) -> list[Fighter]:
    catalog = {p.id: p for p in load_partner_catalog().partners}
    party = []
    for pid in partner_ids:
        d = catalog[pid]
        s = d.exploration_stats
        party.append(Fighter(d.name, (s.strength, s.agility, s.intelligence, s.luck)))
    return party


def loadout_for(content, weapon_id: str, accessory_id: str) -> DelveLoadoutSnapshot:
    """把物品定义翻成战斗快照，字段口径与 service._build_delve_loadout 一致。"""
    data: dict = {}
    for item_id in (weapon_id, accessory_id):
        if not item_id:
            continue
        equipment = content.item_map[item_id].equipment
        if equipment.slot == "weapon":
            data["weapon_item_id"] = item_id
            data["attack_attribute"] = equipment.attribute
            data["damage_dice"] = equipment.damage_dice
        else:
            data["accessory_item_id"] = item_id
        for field_name in ("attack_bonus", "proficiency_bonus", "armor_bonus",
                           "initiative_bonus", "max_hp_bonus", "advantage_uses"):
            value = getattr(equipment, field_name, 0) or 0
            if value:
                data[field_name] = data.get(field_name, 0) + value
    return DelveLoadoutSnapshot(**data)


def _tally(drops: dict, outcome) -> None:
    """把一个结局的产出累加进这一趟的掉落表。品质产物按数量区间取均值。"""
    if outcome is None:
        return
    for reward in outcome.rewards:
        drops[reward.item_id] = drops.get(reward.item_id, 0.0) + (
            reward.quantity_min + reward.quantity_max) / 2
    for reward in outcome.fixed_rewards:
        drops[reward.item_id] = drops.get(reward.item_id, 0.0) + reward.quantity


@dataclass
class Result:
    outcome: str          # cleared / wiped / stalled
    hp_ratio: float = 0.0
    hp_at_boss: float = 0.0
    reached_boss: bool = False
    battles: int = 0
    salves_used: int = 0
    stamina_spent: int = 0
    # item_id -> 件数（品质产物按 quantity_min/max 的均值算，固定掉落按件算）
    drops: dict = field(default_factory=dict)


@dataclass
class Sim:
    party: list[Fighter] = field(default_factory=lambda: list(BASELINE_PARTY))
    partner_level: int = 1
    gear: dict[str, tuple[str, str]] | None = None
    salves: int = 0
    salve_quality: int = 3
    # 调平衡用的覆盖项：只改内存里的内容对象，绝不写回 data/game.json
    boss_attacks_per_turn: int = 0
    heal_below: float = 0.5
    # self = 只救当前行动的人（老模拟的口径）；worst = 救全队最危险的那个
    heal_target: str = "worst"
    stamina: int = 9999
    content: object = None

    def __post_init__(self):
        self.content = self.content or load_content()
        if self.boss_attacks_per_turn:
            self.content = self.content.model_copy(deep=True)
            self.content.delve_enemy_map["fruitheart_warden"].attacks_per_turn = (
                self.boss_attacks_per_turn
            )
        self.expedition = self.content.exploration_expedition_map[EXPEDITION_ID]
        self.enemies = self.content.delve_enemy_map
        salve = self.content.item_map["herbal_salve"].delve_use
        self.salve_dice = salve.dice
        self.salve_flat = salve.flat + max(0, self.salve_quality - 1) * salve.quality_bonus

    # ---- 建队 -------------------------------------------------------
    def _members(self) -> dict[str, delve_battle.PartyMember]:
        members = {}
        for fighter in self.party:
            weapon, accessory = (self.gear or {}).get(fighter.name, ("", ""))
            loadout = loadout_for(self.content, weapon, accessory)
            strength, agility, intelligence, luck = fighter.stats
            max_hp = delve_battle.member_max_hp(self.partner_level, strength, loadout)
            members[fighter.name] = delve_battle.PartyMember(
                partner_id=fighter.name, name=fighter.name,
                strength=strength, agility=agility, intelligence=intelligence, luck=luck,
                state=DelveMemberState(
                    max_hp=max_hp, hp=max_hp,
                    armor_class=delve_battle.armor_class(agility, loadout),
                ),
                loadout=loadout,
            )
        return members

    # ---- 节点抽取（照抄 service._pick_exploration_event） ------------
    def _pick_event(self, rng, counts: dict[str, int], depth: int):
        if depth >= self.expedition.max_depth:
            return self.expedition.event_map[self.expedition.final_event_id]
        eligible = [
            event for event in self.expedition.events
            if event.id != self.expedition.final_event_id
            and event.min_depth <= depth <= event.max_depth
            and counts.get(event.id, 0) < event.max_occurrences
        ]
        if not eligible:
            return None
        draw = rng.random() * sum(event.weight for event in eligible)
        cumulative = 0.0
        for event in eligible:
            cumulative += event.weight
            if draw < cumulative:
                return event
        return eligible[-1]

    # ---- 一场战斗 ---------------------------------------------------
    def _fight(self, rng, members, battle_def, is_boss: bool, pack: list[int]) -> str:
        enemies, initiative = [], {}
        for index, enemy_id in enumerate(battle_def.enemy_ids):
            d = self.enemies[enemy_id]
            key = f"{enemy_id}#{index + 1}"
            enemies.append(DelveEnemyState(
                key=key, enemy_id=d.id, name=d.name, max_hp=d.max_hp, hp=d.max_hp,
                armor_class=d.armor_class, boss=d.boss,
            ))
            initiative[key] = d.initiative_bonus
        battle = DelveBattleState(
            battle_id="sim", event_id="e", choice_id="c", depth=1,
            can_flee=battle_def.can_flee, flee_dc=battle_def.flee_dc, enemies=enemies,
            order=delve_battle.build_initiative(rng, members, enemies, initiative),
            advantage_uses_left={pid: m.loadout.advantage_uses for pid, m in members.items()},
        )
        for _ in range(len(battle.order) * 80):
            outcome = delve_battle.battle_outcome(battle, members)
            if outcome != "ongoing":
                return outcome
            actor_id = delve_battle.current_actor(battle, members)
            if not actor_id:
                return delve_battle.battle_outcome(battle, members)
            if actor_id in members:
                actor = members[actor_id]
                hurt = (actor if self.heal_target == "self" else
                        min(delve_battle.living_members(members),
                            key=lambda m: m.state.hp / m.state.max_hp))
                if pack[0] > 0 and hurt.state.hp <= hurt.state.max_hp * self.heal_below:
                    delve_battle.member_heal(rng, battle, actor, hurt, "秋露药膏",
                                             self.salve_dice, self.salve_flat)
                    pack[0] -= 1
                else:
                    target = next(e.key for e in battle.enemies if e.hp > 0)
                    delve_battle.member_attack(rng, battle, actor, target)
            else:
                enemy = next(e for e in battle.enemies if e.key == actor_id)
                d = self.enemies[enemy.enemy_id]
                delve_battle.enemy_turn(rng, battle, enemy,
                                        [a.model_dump() for a in d.attacks], members,
                                        d.attacks_per_turn)
            delve_battle.advance_turn(battle)
        return delve_battle.battle_outcome(battle, members)

    # ---- 一趟 -------------------------------------------------------
    def run_once(self, seed: int) -> Result:
        rng = random.Random(seed)
        members = self._members()
        counts: dict[str, int] = {}
        pack = [self.salves]
        stamina = self.stamina
        spent = 0
        drops: dict[str, float] = {}
        depth = 0
        battles = 0
        hp_at_boss = 0.0
        reached_boss = False

        def ratio():
            return (sum(m.state.hp for m in members.values())
                    / sum(m.state.max_hp for m in members.values()))

        while depth < self.expedition.max_depth:
            event = self._pick_event(rng, counts, depth + 1)
            if event is None:
                return Result("stalled", ratio(), hp_at_boss, reached_boss, battles,
                              self.salves - pack[0], spent, drops)
            # 有战斗就打战斗分支，没有就走第一个选择，和基线模拟的口径一致。
            choice = next((c for c in event.choices if c.battle is not None), event.choices[0])
            cost = choice.route_stamina + choice.action_stamina
            if stamina < cost:
                return Result("stalled", ratio(), hp_at_boss, reached_boss, battles,
                              self.salves - pack[0], spent, drops)
            stamina -= cost
            spent += cost
            if choice.battle is not None:
                is_boss = event.id == self.expedition.final_event_id
                if is_boss:
                    reached_boss = True
                    hp_at_boss = ratio()
                battles += 1
                outcome = self._fight(rng, members, choice.battle, is_boss, pack)
                if outcome != "victory":
                    return Result("wiped", 0.0, hp_at_boss, reached_boss, battles,
                                  self.salves - pack[0], spent, {})
                _tally(drops, choice.success)
            elif choice.check is not None:
                # 检定不影响 HP，只可能多扣体力；失败按 stamina_surcharge 记。
                face = rng.randint(1, 20)
                best = max(delve_battle.modifier(m.attribute(choice.check.attribute))
                           for m in members.values())
                if face >= 20:
                    _tally(drops, choice.critical_success or choice.success)
                elif face == 1:
                    outcome = choice.critical_failure or choice.failure
                    _tally(drops, outcome)
                    stamina -= outcome.stamina_surcharge if outcome else 0
                elif face + best >= choice.check.dc:
                    _tally(drops, choice.success)
                else:
                    _tally(drops, choice.failure)
                    stamina -= choice.failure.stamina_surcharge if choice.failure else 0
            else:
                _tally(drops, choice.success)
            counts[event.id] = counts.get(event.id, 0) + 1
            depth += 1
        return Result("cleared", ratio(), hp_at_boss, reached_boss, battles,
                      self.salves - pack[0], spent, drops)

    def run_many(self, runs: int = 2000, seed0: int = 0) -> dict:
        results = [self.run_once(seed0 + i) for i in range(runs)]
        cleared = [r for r in results if r.outcome == "cleared"]
        boss = [r for r in results if r.reached_boss]
        return {
            "runs": runs,
            "clear_rate": len(cleared) / runs,
            "wipe_rate": sum(1 for r in results if r.outcome == "wiped") / runs,
            "stalled": sum(1 for r in results if r.outcome == "stalled"),
            "hp_left": sum(r.hp_ratio for r in cleared) / len(cleared) if cleared else 0.0,
            "hp_at_boss": sum(r.hp_at_boss for r in boss) / len(boss) if boss else 0.0,
            "boss_reach_rate": len(boss) / runs,
            "boss_win_rate": len(cleared) / len(boss) if boss else 0.0,
            "salves": sum(r.salves_used for r in results) / runs,
            "stamina": sum(r.stamina_spent for r in results) / runs,
            "stamina_cleared": (sum(r.stamina_spent for r in cleared) / len(cleared)
                                if cleared else 0.0),
            "drops": {
                item_id: sum(r.drops.get(item_id, 0.0) for r in cleared) / len(cleared)
                for item_id in {k for r in cleared for k in r.drops}
            } if cleared else {},
        }


def fmt(label: str, stats: dict) -> str:
    return (f"{label}: 通关 {stats['clear_rate']:.0%} | 到 BOSS {stats['boss_reach_rate']:.0%}"
            f" (进场剩 {stats['hp_at_boss']:.0%}) | BOSS 胜率 {stats['boss_win_rate']:.0%}"
            f" | 通关剩 {stats['hp_left']:.0%} | 用药 {stats['salves']:.1f}")
