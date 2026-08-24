from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


def partner(partner_id: str, industry: str) -> PartnerDefinition:
    return PartnerDefinition.model_validate({
        "id": partner_id,
        "name": partner_id,
        "rarity": 4,
        "growth_curve": "linear",
        "tendencies": [{"industry": industry, "level_1": 40, "level_60": 120}],
        "avatar_crops": [
            {"breakthrough": stage, "x": 0, "y": 0, "w": 1, "h": 1}
            for stage in range(3)
        ],
    })


@pytest.fixture
def game():
    content = load_content().model_copy(deep=True)
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    catalog = PartnerCatalog(partners=[
        partner("gather_one", "gathering"),
        partner("miner", "mining"),
        partner("artisan", "crafting"),
    ])
    service = GameService(
        content,
        repository,
        clock=clock,
        rng=random.Random(7),
        partner_catalog_loader=lambda: catalog,
    )
    player = service.ensure_player("cancel-sub", "取消居民")
    for partner_id in ("gather_one", "miner", "artisan"):
        service.admin_grant_partner(player.player_id, partner_id)
    return service, repository, clock, player


def reach_level(repository, player_id: str, experience: int):
    repository.update(player_id, lambda state: setattr(state, "experience", experience))


def test_cancel_planting_refunds_seed_and_start_task_item_and_resets_plot(game):
    service, repository, _, player = game
    service.buy("cancel-sub", "carrot_seed", 1)
    repository.update(player.player_id, lambda state: state.task_items.update({"thick_soil_fertilizer": 1}))

    service.plant("cancel-sub", 0, "carrot", "thick_soil_fertilizer")
    mid_state = repository.get(player.player_id)
    assert mid_state.inventory.get("carrot_seed") is None
    assert mid_state.task_items.get("thick_soil_fertilizer") is None

    cancelled = service.cancel_task("cancel-sub", "farming", "0")
    plot = cancelled["state"]["plots"][0]
    assert plot["empty"] is True
    assert plot["task_snapshot"] is None

    after = repository.get(player.player_id)
    assert after.inventory["carrot_seed"][0] == 1
    assert after.task_items["thick_soil_fertilizer"] == 1


def test_cancel_gathering_releases_site_without_refunding_items(game):
    service, repository, _, player = game
    service.assign_gathering_partner("cancel-sub", "maple_forest", "gather_one")
    service.start_gathering("cancel-sub", "maple_forest", "collect_maple_wood")

    cancelled = service.cancel_task("cancel-sub", "gathering", "maple_forest")
    site = cancelled["state"]["gathering_sites"][0]
    assert site["empty"] is True
    assert site["task_snapshot"] is None
    assert site["assigned_partner_ids"] == ["gather_one"]

    # partner assignment survives cancellation, so the site can be restarted immediately
    restarted = service.start_gathering("cancel-sub", "maple_forest", "collect_maple_wood")
    assert restarted["state"]["gathering_sites"][0]["task_snapshot"] is not None


def test_cancel_crafting_refunds_consumed_inputs_and_stamina(game):
    service, repository, _, player = game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("cancel-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {1: 1, 3: 2}}))

    before_stamina = repository.get(player.player_id).stamina
    started = service.start_crafting("cancel-sub", "town_workbench", "saw_maple_plank")
    assert repository.get(player.player_id).inventory["maple_wood"] == {3: 1}
    assert repository.get(player.player_id).stamina == before_stamina - 1

    cancelled = service.cancel_task("cancel-sub", "crafting", "town_workbench")
    station = cancelled["state"]["crafting_stations"][0]
    assert station["empty"] is True
    assert station["task_snapshot"] is None

    after = repository.get(player.player_id)
    assert after.inventory["maple_wood"] == {1: 1, 3: 2}
    assert after.stamina == before_stamina
    assert started["result"]["consumed_inputs"] == cancelled["result"]["refunded_inputs"]


def test_cancel_mining_refunds_stamina(game):
    service, repository, _, player = game
    reach_level(repository, player.player_id, 20)

    before_stamina = repository.get(player.player_id).stamina
    service.start_mining("cancel-sub", "copper_foothill", "mine_red_copper")
    assert repository.get(player.player_id).stamina == before_stamina - 5

    cancelled = service.cancel_task("cancel-sub", "mining", "copper_foothill")
    site = cancelled["state"]["mining_sites"][0]
    assert site["empty"] is True
    assert repository.get(player.player_id).stamina == before_stamina


def test_cannot_cancel_a_task_that_is_already_ready(game):
    service, repository, clock, player = game
    reach_level(repository, player.player_id, 60)
    service.snapshot_by_sub("cancel-sub")
    repository.update(player.player_id, lambda state: state.inventory.update({"maple_wood": {0: 2}}))
    started = service.start_crafting("cancel-sub", "town_workbench", "saw_maple_plank")

    clock.advance(started["result"]["final_duration"])
    with pytest.raises(GameError, match="已经完成"):
        service.cancel_task("cancel-sub", "crafting", "town_workbench")


def test_cannot_cancel_when_there_is_no_active_task(game):
    service, _, _, _ = game
    with pytest.raises(GameError, match="没有可以取消"):
        service.cancel_task("cancel-sub", "gathering", "maple_forest")
