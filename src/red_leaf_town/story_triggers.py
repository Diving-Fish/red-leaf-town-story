from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


CUE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(:[a-z0-9_\-]{1,64})?$")
MAX_CONDITION_DEPTH = 4


@dataclass(frozen=True)
class StoryContext:
    player: Any
    cue: str = ""
    now: int = 0


TriggerHook = Callable[[StoryContext, dict[str, Any]], bool]
TriggerDescription = Callable[[dict[str, Any]], str]
TriggerValidator = Callable[[dict[str, Any]], None]
_HOOKS: dict[str, tuple[TriggerHook, TriggerDescription, TriggerValidator]] = {}


def register_story_trigger_hook(code: str, description: TriggerDescription, validator: TriggerValidator):
    def decorator(function: TriggerHook):
        _HOOKS[code] = (function, description, validator)
        return function
    return decorator


def story_trigger_hook_exists(code: str) -> bool:
    return code in _HOOKS


def story_trigger_hook_codes() -> list[str]:
    return sorted(_HOOKS)


def validate_story_trigger(hook: str, params: dict[str, Any]) -> None:
    registered = _HOOKS.get(hook)
    if registered is None:
        raise ValueError(f"unknown story trigger hook: {hook}")
    registered[2](params)


def evaluate_story_trigger(context: StoryContext, hook: str, params: dict[str, Any]) -> bool:
    registered = _HOOKS.get(hook)
    if registered is None:
        raise ValueError(f"unknown story trigger hook: {hook}")
    return registered[0](context, params)


def describe_story_trigger(hook: str, params: dict[str, Any]) -> str:
    registered = _HOOKS.get(hook)
    if registered is None:
        return "触发条件不可用"
    return registered[1](params)


def validate_story_cue(cue: str) -> str:
    candidate = str(cue or "").strip()
    if not CUE_PATTERN.fullmatch(candidate):
        raise ValueError("story cue must look like view:farm or action:harvest")
    return candidate


def _require_positive_int(params: dict[str, Any], key: str, minimum: int = 1) -> int:
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"story trigger requires an integer {key} of at least {minimum}")
    return value


def _require_identifier(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"story trigger requires a non-empty {key}")
    return value.strip()


def _validate_conditions(params: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
    if depth >= MAX_CONDITION_DEPTH:
        raise ValueError("story trigger conditions are nested too deeply")
    conditions = params.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("story trigger requires a non-empty conditions list")
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("each story trigger condition must be an object")
        hook = _require_identifier(condition, "hook")
        nested = condition.get("params") or {}
        if not isinstance(nested, dict):
            raise ValueError("story trigger condition params must be an object")
        if hook in ("all_of", "any_of", "none_of"):
            _validate_conditions(nested, depth + 1)
            continue
        validate_story_trigger(hook, nested)
    return conditions


def _evaluate_conditions(context: StoryContext, params: dict[str, Any]):
    for condition in params.get("conditions", []):
        yield evaluate_story_trigger(context, str(condition["hook"]), condition.get("params") or {})


@register_story_trigger_hook(
    "cue",
    lambda params: f"收到信号 {params['cue']}",
    lambda params: validate_story_cue(_require_identifier(params, "cue")),
)
def _cue(context: StoryContext, params: dict[str, Any]) -> bool:
    return context.cue == str(params["cue"]).strip()


@register_story_trigger_hook(
    "player_level",
    lambda params: f"居民等级达到 {int(params['level'])} 级",
    lambda params: _require_positive_int(params, "level"),
)
def _player_level(context: StoryContext, params: dict[str, Any]) -> bool:
    return context.player.level >= int(params["level"])


@register_story_trigger_hook(
    "has_item",
    lambda params: f"持有 {int(params.get('quantity', 1))} 个 {params['item_id']}",
    lambda params: (_require_identifier(params, "item_id"), _require_positive_int({"quantity": params.get("quantity", 1)}, "quantity")),
)
def _has_item(context: StoryContext, params: dict[str, Any]) -> bool:
    quantities = context.player.inventory.get(str(params["item_id"]), {})
    return sum(quantities.values()) >= int(params.get("quantity", 1))


@register_story_trigger_hook(
    "owns_partner",
    lambda params: f"已经拥有伙伴 {params['partner_id']}",
    lambda params: _require_identifier(params, "partner_id"),
)
def _owns_partner(context: StoryContext, params: dict[str, Any]) -> bool:
    partner_id = str(params["partner_id"]).strip()
    return any(entry.partner_id == partner_id for entry in context.player.owned_partners)


@register_story_trigger_hook(
    "talent_unlocked",
    lambda params: f"已经点亮天赋 {params['node_id']}",
    lambda params: _require_identifier(params, "node_id"),
)
def _talent_unlocked(context: StoryContext, params: dict[str, Any]) -> bool:
    return str(params["node_id"]).strip() in context.player.talent_nodes


@register_story_trigger_hook(
    "all_of",
    lambda params: "同时满足：" + "、".join(
        describe_story_trigger(str(entry["hook"]), entry.get("params") or {}) for entry in params["conditions"]
    ),
    _validate_conditions,
)
def _all_of(context: StoryContext, params: dict[str, Any]) -> bool:
    return all(_evaluate_conditions(context, params))


@register_story_trigger_hook(
    "any_of",
    lambda params: "满足任意一项：" + "、".join(
        describe_story_trigger(str(entry["hook"]), entry.get("params") or {}) for entry in params["conditions"]
    ),
    _validate_conditions,
)
def _any_of(context: StoryContext, params: dict[str, Any]) -> bool:
    return any(_evaluate_conditions(context, params))


@register_story_trigger_hook(
    "none_of",
    lambda params: "均不满足：" + "、".join(
        describe_story_trigger(str(entry["hook"]), entry.get("params") or {}) for entry in params["conditions"]
    ),
    _validate_conditions,
)
def _none_of(context: StoryContext, params: dict[str, Any]) -> bool:
    return not any(_evaluate_conditions(context, params))
