from __future__ import annotations

from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from typing import Any


TraitHandler = Callable[[MutableMapping[str, Any]], None]

TRAIT_PHASES = frozenset({
    "task_prepare",
    "instant_action",
    "asset_prepare",
    "output_draw",
    "quality_roll",
    "result_finalize",
    "exploration_event",
    "livestock_segment",
})


@dataclass(frozen=True)
class PartnerTraitDefinition:
    code: str
    name: str
    description: str
    handler: TraitHandler | None = None
    phases: frozenset[str] = frozenset()

    @property
    def implemented(self) -> bool:
        return self.handler is not None


_TRAITS: dict[str, PartnerTraitDefinition] = {}


def register_partner_trait(
    code: str,
    name: str,
    description: str,
    *,
    phases: Iterable[str] = ("task_prepare",),
    replace: bool = False,
):
    normalized = str(code).strip()
    if not normalized:
        raise ValueError("trait code is required")
    normalized_phases = frozenset(str(phase).strip() for phase in phases)
    unknown_phases = normalized_phases - TRAIT_PHASES
    if unknown_phases:
        raise ValueError(f"unknown partner trait phases: {', '.join(sorted(unknown_phases))}")
    if not normalized_phases:
        raise ValueError("implemented partner traits require at least one phase")

    def decorator(handler: TraitHandler) -> TraitHandler:
        if normalized in _TRAITS and not replace:
            raise ValueError(f"partner trait {normalized} is already registered")
        _TRAITS[normalized] = PartnerTraitDefinition(
            normalized,
            name,
            description,
            handler,
            normalized_phases,
        )
        return handler

    return decorator


def declare_partner_trait(code: str, name: str, description: str) -> None:
    normalized = str(code).strip()
    if not normalized:
        raise ValueError("trait code is required")
    if normalized in _TRAITS:
        raise ValueError(f"partner trait {normalized} is already registered")
    _TRAITS[normalized] = PartnerTraitDefinition(normalized, name, description)


def partner_trait_catalog() -> list[PartnerTraitDefinition]:
    return [_TRAITS[code] for code in sorted(_TRAITS, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))]


def partner_trait_codes() -> set[str]:
    return set(_TRAITS)


def execute_partner_traits(codes: list[str], context: MutableMapping[str, Any]) -> list[str]:
    executed: list[str] = []
    for code in codes:
        definition = _TRAITS.get(str(code))
        if definition is None:
            raise KeyError(f"unknown partner trait: {code}")
        if definition.handler is None:
            continue
        phase = str(context.get("phase") or "").strip()
        if phase and phase not in definition.phases:
            continue
        previous_code = context.get("trait_code")
        context["trait_code"] = definition.code
        try:
            definition.handler(context)
        finally:
            if previous_code is None:
                context.pop("trait_code", None)
            else:
                context["trait_code"] = previous_code
        executed.append(definition.code)
    return executed


def record_partner_trait_effect(
    context: MutableMapping[str, Any],
    effect: str,
    *,
    value: int | float | str | bool | None = None,
    params: dict[str, Any] | None = None,
    stacking_group: str = "",
) -> dict[str, Any]:
    """把已经展开的伙伴效果写入当前任务或资产快照。"""

    trait_code = str(context.get("trait_code") or "").strip()
    source_partner_id = str(context.get("source_partner_id") or "").strip()
    if not trait_code or not source_partner_id:
        raise ValueError("trait effect context requires trait_code and source_partner_id")
    entry: dict[str, Any] = {
        "source_type": "partner_trait",
        "trait_code": trait_code,
        "source_partner_id": source_partner_id,
        "phase": str(context.get("phase") or ""),
        "effect": str(effect).strip(),
    }
    if value is not None:
        entry["value"] = value
    if params:
        entry["params"] = dict(params)
    if stacking_group:
        entry["stacking_group"] = stacking_group
    context.setdefault("applied_effects", []).append(entry)
    return entry


for _code in ("1", "2", "3", "4"):
    declare_partner_trait(_code, f"{_code}号特性", "效果将在 Python 规则中定义")


def _industry_is(context: MutableMapping[str, Any], *industries: str) -> bool:
    return str(context.get("industry") or "") in industries


def _action_is(context: MutableMapping[str, Any], action: str) -> bool:
    return str(context.get("action") or "") == action


def _has_content_tag(context: MutableMapping[str, Any], *tags: str) -> bool:
    return bool(set(context.get("content_tags") or ()) & set(tags))


def _weather_is(context: MutableMapping[str, Any], *weather_ids: str) -> bool:
    world = context.get("world") or {}
    weather = world.get("weather") or {}
    return str(weather.get("id") or "") in weather_ids


def _multiply(
    context: MutableMapping[str, Any],
    field: str,
    multiplier: float,
    *,
    effect: str | None = None,
    stacking_group: str = "",
) -> None:
    context[field] = float(context.get(field, 1.0)) * multiplier
    record_partner_trait_effect(
        context,
        effect or field,
        value=multiplier,
        stacking_group=stacking_group,
    )


def _add(
    context: MutableMapping[str, Any],
    field: str,
    value: int | float,
    *,
    effect: str | None = None,
    stacking_group: str = "",
) -> None:
    context[field] = context.get(field, 0) + value
    record_partner_trait_effect(
        context,
        effect or field,
        value=value,
        stacking_group=stacking_group,
    )


def _reroll_one_quality(context: MutableMapping[str, Any]) -> None:
    record_partner_trait_effect(
        context,
        "reroll_one_quality_take_higher",
        params={"count": 1},
        stacking_group="quality_reroll",
    )


def _promote_lowest_quality(context: MutableMapping[str, Any], chance: float) -> None:
    record_partner_trait_effect(
        context,
        "promote_lowest_quality",
        params={"chance": chance, "levels": 1},
        stacking_group="quality_promotion",
    )


@register_partner_trait(
    "flow_treasure",
    "随流拾珍",
    "陪钓时，稀有鱼和大物的抽取权重提高12%。",
    phases=("instant_action",),
)
def _flow_treasure(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "aquatic") and _action_is(context, "fishing_cast"):
        _multiply(context, "rare_weight_multiplier", 1.12, stacking_group="fishing_rare_weight")


@register_partner_trait(
    "fodder_fields",
    "丰饲田",
    "农作产物可作饲料时，固定额外产出1件。",
    phases=("task_prepare",),
)
def _fodder_fields(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming") and _has_content_tag(context, "fodder"):
        _add(context, "yield_bonus", 1, stacking_group="flat_yield")


@register_partner_trait(
    "golden_line",
    "金色鱼线",
    "陪钓时，稀有鱼和大物的抽取权重提高15%。",
    phases=("instant_action",),
)
def _golden_line(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "aquatic") and _action_is(context, "fishing_cast"):
        _multiply(context, "rare_weight_multiplier", 1.15, stacking_group="fishing_rare_weight")


@register_partner_trait(
    "steady_craft",
    "熟练手作",
    "加工任务的品质能力增加15。",
    phases=("task_prepare",),
)
def _steady_craft(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "crafting"):
        _add(context, "quality_ability_bonus", 15, stacking_group="quality_ability")


@register_partner_trait(
    "dream_forage",
    "梦游拾遗",
    "执行采集任务时，额外抽取1次产出。",
    phases=("output_draw",),
)
def _dream_forage(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "gathering"):
        _add(context, "draw_bonus", 1, stacking_group="draw_count")


@register_partner_trait(
    "ore_chaser",
    "追脉",
    "采矿任务固定额外产出1件矿物。",
    phases=("task_prepare",),
)
def _ore_chaser(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "mining"):
        _add(context, "yield_bonus", 1, stacking_group="flat_yield")


@register_partner_trait(
    "rain_garden",
    "雨庭",
    "小雨天气开始农作时，品质能力增加20。",
    phases=("task_prepare",),
)
def _rain_garden(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming") and _weather_is(context, "rain"):
        _add(context, "quality_ability_bonus", 20, stacking_group="quality_ability")


@register_partner_trait(
    "varied_forage",
    "各有所获",
    "采集首次抽到已经出现的物品时，改从尚未出现的物品中重抽一次。",
    phases=("output_draw",),
)
def _varied_forage(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "gathering"):
        record_partner_trait_effect(
            context,
            "reroll_first_duplicate",
            stacking_group="output_variety",
        )


@register_partner_trait(
    "ghostfire_refinement",
    "鬼火精制",
    "农作或加工结算时，有30%概率将最低品质的一件产物提升一级。",
    phases=("result_finalize",),
)
def _ghostfire_refinement(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming", "crafting"):
        _promote_lowest_quality(context, 0.30)


@register_partner_trait(
    "deep_soil_edge",
    "厚土藏锋",
    "农作任务的品质能力提高10%。",
    phases=("task_prepare",),
)
def _deep_soil_edge(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming"):
        _multiply(context, "quality_ability_multiplier", 1.10, stacking_group="quality_ability")


@register_partner_trait(
    "listen_to_rock",
    "静听岩层",
    "采矿任务的品质能力提高12%。",
    phases=("task_prepare",),
)
def _listen_to_rock(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "mining"):
        _multiply(context, "quality_ability_multiplier", 1.12, stacking_group="quality_ability")


@register_partner_trait(
    "ancient_formula",
    "古方",
    "加工药品时，随机一件成品的品质重投一次并取较高值。",
    phases=("quality_roll",),
)
def _ancient_formula(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "crafting") and _has_content_tag(context, "medicine"):
        _reroll_one_quality(context)


@register_partner_trait(
    "overcast_worker",
    "阴翳作业",
    "多云或小雨天气开始农作、采集时，最终耗时减少12%。",
    phases=("task_prepare",),
)
def _overcast_worker(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming", "gathering") and _weather_is(context, "cloudy", "rain"):
        _multiply(context, "duration_multiplier", 0.88, stacking_group="duration")


@register_partner_trait(
    "herb_lore",
    "药草辨识",
    "采集池中存在药品时，保证本次任务至少获得1件药品。",
    phases=("output_draw",),
)
def _herb_lore(context: MutableMapping[str, Any]) -> None:
    if not _industry_is(context, "gathering"):
        return
    eligible_item_ids = [
        str(entry.get("item_id") or "")
        for entry in context.get("output_items") or ()
        if "medicine" in set(entry.get("tags") or ()) and entry.get("item_id")
    ]
    if eligible_item_ids:
        record_partner_trait_effect(
            context,
            "guarantee_tagged_output",
            params={
                "tag": "medicine",
                "count": 1,
                "eligible_item_ids": eligible_item_ids,
            },
            stacking_group="guaranteed_output",
        )


@register_partner_trait(
    "meticulous_farming",
    "精耕细作",
    "农作结算时，随机一件产物的品质重投一次并取较高值。",
    phases=("quality_roll",),
)
def _meticulous_farming(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming"):
        _reroll_one_quality(context)


@register_partner_trait(
    "warm_soil",
    "暖土催生",
    "晴朗天气开始农作时，最终耗时减少10%。",
    phases=("task_prepare",),
)
def _warm_soil(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming") and _weather_is(context, "sunny"):
        _multiply(context, "duration_multiplier", 0.90, stacking_group="duration")


@register_partner_trait(
    "swift_wind_work",
    "疾风行",
    "采集或采矿任务的最终耗时减少12%。",
    phases=("task_prepare",),
)
def _swift_wind_work(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "gathering", "mining"):
        _multiply(context, "duration_multiplier", 0.88, stacking_group="duration")


@register_partner_trait(
    "ore_heart",
    "矿心",
    "采矿任务的品质能力增加20。",
    phases=("task_prepare",),
)
def _ore_heart(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "mining"):
        _add(context, "quality_ability_bonus", 20, stacking_group="quality_ability")


@register_partner_trait(
    "falling_star",
    "星落",
    "农作或采集结算时，有20%概率将最低品质的一件产物提升一级。",
    phases=("result_finalize",),
)
def _falling_star(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "farming", "gathering"):
        _promote_lowest_quality(context, 0.20)


@register_partner_trait(
    "moonlit_selection",
    "清辉筛选",
    "采集、加工或普通钓获时，第一件可品质化产物重投品质并取较高值。",
    phases=("quality_roll", "instant_action"),
)
def _moonlit_selection(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "gathering", "crafting") or (
        _industry_is(context, "aquatic") and _action_is(context, "fishing_cast")
    ):
        _reroll_one_quality(context)


@register_partner_trait(
    "peaceful_cooking",
    "安作",
    "加工食物结算时，有30%概率将最低品质的一件成品提升一级。",
    phases=("result_finalize",),
)
def _peaceful_cooking(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "crafting") and _has_content_tag(context, "food"):
        _promote_lowest_quality(context, 0.30)


@register_partner_trait(
    "seasonal_rhythm",
    "循时而作",
    "晴天农作或雨天采集时，品质能力增加15。",
    phases=("task_prepare",),
)
def _seasonal_rhythm(context: MutableMapping[str, Any]) -> None:
    if (
        (_industry_is(context, "farming") and _weather_is(context, "sunny"))
        or (_industry_is(context, "gathering") and _weather_is(context, "rain"))
    ):
        _add(context, "quality_ability_bonus", 15, stacking_group="quality_ability")


@register_partner_trait(
    "fodder_artisan",
    "备粮匠",
    "加工饲料时固定额外产出1件。",
    phases=("task_prepare",),
)
def _fodder_artisan(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "crafting") and _has_content_tag(context, "fodder"):
        _add(context, "yield_bonus", 1, stacking_group="flat_yield")


def _livestock_segment(context: MutableMapping[str, Any]) -> bool:
    return _industry_is(context, "livestock") and _action_is(context, "livestock_segment")


def _livestock_birth(context: MutableMapping[str, Any]) -> bool:
    return _industry_is(context, "livestock") and str(context.get("action") or "") in {
        "livestock_breed",
        "livestock_incubate",
    }


@register_partner_trait(
    "herding_heart",
    "牧心",
    "驻场畜牧设施的品质能力增加20。",
    phases=("livestock_segment",),
)
def _herding_heart(context: MutableMapping[str, Any]) -> None:
    if _livestock_segment(context):
        _add(context, "quality_bonus", 20, stacking_group="livestock_quality")


@register_partner_trait(
    "generous_keep",
    "厚养",
    "驻场畜牧设施中亲密度已满的牲畜，特殊产出概率提高2个百分点。",
    phases=("livestock_segment",),
)
def _generous_keep(context: MutableMapping[str, Any]) -> None:
    if _livestock_segment(context):
        _add(context, "special_chance_bonus", 0.02, stacking_group="livestock_special")


@register_partner_trait(
    "full_larder",
    "囤仓",
    "驻场畜牧设施的饲料消耗减少20%，产出溢出上限提高1个周期。",
    phases=("livestock_segment",),
)
def _full_larder(context: MutableMapping[str, Any]) -> None:
    if _livestock_segment(context):
        _multiply(context, "feed_multiplier", 0.80, stacking_group="livestock_feed")
        _add(context, "overflow_bonus", 1, stacking_group="livestock_overflow")


@register_partner_trait(
    "unhurried",
    "慢条斯理",
    "驻场畜牧设施的产出溢出上限提高1个周期。",
    phases=("livestock_segment",),
)
def _unhurried(context: MutableMapping[str, Any]) -> None:
    if _livestock_segment(context):
        _add(context, "overflow_bonus", 1, stacking_group="livestock_overflow")


@register_partner_trait(
    "matchmaker",
    "相看",
    "在驻场畜牧设施配种或孵化时，子代的每条基因各重投一次并取较高值。",
    phases=("instant_action",),
)
def _matchmaker(context: MutableMapping[str, Any]) -> None:
    if _livestock_birth(context):
        _add(context, "gene_rerolls", 1, stacking_group="livestock_gene_reroll")


@register_partner_trait(
    "fine_combing",
    "细梳",
    "照料驻场畜牧设施的牲畜时亲密度额外增加4点；亲密度满时的品质系数额外提高0.1。",
    phases=("instant_action", "livestock_segment"),
)
def _fine_combing(context: MutableMapping[str, Any]) -> None:
    if _industry_is(context, "livestock") and _action_is(context, "livestock_care"):
        _add(context, "affection_per_care_bonus", 4, stacking_group="livestock_affection")
    elif _livestock_segment(context):
        _add(context, "affection_quality_bonus", 0.001, stacking_group="livestock_affection_quality")
