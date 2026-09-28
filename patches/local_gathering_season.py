"""夏活采集点档期 + 采集收益加成补丁（独立模块，不改动 red_leaf_town 包内文件）。

绯恩SP 是采集(37/235)+水产(32/205)双倾向，夏活要给她一条能吃满加成的线。探索路线
的领队必须有探索倾向（`_exploration_leader_required`，见 `_exploration_party_ability`），
她当不了，所以走采集系统——采集任务的驻场伙伴正好要求「有采集倾向」。

本模块在 `GameService` 上打三处运行时外层补丁：

    _content_visible      档期外的活动采集点**和它的采集任务**一并不可见
                          （列表里消失、`_require_content` 会直接拦下绕过列表的请求）
    start_gathering       档期外直接拒绝开工，并给出「活动已结束」的准确文案
                          （补 `_content_visible` 只会拿到上游那句通用的「仅对内测玩家开放」）
    _snapshot             在档的活动采集点条目上塞 `event_badge`，前端渲染成角标
    collect_gathering     收取时把本次收获总量放大到 120%（参数在 seasons.json 的
                          `gathering_bonus`，且要求驻场伙伴正是配置里的那位）

三条硬口径（与夏夜潮祭的领队加成完全同款）：
  1. 档期判断用**后端时钟**（`self._now()`），所以 `POST /dev/timewarp` 能直接试出
     「活动结束」的效果，不用等真时间。
  2. 已经开工的采集不受影响——档期只管「能不能看到 / 能不能新开工」。
     收取这一步**不查档期**，所以跨过档期结束时刻才收的活照常结算、照常发加成。
  3. 加成按**总量**算一次（复用 `local_seasons.scale_quantities`），不是逐项乘——
     逐项乘会被 round 吃掉零头（数量 1 × 1.2 还是 1）。

写一条新活动采集点的全部成本：
    1. 在 `data/game.json` 里配好活动采集点 `gathering_sites` / `gathering_tasks`
    2. 在 `data/seasons.json` 的活动条目里加 `gathering_site_ids` /
       `gathering_site_badge` /（可选）`gathering_bonus`
    3. 重启后端 —— 档期本身是每次请求现读的，改完立刻生效

    python patches/local_gathering_season.py     # 看一眼当前配置状态
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any, Callable

try:
    from .local_seasons import load_seasons, scale_quantities
except ImportError:  # 直接以脚本方式运行本文件时
    from local_seasons import load_seasons, scale_quantities

HERE = Path(__file__).resolve().parent

# 只有这两类定义会被档期过滤，避免无谓地给别的内容读档期文件。
GATHERING_TYPES: frozenset[str] = frozenset({"GatheringSiteDefinition", "GatheringTaskDefinition"})

BONUS_FLAG = "local_gathering_season_bonus"

_ORIGINALS: dict[str, Callable] = {}


# ------------------------------------------------------------------ 配置读取


def _site_ids_of(raw: dict) -> list[str]:
    return [str(value).strip() for value in (raw.get("gathering_site_ids") or []) if str(value).strip()]


def hidden_site_ids(now: float | int) -> frozenset[str]:
    """档期外要从采集列表里拿掉的活动采集点 id（任务跟着站点一起走）。"""

    hidden: set[str] = set()
    for season in load_seasons():
        raw = season.raw or {}
        site_ids = _site_ids_of(raw)
        if site_ids and not season.is_open(now):
            hidden.update(site_ids)
    return frozenset(hidden)


def site_badges(now: float | int) -> dict[str, str]:
    """在档活动采集点 → 卡片角标文案（如「夏日限定」）。"""

    badges: dict[str, str] = {}
    for season in load_seasons():
        raw = season.raw or {}
        badge = str(raw.get("gathering_site_badge") or "").strip()
        if not badge or not season.is_open(now):
            continue
        for site_id in _site_ids_of(raw):
            badges[site_id] = badge
    return badges


def site_notes(now: float | int) -> dict[str, str]:
    """在档活动采集点 → 卡片蓝字备注（如「夏典期间…采集收益为120%」）。

    与探索路线的 `leader_note`、钓鱼的 `fishing_spot_note` 同款：文案写在
    seasons.json 的 `gathering_site_note` 里，由补丁塞进站点快照的 `event_note`，
    前端（`ProductionCard`）在卡片上渲染成蓝字。
    """

    notes: dict[str, str] = {}
    for season in load_seasons():
        raw = season.raw or {}
        note = str(raw.get("gathering_site_note") or "").strip()
        if not note or not season.is_open(now):
            continue
        for site_id in _site_ids_of(raw):
            notes[site_id] = note
    return notes


def gathering_bonus_for(
    site_id: str, partner_id: str, now: float | int | None = None, *, require_open: bool = True
) -> dict[str, Any] | None:
    """这个采集点 + 这个驻场伙伴，现在能吃到的加成配置；吃不到返回 None。

    `require_open=False` 用于**收取**那一刻：和夏夜潮祭的领队加成同款口径——
    档期只管「能不能看到 / 能不能新开工」，档期内开工、档期结束后才收的活照常发加成。
    """

    moment = time.time() if now is None else float(now)
    target_site = str(site_id or "").strip()
    target_partner = str(partner_id or "").strip()
    if not target_site or not target_partner:
        return None
    for season in load_seasons():
        raw = season.raw or {}
        bonus = raw.get("gathering_bonus") or None
        if not bonus:
            continue
        if require_open and not season.is_open(moment):
            continue
        if str(bonus.get("partner_id") or "").strip() != target_partner:
            continue
        if target_site not in _site_ids_of(raw):
            continue
        return {
            "partner_id": target_partner,
            "multiplier": float(bonus.get("reward_multiplier") or 1.0),
            "label": str(bonus.get("label") or ""),
            "note": str(bonus.get("note") or ""),
            "site_id": target_site,
            "season_name": season.name,
        }
    return None


def describe(now: float | int | None = None) -> list[str]:
    """给人看的当前状态，供启动自检调用。"""

    moment = time.time() if now is None else float(now)
    lines: list[str] = []
    for season in load_seasons():
        raw = season.raw or {}
        site_ids = _site_ids_of(raw)
        if not site_ids:
            continue
        state = "开放中" if season.is_open(moment) else "已关闭（列表隐藏 + 禁止开工）"
        badge = str(raw.get("gathering_site_badge") or "")
        badge_text = f"（角标「{badge}」）" if badge else ""
        lines.append(f"  活动采集点：{'、'.join(site_ids)}{badge_text} · {state} · {season.name}")
        site_note = str(raw.get("gathering_site_note") or "").strip()
        if site_note:
            lines.append(f"    采集点蓝字：{site_note}")
        bonus = raw.get("gathering_bonus") or None
        if bonus:
            percent = round(float(bonus.get("reward_multiplier") or 1.0) * 100)
            lines.append(
                f"    采集加成：{bonus.get('partner_id')} 驻场时本次收获总量提升至 {percent}%"
                f"（{bonus.get('label') or '未命名'}）"
            )
    return lines or ["  （没有配置活动采集点）"]


# -------------------------------------------------------------------- 补丁本体


def _now_of(service) -> float:
    try:
        return float(service._now())
    except Exception:  # noqa: BLE001 - 拿不到就退回真实时间，宁可判断不准也不能炸
        return time.time()


def _patched_content_visible(self, player, definition) -> bool:
    """档期外的活动采集点/采集任务一律不可见。

    `_content_visible` 是所有内容的统一可见性开关（上游用它实现 beta 白名单），
    采集列表、`available_tasks`、以及 `_require_content` 走的都是它——所以一个补丁
    就同时覆盖了「界面消失」和「绕过列表直接打接口也会被拒」。
    """

    if definition is not None and type(definition).__name__ in GATHERING_TYPES:
        hidden = hidden_site_ids(_now_of(self))
        if hidden:
            ident = str(getattr(definition, "id", "") or "")
            owner_site = str(getattr(definition, "site_id", "") or "")
            if ident in hidden or (owner_site and owner_site in hidden):
                return False
    return _ORIGINALS["_content_visible"](self, player, definition)


def _closed_site_message(self, site_id: str) -> str | None:
    """档期外的活动采集点 → 给人看得懂的话；在档/非活动点返回 None。"""

    moment = _now_of(self)
    for season in load_seasons():
        raw = season.raw or {}
        if site_id in _site_ids_of(raw) and not season.is_open(moment):
            return f"「{season.name}」已经结束了，这个采集点暂不开放"
    return None


def _patched_start_gathering(self, oauth_sub: str, *args, **kwargs):
    """档期外直接拒绝开工（防绕过列表打接口），并给出准确文案。"""

    from red_leaf_town.application import GameError  # noqa: PLC0415

    site_id = str(kwargs.get("site_id") or (args[0] if args else "") or "").strip()
    if site_id:
        message = _closed_site_message(self, site_id)
        if message:
            raise GameError("content_locked", message, 409)
    return _ORIGINALS["start_gathering"](self, oauth_sub, *args, **kwargs)


def _patched_snapshot(self, player, now=None):
    """给在档的活动采集点塞 `event_badge`（角标）与 `event_note`（蓝字备注）。"""

    payload = _ORIGINALS["_snapshot"](self, player, now)
    if isinstance(payload, dict):
        moment = _now_of(self)
        badges = site_badges(moment)
        notes = site_notes(moment)
        if badges or notes:
            for entry in payload.get("gathering_sites") or []:
                site_id = str(entry.get("site_id") or "")
                badge = badges.get(site_id)
                if badge:
                    entry["event_badge"] = badge
                note = notes.get(site_id)
                if note:
                    entry["event_note"] = note
    return payload


def _apply_bonus(self, oauth_sub: str, site_id: str) -> dict[str, Any] | None:
    """把待收取的采集结果按总量放大一次，返回给前端看的记录。"""

    if not site_id:
        return None
    try:
        player = self.repository.get_by_sub(oauth_sub)
    except Exception:  # noqa: BLE001
        return None
    if player is None:
        return None
    site = next((entry for entry in player.gathering_sites if entry.site_id == site_id), None)
    if site is None or not site.task_results:
        return None

    bonus: dict[str, Any] | None = None
    for partner_id in (site.assigned_partner_ids or []):
        bonus = gathering_bonus_for(
            site_id, str(partner_id), _now_of(self), require_open=False
        )
        if bonus is not None:
            break
    if bonus is None or bonus["multiplier"] <= 1.0:
        return None

    quantities = [max(1, int(result.quantity)) for result in site.task_results]
    scaled = scale_quantities(quantities, bonus["multiplier"])
    if sum(scaled) <= sum(quantities):
        return None

    record: dict[str, Any] = {
        "partner_id": bonus["partner_id"],
        "label": bonus["label"],
        "multiplier": bonus["multiplier"],
        "season": bonus["season_name"],
        "site_id": site_id,
        "applied": False,
        "items_before": sum(quantities),
        "items_after": sum(scaled),
    }

    def mutation(player):
        site = next((entry for entry in player.gathering_sites if entry.site_id == site_id), None)
        if site is None or not site.task_results:
            return
        for result, value in zip(site.task_results, scaled):
            result.quantity = int(value)
        record["applied"] = True

    self._update_by_sub(oauth_sub, mutation)
    if not record["applied"]:
        return None
    record.pop("applied", None)
    return record


def _patched_collect_gathering(self, oauth_sub: str, *args, **kwargs):
    """外层：先把待收取的收获放大，再交给原方法搬进背包。"""

    site_id = str(kwargs.get("site_id") or (args[0] if args else "") or "").strip()
    record: dict[str, Any] | None = None
    try:
        record = _apply_bonus(self, oauth_sub, site_id)
    except Exception:  # noqa: BLE001 - 加成失败不能把这次收取整个作废
        traceback.print_exc()

    payload = _ORIGINALS["collect_gathering"](self, oauth_sub, *args, **kwargs)
    if record is not None and isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            result["season_bonus"] = record
    return payload


def install(*, force: bool = False) -> None:
    """给 GameService 打补丁。幂等：重复调用不会套娃。"""

    from red_leaf_town.application import GameService  # noqa: PLC0415 - 延迟导入，避开启动顺序

    if getattr(GameService, "_local_gathering_season_installed", False) and not force:
        return
    for name in ("_content_visible", "start_gathering", "_snapshot", "collect_gathering"):
        if name not in _ORIGINALS:
            _ORIGINALS[name] = getattr(GameService, name)
    GameService._content_visible = _patched_content_visible
    GameService.start_gathering = _patched_start_gathering
    GameService._snapshot = _patched_snapshot
    GameService.collect_gathering = _patched_collect_gathering
    GameService._local_gathering_season_installed = True


def main() -> None:
    print("活动采集档期与加成（patches/local_gathering_season.py）")
    for line in describe():
        print(line)


if __name__ == "__main__":
    main()
