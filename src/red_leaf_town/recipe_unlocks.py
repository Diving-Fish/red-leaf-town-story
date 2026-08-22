from __future__ import annotations

from collections.abc import Callable
from typing import Any


UnlockHook = Callable[[Any, dict[str, int | str | bool]], bool]
UnlockDescription = Callable[[dict[str, int | str | bool]], str]
UnlockValidator = Callable[[dict[str, int | str | bool]], None]
_HOOKS: dict[str, tuple[UnlockHook, UnlockDescription, UnlockValidator]] = {}


def register_recipe_unlock_hook(code: str, description: UnlockDescription, validator: UnlockValidator):
    def decorator(function: UnlockHook):
        _HOOKS[code] = (function, description, validator)
        return function
    return decorator


def recipe_unlock_hook_exists(code: str) -> bool:
    return code in _HOOKS


def validate_recipe_unlock(hook: str, params: dict[str, int | str | bool]) -> None:
    registered = _HOOKS.get(hook)
    if registered is None:
        raise ValueError(f"unknown recipe unlock hook: {hook}")
    registered[2](params)


def evaluate_recipe_unlock(player, hook: str, params: dict[str, int | str | bool]) -> bool:
    registered = _HOOKS.get(hook)
    if registered is None:
        raise ValueError(f"unknown recipe unlock hook: {hook}")
    return registered[0](player, params)


def describe_recipe_unlock(hook: str, params: dict[str, int | str | bool]) -> str:
    registered = _HOOKS.get(hook)
    if registered is None:
        return "解锁条件不可用"
    return registered[1](params)


def _validate_player_level(params: dict[str, int | str | bool]) -> None:
    level = params.get("level")
    if not isinstance(level, int) or isinstance(level, bool) or level < 1:
        raise ValueError("player_level recipe unlock hook requires a positive integer level")


@register_recipe_unlock_hook(
    "player_level",
    lambda params: f"居民等级达到 {int(params['level'])} 级",
    _validate_player_level,
)
def _player_level(player, params: dict[str, int | str | bool]) -> bool:
    _validate_player_level(params)
    return player.level >= int(params["level"])
