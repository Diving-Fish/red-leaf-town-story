from __future__ import annotations

from red_leaf_town.content import GameContent, RewardDefinition
from red_leaf_town.domain.quality import QUALITY_NAMES
from red_leaf_town.partner_content import PartnerCatalog


def serialize_reward(reward: RewardDefinition, content: GameContent, partners: PartnerCatalog) -> dict:
    """把奖励配置摊成前端能直接渲染的样子。剧情和传送门共用这一份。"""
    items = content.item_map
    partner_map = partners.partner_map
    return {
        "coins": reward.coins,
        "experience": reward.experience,
        "talent_points": reward.talent_points,
        "maple_flame": reward.maple_flame,
        "guide_leaves": reward.guide_leaves,
        "items": [
            {
                **entry.model_dump(),
                "name": items[entry.item_id].name if entry.item_id in items else entry.item_id,
                "icon": items[entry.item_id].icon if entry.item_id in items else "package",
                "quality_name": QUALITY_NAMES.get(entry.quality),
            }
            for entry in reward.items
        ],
        "partners": [
            {
                "partner_id": partner_id,
                "name": partner_map[partner_id].name if partner_id in partner_map else partner_id,
            }
            for partner_id in reward.partner_ids
        ],
        "empty": reward.empty,
    }


def validate_reward_references(reward: RewardDefinition, content: GameContent, partners: PartnerCatalog, label: str) -> None:
    """奖励引用的物品和伙伴都必须存在，否则发放时会静默少给东西。"""
    unknown_items = {entry.item_id for entry in reward.items} - set(content.item_map)
    if unknown_items:
        raise ValueError(f"{label} rewards unknown items: {', '.join(sorted(unknown_items))}")
    for entry in reward.items:
        if entry.quality and not content.item_map[entry.item_id].has_quality:
            raise ValueError(f"{label} rewards a quality {entry.item_id} cannot have")
    unknown_partners = set(reward.partner_ids) - set(partners.partner_map)
    if unknown_partners:
        raise ValueError(f"{label} rewards unknown partners: {', '.join(sorted(unknown_partners))}")
