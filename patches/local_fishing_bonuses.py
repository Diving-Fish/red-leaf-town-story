"""活动钓点陪钓加成补丁（独立模块，不改动 red_leaf_town 包内文件）。

一件事，在 `GameService` 上打运行时外层补丁：

「灯湾陪钓加成」（活动档期内，配置在 seasons.json 的 companion_bonus）
    艾欣愉陪钓夏夜灯湾时，单竿钓获总量 ×1.2——口径与顾祇SP 领队夏夜潮祭的
    120% 完全同款：复用 `local_seasons.scale_quantities` 按总量取整分摊，
    结算后把差额直接补进背包并同步到返回的 drops 里（钓获没有 pending 中间态，
    只能结算后补差）。档期判断复用 `local_seasons.load_seasons`——companion_bonus
    是挂在 seasons.json 活动条目上的新字段，`Season.raw` 里能原样读到，
    档期现读、改完立刻生效。

    玩家看到的说明写在档期配置的 `fishing_spot_note` 里，由 `local_seasons`
    塞进钓点快照的 `event_note`，前端在钓点卡片上渲染成蓝字。

    python patches/local_fishing_bonuses.py     # 看一眼当前配置状态
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

try:
    from .local_seasons import load_seasons, scale_quantities
except ImportError:  # 直接以脚本方式运行本文件时
    from local_seasons import load_seasons, scale_quantities

HERE = Path(__file__).resolve().parent

# cast_line 外层补丁 → 结算后补差：同一个请求里完成，Quart 的 async 并发不会串。

_ORIGINALS: dict[str, Callable] = {}

BONUS_FLAG = "local_fishing_companion_bonus"


# ------------------------------------------------------------------ 配置读取


def _companion_bonuses(now: float) -> list[dict[str, Any]]:
    """sears.json 里在档的 companion_bonus 配置（现读，改完立刻生效）。"""

    bonuses: list[dict[str, Any]] = []
    for season in load_seasons():
        raw = season.raw or {}
        bonus = raw.get("companion_bonus") or None
        if not bonus:
            continue
        if not season.is_open(now):
            continue
        bonuses.append(
            {
                "partner_id": str(bonus.get("partner_id") or "").strip(),
                "multiplier": float(bonus.get("reward_multiplier") or 1.0),
                "label": str(bonus.get("label") or ""),
                "note": str(bonus.get("note") or ""),
                "spots": set(season.fishing_spot_ids),
                "season_name": season.name,
            }
        )
    return bonuses


def companion_bonus_for(
    spot_id: str, companion_partner_id: str, now: float | None = None
) -> dict[str, Any] | None:
    """这个钓点 + 这个陪钓，现在能吃到的加成配置；吃不到返回 None。"""

    moment = time.time() if now is None else float(now)
    for bonus in _companion_bonuses(moment):
        if bonus["partner_id"] != companion_partner_id:
            continue
        if spot_id in bonus["spots"]:
            return bonus
    return None


def describe(now: float | None = None) -> list[str]:
    """给人看的当前状态，供启动自检调用。"""

    moment = time.time() if now is None else float(now)
    lines: list[str] = []
    for bonus in _companion_bonuses(moment):
        percent = round(bonus["multiplier"] * 100)
        lines.append(
            f"  陪钓加成：{bonus['partner_id']} 陪钓 {'、'.join(sorted(bonus['spots']))}"
            f"时钓获总量提升至 {percent}%（{bonus['label'] or '未命名'} · {bonus['season_name']}）"
        )
    return lines or ["  （没有配置钓鱼加成）"]


# -------------------------------------------------------------------- 补丁本体


def _companion_of(service, oauth_sub: str) -> str:
    try:
        player = service.repository.get_by_sub(oauth_sub)
    except Exception:  # noqa: BLE001 - 查不到陪钓就当没带伙伴，宁可不加也不炸
        return ""
    if player is None:
        return ""
    return str(getattr(player.fishing, "companion_partner_id", "") or "")


def _patched_cast_line(self, oauth_sub: str, *args, **kwargs):
    """外层：记下当前陪钓 → 调原方法 → 给满足条件的钓获做总量放大。"""

    # 路由是 cast_line(subject, spot_id, request_id) 位置传参，所以 spot_id 在 args[0]。
    # 别用 args[1]（那是 request_id，默认空串），否则钓点判断永远落空、加成静默失效。
    spot_id = str(kwargs.get("spot_id") or (args[0] if args else "") or "").strip()
    companion = _companion_of(self, oauth_sub)
    payload = _ORIGINALS["cast_line"](self, oauth_sub, *args, **kwargs)

    try:
        _apply_companion_bonus(self, oauth_sub, spot_id, companion, payload)
    except Exception:  # noqa: BLE001 - 加成失败不能把这次抛竿整个作废
        import traceback  # noqa: PLC0415

        traceback.print_exc()
    return payload


def _apply_companion_bonus(self, oauth_sub: str, spot_id: str, companion: str, payload: Any) -> None:
    """结算后补差：钓获总量 ×multiplier，差额直接进背包并同步到 drops。"""

    if not companion or not isinstance(payload, dict):
        return
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    bonus = companion_bonus_for(spot_id, companion, _now_of(self))
    if bonus is None or bonus["multiplier"] <= 1.0:
        return

    drops = [d for d in (result.get("drops") or []) if isinstance(d, dict) and d.get("item_id")]
    if not drops:
        return
    quantities = [max(1, int(d.get("quantity") or 1)) for d in drops]
    scaled = scale_quantities(quantities, bonus["multiplier"])
    if sum(scaled) <= sum(quantities):
        return

    record: dict[str, Any] = {
        "partner_id": companion,
        "label": bonus["label"],
        "multiplier": bonus["multiplier"],
        "season": bonus["season_name"],
        "spot_id": spot_id,
        "applied": False,
        "items_before": sum(quantities),
        "items_after": sum(scaled),
    }

    def mutation(player):
        for drop, before, after in zip(drops, quantities, scaled):
            delta = after - before
            if delta <= 0:
                continue
            add_item(player, str(drop["item_id"]), delta, int(drop.get("quality") or 0))
            drop["quantity"] = after
        record["applied"] = True

    self._update_by_sub(oauth_sub, mutation)
    if record["applied"]:
        record.pop("applied", None)
        result["companion_bonus"] = record


def _now_of(service) -> float:
    try:
        return float(service._now())
    except Exception:  # noqa: BLE001
        return time.time()


def install(*, force: bool = False) -> None:
    """给 GameService 打补丁。幂等：重复调用不会套娃。"""

    from red_leaf_town.application import GameService  # noqa: PLC0415 - 延迟导入，避开启动顺序
    from red_leaf_town.domain.economy import add_item  # noqa: PLC0415

    globals()["add_item"] = add_item
    if getattr(GameService, "_local_fishing_bonuses_installed", False) and not force:
        return
    if "cast_line" not in _ORIGINALS:
        _ORIGINALS["cast_line"] = getattr(GameService, "cast_line")
    GameService.cast_line = _patched_cast_line
    GameService._local_fishing_bonuses_installed = True


def main() -> None:
    print("活动钓点陪钓加成（patches/local_fishing_bonuses.py）")
    for line in describe():
        print(line)


if __name__ == "__main__":
    main()
