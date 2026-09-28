"""夏夜潮祭活动档期与领队加成补丁（独立模块，不改动 red_leaf_town 包内文件）。

上游只有「beta 白名单」这一种灰度开关，没有档期概念：
`ExplorationExpeditionDefinition` 里没有开始/结束时间，`_visible_expeditions` 也只看 beta。
夏活这类限时路线要「结束后从探索列表消失、也不能再出发」，又不想改上游的
models/content/service，所以在本模块里给 `GameService` 打三处运行时补丁：

    _visible_expeditions      列表快照里滤掉档期外的活动路线
    start_exploration         档期外直接拒绝出发（防止绕过列表打接口）
    withdraw_exploration      领队加成：顾祇SP 带队时把最终战利品总量放大到 120%
    _exploration_snapshot     给带备注的路线塞 leader_note，前端渲染成蓝字提示
    _aquatic_snapshot         钓鱼列表里滤掉档期外的活动钓点，并给在档的活动钓点塞 event_badge
    cast_line                 活动钓点档期外直接拒绝抛竿（防止绕过列表打接口）

三条硬口径：
  1. 档期判断用**后端时钟**（`self._now()`），所以 `POST /dev/timewarp` 能直接试出
     「夏活结束」的效果，不用等真时间。
  2. 已经出发的探索不受影响——档期只管「能不能看到 / 能不能新开一趟」，
     走到一半的活动照常走完、照常结算，加成也照常发。
  3. 加成只在**结算那一刻**按总量算一次（`scale_quantities`），不是每层事件各乘一次。
     每层各乘会被 round 吃掉零头（数量 1 × 1.2 还是 1），总量算才真的等于 120%。
     装备类固定掉落（fixed_rewards）不参与放大。

写一条新活动档期的全部成本：
    1. 在 data/seasons.json 的 seasons[] 里加一条
       （expedition_id / name / starts_at / ends_at / 可选 leader_bonus；
         活动钓点用 fishing_spot_ids + fishing_spot_badge）
    2. 重启后端 —— 或直接改文件，档期是每次请求现读的（不缓存，改完立刻生效）

    python patches/local_seasons.py            # 看一眼当前档期状态
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import floor
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SEASON_PATH = ROOT / "data" / "seasons.json"

# 引擎/存档里代表「这次探索已经吃过领队加成」的标记位，
# 存在 run.trait_usage 里（它本来就是个任意 key 的计数器，快照不外发）。
BONUS_FLAG = "local_season_leader_bonus"

# 平台时区：内容里写的是 +08:00 的墙钟时间，缺时区的时间按这个补。
PLATFORM_TZ = timezone(timedelta(hours=8))

# 文件很小（几百字节），每次调用现读现解，不缓存。
# 别改成按 mtime 缓存：本机 mtime 只有秒级精度，同一秒内改两次（比如改完再写回）
# 会被当成"没变过"，档期就卡在旧值上——实机验证时踩过一次。
_WARNED: set[str] = set()

_ORIGINALS: dict[str, Callable] = {}
_SEASON_PATH: Path = DEFAULT_SEASON_PATH
_SERVICE_CLS: Any = None


# ------------------------------------------------------------------ 档期数据


@dataclass(frozen=True)
class LeaderBonus:
    partner_id: str
    reward_multiplier: float
    label: str = ""
    note: str = ""


@dataclass(frozen=True)
class Season:
    expedition_id: str
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    note: str = ""
    leader_bonus: LeaderBonus | None = None
    leader_note: str = ""
    fishing_spot_ids: tuple[str, ...] = ()
    fishing_spot_badge: str = ""
    fishing_spot_note: str = ""
    raw: dict = field(default_factory=dict)

    def is_open(self, now: float | int) -> bool:
        moment = datetime.fromtimestamp(float(now), tz=timezone.utc)
        if self.starts_at is not None and moment < self.starts_at:
            return False
        if self.ends_at is not None and moment > self.ends_at:
            return False
        return True

    def window_text(self) -> str:
        def fmt(value: datetime | None, fallback: str) -> str:
            return fallback if value is None else value.astimezone(PLATFORM_TZ).strftime("%Y-%m-%d %H:%M")

        return f"{fmt(self.starts_at, '不限')} → {fmt(self.ends_at, '不限')}"


def _parse_moment(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"档期时间看不懂（要 ISO 8601）：{text}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PLATFORM_TZ)
    return moment


def load_seasons(path: Path | str | None = None, *, reload: bool = False) -> list[Season]:
    """读档期文件。每次现读，改了文件立刻生效（不用重启、也不用等缓存过期）。

    `reload` 只是为了兼容旧调用；现在本来就是现读的，留着不影响。
    """

    target = Path(path) if path is not None else _SEASON_PATH
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # 档期文件坏了不该把整个游戏带崩：报一次警，然后当"没有档期"处理。
        key = f"{target}:{exc}"
        if key not in _WARNED:
            _WARNED.add(key)
            print(f"[档期] {target} 读不动，已按「没有配置档期」处理：{exc}")
        return []

    seasons: list[Season] = []
    for entry in payload.get("seasons") or []:
        expedition_id = str(entry.get("expedition_id") or "").strip()
        fishing_spot_ids = tuple(
            str(value).strip()
            for value in (entry.get("fishing_spot_ids") or [])
            if str(value).strip()
        )
        # 只管钓点、不管路线的档期也允许（活动钓场可以独立上线）。
        if not expedition_id and not fishing_spot_ids:
            continue
        bonus_raw = entry.get("leader_bonus") or None
        bonus = None
        if bonus_raw:
            partner_id = str(bonus_raw.get("partner_id") or "").strip()
            if partner_id:
                bonus = LeaderBonus(
                    partner_id=partner_id,
                    reward_multiplier=float(bonus_raw.get("reward_multiplier") or 1.0),
                    label=str(bonus_raw.get("label") or ""),
                    note=str(bonus_raw.get("note") or ""),
                )
        seasons.append(Season(
            expedition_id=expedition_id,
            name=str(entry.get("name") or expedition_id or (fishing_spot_ids[0] if fishing_spot_ids else "活动")),
            starts_at=_parse_moment(entry.get("starts_at")),
            ends_at=_parse_moment(entry.get("ends_at")),
            note=str(entry.get("note") or ""),
            leader_bonus=bonus,
            leader_note=str(entry.get("leader_note") or ""),
            fishing_spot_ids=fishing_spot_ids,
            fishing_spot_badge=str(entry.get("fishing_spot_badge") or ""),
            fishing_spot_note=str(entry.get("fishing_spot_note") or ""),
            raw=entry,
        ))
    return list(seasons)


def leader_notes(path: Path | str | None = None) -> dict[str, str]:
    """expedition_id → 要显示在「组织队伍」下面的蓝字备注。

    备注文案完全由 seasons.json 的 `leader_note` 提供（想改措辞改数据就行，
    不用动前端）。没写 leader_note 的活动路线就不显示。
    """

    return {
        season.expedition_id: season.leader_note
        for season in load_seasons(path)
        if season.leader_note
    }


def season_for(expedition_id: str, path: Path | str | None = None) -> Season | None:
    target = str(expedition_id or "").strip()
    if not target:
        return None
    for season in load_seasons(path):
        if season.expedition_id == target:
            return season
    return None


def hidden_expedition_ids(now: float | int, path: Path | str | None = None) -> set[str]:
    return {season.expedition_id for season in load_seasons(path) if not season.is_open(now)}


def hidden_fishing_spot_ids(now: float | int, path: Path | str | None = None) -> set[str]:
    """档期外要从钓鱼列表里拿掉的活动钓点。"""

    return {
        spot_id
        for season in load_seasons(path)
        if not season.is_open(now)
        for spot_id in season.fishing_spot_ids
    }


def fishing_spot_badges(now: float | int, path: Path | str | None = None) -> dict[str, str]:
    """在档活动钓点 → 卡片角标文案（如「夏日限定」）。"""

    badges: dict[str, str] = {}
    for season in load_seasons(path):
        if not season.is_open(now) or not season.fishing_spot_badge:
            continue
        for spot_id in season.fishing_spot_ids:
            badges[spot_id] = season.fishing_spot_badge
    return badges


def fishing_spot_notes(now: float | int, path: Path | str | None = None) -> dict[str, str]:
    """在档活动钓点 → 卡片蓝字备注（如「夏典期间…陪钓收益为120%」）。

    和 `leader_note` 同款：文案写在 seasons.json 的 `fishing_spot_note` 里，
    由补丁塞进钓点快照的 `event_note`，前端在钓点卡片上渲染成蓝字。
    """

    notes: dict[str, str] = {}
    for season in load_seasons(path):
        if not season.is_open(now) or not season.fishing_spot_note:
            continue
        for spot_id in season.fishing_spot_ids:
            notes[spot_id] = season.fishing_spot_note
    return notes


def season_for_fishing_spot(spot_id: str, path: Path | str | None = None) -> Season | None:
    target = str(spot_id or "").strip()
    if not target:
        return None
    for season in load_seasons(path):
        if target in season.fishing_spot_ids:
            return season
    return None


# --------------------------------------------------------------- 收益放大算法


def scale_quantities(quantities: list[int], multiplier: float) -> list[int]:
    """把一组数量整体放大到 round(总量 × multiplier)。

    先算总量、再分摊多出来的整数，这样「全队最终收益 = 120%」是准的；
    逐项乘再四舍五入会被零头吃掉（数量 1 × 1.2 还是 1）。
    多出来的份额优先补给数量最大的那几组，依次轮转直到分完。
    """

    values = [max(1, int(quantity)) for quantity in quantities]
    if not values or multiplier <= 1:
        return values
    total_before = sum(values)
    total_after = max(total_before, floor(total_before * float(multiplier) + 0.5))
    extra = total_after - total_before
    result = list(values)
    if extra <= 0:
        return result
    order = sorted(range(len(result)), key=lambda index: (-result[index], index))
    cursor = 0
    while extra > 0:
        result[order[cursor % len(order)]] += 1
        cursor += 1
        extra -= 1
    return result


# -------------------------------------------------------------------- 补丁本体


def _now_of(service) -> float:
    try:
        return float(service._now())
    except Exception:  # noqa: BLE001 - 拿不到就退回真实时间，宁可判断不准也不能炸
        return time.time()


def _patched_visible_expeditions(self, player):
    entries = _ORIGINALS["_visible_expeditions"](self, player)
    hidden = hidden_expedition_ids(_now_of(self))
    if not hidden:
        return entries
    return [entry for entry in entries if getattr(entry, "id", "") not in hidden]


def _patched_start_exploration(self, oauth_sub, *args, **kwargs):
    from red_leaf_town.application import GameError  # noqa: PLC0415 - 延迟导入，避开启动顺序

    expedition_id = str(kwargs.get("expedition_id") or (args[0] if args else "") or "").strip()
    season = season_for(expedition_id)
    if season is not None and not season.is_open(_now_of(self)):
        raise GameError("content_locked", f"「{season.name}」已经结束了，这条路线暂时关闭", 409)
    return _ORIGINALS["start_exploration"](self, oauth_sub, *args, **kwargs)


def _apply_leader_bonus(self, oauth_sub: str, season: Season) -> dict:
    """结算前把这次的战利品总量放大一次。只做一次，标记写进 run.trait_usage。"""

    bonus = season.leader_bonus
    assert bonus is not None
    record: dict[str, Any] = {
        "partner_id": bonus.partner_id,
        "label": bonus.label,
        "multiplier": bonus.reward_multiplier,
        "applied": False,
        "items_before": 0,
        "items_after": 0,
    }

    def mutation(player):
        run = player.exploration_run
        # 前置条件交给上游原逻辑去报错，这里只负责「能加就加」。
        if run is None or run.battle is not None:
            return
        if run.trait_usage.get(BONUS_FLAG):
            return
        rewards = list(run.pending_rewards)
        quantities = [int(reward.quantity) for reward in rewards]
        scaled = scale_quantities(quantities, bonus.reward_multiplier)
        for reward, value in zip(rewards, scaled):
            reward.quantity = value
        run.trait_usage[BONUS_FLAG] = 1
        record["applied"] = True
        record["items_before"] = sum(quantities)
        record["items_after"] = sum(scaled)

    self._update_by_sub(oauth_sub, mutation)
    return record


def _patched_withdraw_exploration(self, oauth_sub, *args, **kwargs):
    record: dict[str, Any] | None = None
    season: Season | None = None
    player = self.repository.get_by_sub(oauth_sub)
    run = getattr(player, "exploration_run", None) if player is not None else None
    if run is not None:
        season = season_for(str(getattr(run, "expedition_id", "") or ""))
        if (
            season is not None
            and season.leader_bonus is not None
            and str(getattr(run, "leader_partner_id", "") or "") == season.leader_bonus.partner_id
        ):
            record = _apply_leader_bonus(self, oauth_sub, season)

    payload = _ORIGINALS["withdraw_exploration"](self, oauth_sub, *args, **kwargs)
    if record is not None and isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            result["leader_bonus"] = {
                **record,
                "season": season.name if season else "",
                "note": "本次结算已按领队加成放大战利品总量（装备类固定掉落不计入）",
            }
    return payload


def _patched_exploration_snapshot(self, player, now, partner_map):
    """给带备注的活动路线塞一个 `leader_note` 字段，前端渲染成蓝字提示。"""

    payload = _ORIGINALS["_exploration_snapshot"](self, player, now, partner_map)
    notes = leader_notes()
    if notes and isinstance(payload, dict):
        for entry in payload.get("expeditions") or []:
            note = notes.get(str(entry.get("id") or ""))
            if note:
                entry["leader_note"] = note
    return payload


def _patched_aquatic_snapshot(self, player, now, partner_map):
    """钓鱼列表：档期外的活动钓点不出现，在档的带上角标文案。

    `next_spot_level` 必须按过滤后的列表重算——不然活动钓点下线以后，
    界面会一直提示「等级 12 解锁」，可那个水面永远不会出现。
    """

    payload = _ORIGINALS["_aquatic_snapshot"](self, player, now, partner_map)
    if not isinstance(payload, dict):
        return payload
    moment = _now_of(self)
    hidden = hidden_fishing_spot_ids(moment)
    badges = fishing_spot_badges(moment)
    notes = fishing_spot_notes(moment)
    spots = list(payload.get("spots") or [])
    if hidden:
        spots = [entry for entry in spots if str(entry.get("id") or "") not in hidden]
    if badges or notes:
        for entry in spots:
            spot_id = str(entry.get("id") or "")
            badge = badges.get(spot_id)
            if badge:
                entry["event_badge"] = badge
            note = notes.get(spot_id)
            if note:
                entry["event_note"] = note
    payload["spots"] = spots
    payload["unlocked"] = any(entry.get("unlocked") for entry in spots)
    visible = {str(entry.get("id") or "") for entry in spots}
    payload["next_spot_level"] = next(
        (
            spot.min_level
            for spot in self.content.fishing_spots
            if spot.id in visible and player.level < spot.min_level
        ),
        None,
    )
    return payload


def _patched_cast_line(self, oauth_sub, *args, **kwargs):
    """活动钓点档期外直接拒绝抛竿（防止绕过列表打接口）。"""

    from red_leaf_town.application import GameError  # noqa: PLC0415

    spot_id = str(kwargs.get("spot_id") or (args[0] if args else "") or "").strip()
    season = season_for_fishing_spot(spot_id)
    if season is not None and not season.is_open(_now_of(self)):
        raise GameError("content_locked", f"「{season.name}」已经结束，这个钓点暂不开放", 409)
    return _ORIGINALS["cast_line"](self, oauth_sub, *args, **kwargs)


def install(seasons_path: Path | str | None = None, *, force: bool = False) -> None:
    """给 GameService 打补丁。幂等：重复调用不会套娃，只会换档期文件。"""

    global _SEASON_PATH, _SERVICE_CLS

    from red_leaf_town.application import GameService  # noqa: PLC0415 - 延迟导入，避开启动顺序

    _SERVICE_CLS = GameService
    if seasons_path is not None:
        _SEASON_PATH = Path(seasons_path)
    if getattr(GameService, "_local_seasons_installed", False) and not force:
        return
    for name in ("_visible_expeditions", "start_exploration", "withdraw_exploration",
                 "_exploration_snapshot", "_aquatic_snapshot", "cast_line"):
        if name not in _ORIGINALS:
            _ORIGINALS[name] = getattr(GameService, name)
    GameService._visible_expeditions = _patched_visible_expeditions
    GameService.start_exploration = _patched_start_exploration
    GameService.withdraw_exploration = _patched_withdraw_exploration
    GameService._exploration_snapshot = _patched_exploration_snapshot
    GameService._aquatic_snapshot = _patched_aquatic_snapshot
    GameService.cast_line = _patched_cast_line
    GameService._local_seasons_installed = True


# ---------------------------------------------------------------------- 自检


def describe(seasons_path: Path | str | None = None, now: float | None = None) -> list[str]:
    """给人看的档期状态，供启动自检调用。"""

    target = Path(seasons_path) if seasons_path is not None else _SEASON_PATH
    moment = float(now) if now is not None else time.time()
    seasons = load_seasons(target)
    if not seasons:
        return [f"没有配置任何活动档期（{target}）"]
    lines = [f"活动档期 {target}"]
    for season in seasons:
        state = "开放中" if season.is_open(moment) else "已关闭（列表隐藏 + 禁止出发）"
        label = season.expedition_id or "仅钓点"
        lines.append(f"  {season.name}（{label}）{season.window_text()} · {state}")
        if season.leader_bonus is not None:
            percent = round(season.leader_bonus.reward_multiplier * 100)
            lines.append(
                f"    领队加成：{season.leader_bonus.partner_id} 任领队时收益提升至 {percent}%"
                f"（{season.leader_bonus.label or '未命名'}）"
            )
        if season.leader_note:
            lines.append(f"    界面备注：{season.leader_note}")
        if season.fishing_spot_ids:
            badge = f"（角标「{season.fishing_spot_badge}」）" if season.fishing_spot_badge else ""
            lines.append(f"    活动钓点：{'、'.join(season.fishing_spot_ids)}{badge}")
            if season.fishing_spot_note:
                lines.append(f"    钓点蓝字：{season.fishing_spot_note}")
    return lines


def main() -> None:
    for line in describe():
        print(line)


if __name__ == "__main__":
    main()
