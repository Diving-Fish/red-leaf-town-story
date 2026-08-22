from __future__ import annotations

from red_leaf_town.content import GameContent

from .models import GatheringSiteState, PlayerState, PlotState


def settle_stamina(player: PlayerState, content: GameContent, now: int) -> None:
    level = content.level_definition(player.level)
    cap = level.stamina_cap
    if player.stamina >= cap:
        player.stamina = cap
        player.stamina_updated_at = now
        return
    elapsed = max(0, now - player.stamina_updated_at)
    gained = elapsed // content.stamina.restore_seconds
    if gained <= 0:
        return
    player.stamina = min(cap, player.stamina + gained)
    if player.stamina >= cap:
        player.stamina_updated_at = now
    else:
        player.stamina_updated_at += gained * content.stamina.restore_seconds


def consume_stamina(player: PlayerState, amount: int, content: GameContent, now: int) -> None:
    settle_stamina(player, content, now)
    if player.stamina < amount:
        raise ValueError("体力不足")
    was_full = player.stamina >= content.level_definition(player.level).stamina_cap
    player.stamina -= amount
    if was_full:
        player.stamina_updated_at = now


def grant_experience(player: PlayerState, amount: int, content: GameContent) -> list[int]:
    if amount < 0:
        raise ValueError("经验值不能为负数")
    previous_level = player.level
    player.experience += amount
    player.level = content.level_for_xp(player.experience).level
    unlocked_levels = list(range(previous_level + 1, player.level + 1))
    normalize_plot_slots(player, content)
    normalize_gathering_sites(player, content)
    return unlocked_levels


def normalize_plot_slots(player: PlayerState, content: GameContent) -> None:
    target = content.level_definition(player.level).plot_slots
    current = {plot.slot: plot for plot in player.plots}
    player.plots = [current.get(slot, PlotState(slot=slot)) for slot in range(target)]


def normalize_gathering_sites(player: PlayerState, content: GameContent) -> None:
    current = {site.site_id: site for site in player.gathering_sites}
    player.gathering_sites = [
        current.get(definition.id, GatheringSiteState(site_id=definition.id))
        for definition in content.gathering_sites
        if definition.min_level <= player.level
    ]
