from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import QQIdentity
from red_leaf_town.infrastructure import InMemoryPlayerRepository


class Clock:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += seconds


@pytest.fixture
def game():
    content = load_content()
    repository = InMemoryPlayerRepository(content)
    clock = Clock()
    service = GameService(content, repository, clock=clock, rng=random.Random(7))
    player = service.ensure_player("oauth-sub-1", "枫糖")
    return service, repository, clock, player


def test_oauth_account_has_exactly_one_player(game):
    service, repository, _, first = game
    second = service.ensure_player("oauth-sub-1", "新昵称")
    assert second.player_id == first.player_id
    assert repository.get_by_sub("oauth-sub-1").display_name == "新昵称"
    assert len(repository.players) == 1


def test_buy_plant_wait_harvest_and_sell_is_a_closed_loop(game):
    service, repository, clock, _ = game
    bought = service.buy("oauth-sub-1", "carrot_seed", 1)
    assert bought["state"]["player"]["coins"] == 72
    assert bought["state"]["inventory"][0]["item_id"] == "carrot_seed"

    planted = service.plant("oauth-sub-1", 0, "carrot")
    assert planted["state"]["player"]["stamina"] == 19
    assert planted["state"]["plots"][0]["remaining_seconds"] == 30

    with pytest.raises(GameError, match="还没有成熟"):
        service.harvest("oauth-sub-1", 0)

    clock.advance(30)
    harvested = service.harvest("oauth-sub-1", 0)
    reward = harvested["result"]
    assert reward["item_id"] == "carrot"
    assert 2 <= reward["quantity"] <= 3
    assert harvested["state"]["plots"][0]["empty"] is True

    sold = service.sell("oauth-sub-1", "carrot", reward["quantity"])
    assert sold["state"]["player"]["coins"] > 72
    assert repository.get_by_sub("oauth-sub-1").inventory.get("carrot", 0) == 0


def test_locked_plot_and_crop_are_enforced(game):
    service, _, _, _ = game
    service.buy("oauth-sub-1", "carrot_seed", 1)
    with pytest.raises(GameError, match="土地尚未解锁"):
        service.plant("oauth-sub-1", 3, "carrot")
    with pytest.raises(GameError, match="达到 2 级"):
        service.buy("oauth-sub-1", "wheat_seed", 1)


def test_stamina_recovers_lazily(game):
    service, repository, clock, player = game

    def drain(state):
        state.stamina = 10
        state.stamina_updated_at = clock.now

    repository.update(player.player_id, drain)
    clock.advance(service.content.stamina.restore_seconds * 3 + 20)
    state = service.snapshot_by_sub("oauth-sub-1")
    assert state["player"]["stamina"] == 13


def test_binding_uses_adapter_bot_and_openid_not_qq_number(game):
    service, _, _, player = game
    code = service.create_binding_code("oauth-sub-1")
    official_identity = QQIdentity(platform="QQ", bot_id="102042640", subject="opaque-openid")
    bound = service.bind_identity(code, official_identity)
    assert bound.player_id == player.player_id
    assert service.snapshot_by_identity(official_identity)["player"]["player_id"] == player.player_id

    another_bot = QQIdentity(platform="QQ", bot_id="another-bot", subject="opaque-openid")
    with pytest.raises(GameError, match="尚未绑定"):
        service.snapshot_by_identity(another_bot)
