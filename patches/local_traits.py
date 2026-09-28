"""活动限定伙伴特性（独立模块，不改动 partner_traits.py）。

上游把特性注册表做成了运行时 dict（partner_traits._TRAITS），并公开了
register_partner_trait 装饰器——这就是设计好的扩展点。本模块在应用
启动时被 import，注册进同一张注册表，对引擎来说与上游特性毫无区别。

写一条新特性的全部成本：
    1. 在本文件用 @register_partner_trait 注册（code/name/description/handler）
    2. 在 data/partners.json 里把 code 填进伙伴的 trait_codes
    3. 重启后端

handler 在对应 phase 被调用，直接改 context 字段：
    exploration_event 常用字段：
        check_bonus                检定调整值加成（叠加）
        dice_adjustment            骰子加值（优势 ≈ +1）
        critical_success_min       大成功最小自然数（默认 20，改成 19 即 19-20 大成功）
        ordinary_failure_stamina_reduction  普通失败附加体力减免
        reward_quantity_multiplier 奖励数量倍率
        quality_ability_bonus      战利品品质加成
        leader_partner_id          本趟探索的领队（队伍一号位）；source_partner_id 是
                                   当前正在执行特性的伙伴——两者相等即「她站在一号位」
    生产任务（task_prepare）常用：
        task_time_multiplier / task_output_multiplier / task_quality_bonus

可复用上游辅助函数（下划线开头但就是给特性作者用的）：
    _exploration_check(ctx)  当前是否处于探索检定
    _exploration_actor(ctx)  当前检定者是否为本特性所属伙伴
    _add(ctx, field, n) / _multiply(ctx, field, x)
"""

from __future__ import annotations

from typing import Any, MutableMapping

from red_leaf_town.partner_traits import (
    _add,
    _exploration_check,
    _industry_is,
    _weather_is,
    record_partner_trait_effect,
    register_partner_trait,
)


@register_partner_trait(
    "stage_presence",
    "舞台气场",
    "顾祇SP探索担任领队时，全队探索检定调整值+1；敏捷检定额外再+1。偶像站上 C 位，聚光灯就会照过来。",
    phases=("exploration_event",),
)
def _stage_presence(context: MutableMapping[str, Any]) -> None:
    """舞台气场：只有站在一号位（领队）时才点亮，敏捷再吃一档。

    「在队」这件事本身不用在这里判断：service 的特性阶段按 run.partner_ids
    逐个伙伴执行（_execute_partner_trait_phase），她不在队伍里 handler 根本不会
    被调用。这里额外管的是「队内位置」——只有 source_partner_id 恰好等于
    run.leader_partner_id（前端队伍选择器的一号位「领队」）时才生效，
    和上游「王骑号令」判断领队的写法一致。
    """

    if not _exploration_check(context):
        return
    leader_partner_id = str(context.get("leader_partner_id") or "")
    if not leader_partner_id or leader_partner_id != str(context.get("source_partner_id") or ""):
        return
    _add(context, "check_bonus", 1, stacking_group="exploration_check_bonus")
    if context.get("check_attribute") == "agility":
        _add(
            context,
            "check_bonus",
            1,
            effect="stage_presence_agility_edge",
            stacking_group="exploration_check_bonus",
        )


@register_partner_trait(
    "summer_mood",
    "夏日心情",
    "采集与水产任务的品质能力+25；晴朗天气下开始采集任务时，额外抽取1次产出。",
    phases=("task_prepare", "output_draw"),
)
def _summer_mood(context: MutableMapping[str, Any]) -> None:
    """夏日心情：绯恩SP 专属，覆盖她的「采集 + 水产」双倾向。

        task_prepare  采集/水产任务的品质能力 +25（无天气门槛，稳定吃）
        output_draw   晴朗天气下做采集任务，额外抽 1 次产出（水产不吃这档）

    强度对标：上游「矿心」（采矿品质+20）是单行业无门槛的最高档，
    这里双行业同档再叠一档晴天抽取，配得上 5★ SP。
    """

    phase = str(context.get("phase") or "")
    if phase == "task_prepare":
        if _industry_is(context, "gathering", "aquatic"):
            _add(context, "quality_ability_bonus", 25, stacking_group="quality_ability")
    elif phase == "output_draw":
        if _industry_is(context, "gathering") and _weather_is(context, "sunny"):
            _add(context, "draw_bonus", 1, stacking_group="draw_count")
