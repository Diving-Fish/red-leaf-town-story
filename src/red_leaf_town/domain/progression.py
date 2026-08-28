from __future__ import annotations

from red_leaf_town.content import GameContent

from .models import (
    CraftingStationState,
    GatheringSiteState,
    LivestockFacilityState,
    MiningSiteState,
    PlayerState,
    PlotState,
)


def settle_stamina(player: PlayerState, content: GameContent, now: int) -> None:
    level = content.level_definition(player.level)
    cap = level.stamina_cap
    if player.stamina >= cap:
        # 体力药和枫火购买允许把体力顶到上限之上。溢出期间不回不扣，只把计时归零，
        # 掉回上限以下时就从那一刻重新开始攒。这里不能夹回 cap，否则溢出立刻蒸发。
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


def refund_stamina(player: PlayerState, amount: int, content: GameContent, now: int) -> None:
    """退还已经花掉的体力（取消任务）。退回来的不算额外补给，照旧封在上限。"""
    if amount <= 0:
        return
    settle_stamina(player, content, now)
    cap = content.level_definition(player.level).stamina_cap
    # 已经溢出的体力不能被这次退还夹回上限，所以取「原值」和「补到上限」里大的那个。
    player.stamina = max(player.stamina, min(cap, player.stamina + amount))


def grant_stamina(player: PlayerState, amount: int, content: GameContent, now: int) -> int:
    """体力药、枫火购买这类外部补给，可以把体力顶到上限之上。返回实际加了多少。"""
    if amount <= 0:
        return 0
    settle_stamina(player, content, now)
    player.stamina += amount
    return amount


def grant_experience(player: PlayerState, amount: int, content: GameContent) -> list[int]:
    if amount < 0:
        raise ValueError("经验值不能为负数")
    previous_level = player.level
    player.experience += amount
    player.level = content.level_for_xp(player.experience).level
    unlocked_levels = list(range(previous_level + 1, player.level + 1))
    normalize_plot_slots(player, content)
    normalize_gathering_sites(player, content)
    normalize_crafting_stations(player, content)
    normalize_mining_sites(player, content)
    normalize_ponds(player, content)
    normalize_livestock(player, content)
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


def normalize_crafting_stations(player: PlayerState, content: GameContent) -> None:
    current = {station.station_id: station for station in player.crafting_stations}
    player.crafting_stations = [
        current.get(definition.id, CraftingStationState(station_id=definition.id))
        for definition in content.crafting_stations
        if definition.min_level <= player.level
    ]


def normalize_mining_sites(player: PlayerState, content: GameContent) -> None:
    current = {site.site_id: site for site in player.mining_sites}
    player.mining_sites = [
        current.get(definition.id, MiningSiteState(site_id=definition.id))
        for definition in content.mining_sites
        if definition.min_level <= player.level
    ]


def normalize_ponds(player: PlayerState, content: GameContent) -> None:
    """鱼塘要花红叶币挖，不随等级白送，所以这里只剔除内容里已经不存在的塘并保持顺序。"""

    order = {definition.id: index for index, definition in enumerate(content.ponds)}
    player.ponds = sorted(
        (pond for pond in player.ponds if pond.pond_id in order),
        key=lambda pond: order[pond.pond_id],
    )


def normalize_livestock(player: PlayerState, content: GameContent, now: int = 0) -> None:
    """散养地到等级白送，鸡舍和畜栏要建。被回收的设施不再补发。

    动物跟着设施走：设施没了（内容删改）动物也留不住，否则会出现无处安放的孤儿个体。
    """

    order = {definition.id: index for index, definition in enumerate(content.livestock_facilities)}
    current = {facility.facility_id: facility for facility in player.livestock_facilities}
    retired = {
        definition.replaces
        for definition in content.livestock_facilities
        if definition.replaces and definition.id in current
    }
    facilities: list[LivestockFacilityState] = []
    for definition in content.livestock_facilities:
        existing = current.get(definition.id)
        if existing is not None:
            if definition.id in retired:
                continue
            facilities.append(existing)
            continue
        if definition.granted and definition.min_level <= player.level and definition.id not in retired:
            facilities.append(LivestockFacilityState(facility_id=definition.id, last_settled_at=now))
    player.livestock_facilities = sorted(facilities, key=lambda entry: order[entry.facility_id])

    live = {facility.facility_id for facility in player.livestock_facilities}
    species = content.livestock_species_map
    player.animals = [
        animal
        for animal in player.animals
        if animal.facility_id in live and animal.species_id in species
    ]
