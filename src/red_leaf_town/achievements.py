from __future__ import annotations

from red_leaf_town.content import AchievementDefinition, GameContent
from red_leaf_town.domain.models import AchievementCompletionState, PlayerState, ProductionResultSnapshot


TIER_NAMES = {"blue": "蓝色", "purple": "紫色", "gold": "金色"}


def record_production_collection(
    player: PlayerState,
    industry: str,
    content_id: str,
    results: list[ProductionResultSnapshot],
) -> None:
    stats = player.achievement_stats
    stats.production_collections[industry] = stats.production_collections.get(industry, 0) + 1
    if industry == "farming" and content_id not in stats.harvested_crop_ids:
        stats.harvested_crop_ids.append(content_id)
    if industry == "crafting" and content_id not in stats.crafted_recipe_ids:
        stats.crafted_recipe_ids.append(content_id)
    stats.max_production_quality = max(
        stats.max_production_quality,
        max((result.quality for result in results), default=0),
    )


def evaluate_achievements(player: PlayerState, content: GameContent, now: int) -> list[dict]:
    completed = {entry.achievement_id for entry in player.achievements}
    newly_completed: list[dict] = []
    for definition in content.achievements:
        if definition.id in completed:
            continue
        current, target = achievement_progress(player, definition, content)
        if current < target:
            continue
        player.achievements.append(
            AchievementCompletionState(achievement_id=definition.id, completed_at=now),
        )
        completed.add(definition.id)
        newly_completed.append({
            "achievement_id": definition.id,
            "name": definition.name,
            "tier": definition.tier,
            "tier_name": TIER_NAMES[definition.tier],
            "reward_maple_flame": definition.reward_maple_flame,
        })
    return newly_completed


def reconcile_legacy_auto_rewards(player: PlayerState, content: GameContent) -> None:
    if player.achievement_auto_rewards_reconciled:
        return
    definitions = content.achievement_map
    for progress in player.achievements:
        definition = definitions.get(progress.achievement_id)
        if definition is None or progress.claimed_at:
            continue
        reward = definition.reward_maple_flame
        if player.maple_flame >= reward:
            player.maple_flame -= reward
        else:
            # 奖励已经被消费时不能把货币扣成负数；视作已经领取，避免再次发放。
            progress.claimed_at = progress.completed_at
    player.achievement_auto_rewards_reconciled = True


def achievement_snapshot(player: PlayerState, content: GameContent) -> dict:
    completed = {entry.achievement_id: entry for entry in player.achievements}
    entries = []
    for definition in content.achievements:
        current, target = achievement_progress(player, definition, content)
        progress = completed.get(definition.id)
        completed_at = progress.completed_at if progress else 0
        claimed_at = progress.claimed_at if progress else 0
        entries.append({
            "achievement_id": definition.id,
            "name": definition.name,
            "description": definition.description,
            "tier": definition.tier,
            "tier_name": TIER_NAMES[definition.tier],
            "reward_maple_flame": definition.reward_maple_flame,
            "current": min(current, target),
            "target": target,
            "completed": bool(completed_at),
            "completed_at": completed_at or None,
            "claimed": bool(claimed_at),
            "claimed_at": claimed_at or None,
            "claimable": bool(completed_at and not claimed_at),
        })
    completed_entries = [entry for entry in entries if entry["completed"]]
    claimed_entries = [entry for entry in entries if entry["claimed"]]
    claimable_entries = [entry for entry in entries if entry["claimable"]]
    return {
        "completed": len(completed_entries),
        "total": len(entries),
        "claimed": len(claimed_entries),
        "claimable": len(claimable_entries),
        "maple_flame_earned": sum(entry["reward_maple_flame"] for entry in claimed_entries),
        "claimable_maple_flame": sum(entry["reward_maple_flame"] for entry in claimable_entries),
        "entries": entries,
    }


def achievement_progress(
    player: PlayerState,
    definition: AchievementDefinition,
    content: GameContent,
) -> tuple[int, int]:
    hook = definition.condition.hook
    params = definition.condition.params
    stats = player.achievement_stats

    if hook == "story_seen":
        return int(str(params["story_id"]) in player.seen_story_ids), 1
    if hook == "production_collections":
        target = int(params.get("count", 1))
        return stats.production_collections.get(str(params["industry"]), 0), target
    if hook == "partners_owned":
        return len(player.owned_partners), int(params["count"])
    if hook == "player_level":
        return player.level, int(params["level"])
    if hook == "crops_harvested":
        required = {str(entry) for entry in params["crop_ids"]}
        return len(required & set(stats.harvested_crop_ids)), len(required)
    if hook == "recipes_crafted":
        required = {str(entry) for entry in params["recipe_ids"]}
        return len(required & set(stats.crafted_recipe_ids)), len(required)
    if hook == "commissions_completed":
        current = stats.own_commissions_completed if params.get("own_only") else stats.commissions_completed
        return current, int(params["count"])
    if hook == "talents_unlocked":
        return len(player.talent_nodes), int(params["count"])
    if hook == "pond_harvested":
        return stats.pond_harvested.get(str(params["species_id"]), 0), int(params["count"])
    if hook == "fish_codex_entries":
        return len(player.fish_codex.entries), int(params["count"])
    if hook == "big_catch_caught":
        big_catch_ids = {
            spot.big_catch.item_id
            for spot in content.fishing_spots
            if spot.big_catch is not None
        }
        return int(any(entry.item_id in big_catch_ids for entry in player.fish_codex.entries)), 1
    if hook == "max_production_quality":
        return stats.max_production_quality, int(params["quality"])
    if hook == "portal_completed":
        portal_id = str(params["portal_id"])
        return int(any(entry.portal_id == portal_id and entry.completed_at for entry in player.portals)), 1
    raise ValueError(f"unsupported achievement hook: {hook}")
