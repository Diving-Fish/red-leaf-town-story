from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any


TraitHandler = Callable[[MutableMapping[str, Any]], None]


@dataclass(frozen=True)
class PartnerTraitDefinition:
    code: str
    name: str
    description: str
    handler: TraitHandler | None = None

    @property
    def implemented(self) -> bool:
        return self.handler is not None


_TRAITS: dict[str, PartnerTraitDefinition] = {}


def register_partner_trait(
    code: str,
    name: str,
    description: str,
    *,
    replace: bool = False,
):
    normalized = str(code).strip()
    if not normalized:
        raise ValueError("trait code is required")

    def decorator(handler: TraitHandler) -> TraitHandler:
        if normalized in _TRAITS and not replace:
            raise ValueError(f"partner trait {normalized} is already registered")
        _TRAITS[normalized] = PartnerTraitDefinition(normalized, name, description, handler)
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
        definition.handler(context)
        executed.append(definition.code)
    return executed


for _code in ("1", "2", "3", "4"):
    declare_partner_trait(_code, f"{_code}号特性", "效果将在 Python 规则中定义")

