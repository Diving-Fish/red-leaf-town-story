from __future__ import annotations

import json
from uuid import uuid4

import pytest

from red_leaf_town.application import GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import OwnedPartnerState, QQIdentity
from red_leaf_town.infrastructure import RedisPlayerRepository
from src.data_access.redis import redis_global


@pytest.fixture
def repository():
    prefix = f"test:rlt:{uuid4().hex}:"

    class IsolatedRedisRepository(RedisPlayerRepository):
        PREFIX = prefix

    instance = IsolatedRedisRepository(redis_global, load_content())
    yield instance
    for key in redis_global.scan_iter(match=f"{prefix}*"):
        redis_global.delete(key)


def test_oauth_player_actions_and_openid_binding_persist(repository):
    service = GameService(load_content(), repository, clock=lambda: 1_700_000_000)
    first = service.ensure_player("redis-oauth-sub", "小叶")
    second = service.ensure_player("redis-oauth-sub", "小叶子")
    assert second.player_id == first.player_id

    service.buy("redis-oauth-sub", "carrot_seed", 2)
    reloaded = repository.get(first.player_id)
    assert reloaded.inventory["carrot_seed"][0] == 2
    assert reloaded.coins == 64

    identity = QQIdentity(platform="QQ", bot_id="official-bot", subject="opaque-openid")
    code = service.create_binding_code("redis-oauth-sub")
    service.bind_identity(code, identity)
    assert repository.player_id_for_identity(identity) == first.player_id
    assert repository.binding_labels(first.player_id) == ["QQ Bot"]

    repository.update(
        first.player_id,
        lambda player: player.owned_partners.append(
            OwnedPartnerState(partner_id="partner_test", acquired_at=1_700_000_000),
        ),
    )
    repository.update(
        first.player_id,
        lambda player: setattr(player.plots[0], "assigned_partner_ids", ["partner_test"]),
    )
    reloaded = repository.get(first.player_id)
    assert [partner.partner_id for partner in reloaded.owned_partners] == ["partner_test"]
    assert reloaded.plots[0].assigned_partner_ids == ["partner_test"]


def test_schema_two_spirit_warehouse_is_rewritten_with_partner_fields(repository):
    player_id = "legacy-partner-player"
    repository.redis.set(repository._player_key(player_id), json.dumps({
        "schema_version": 2,
        "player_id": player_id,
        "oauth_sub": "legacy-partner-sub",
        "display_name": "旧居民",
        "stamina_updated_at": 1,
        "created_at": 1,
        "updated_at": 1,
        "owned_spirits": [{"spirit_id": "maple_sprite", "acquired_at": 2}],
    }))

    loaded = repository.get(player_id)
    assert loaded.schema_version == 5
    assert loaded.owned_partners[0].partner_id == "maple_sprite"

    repository.update(player_id, lambda player: None)
    stored = json.loads(repository.redis.get(repository._player_key(player_id)))
    assert stored["schema_version"] == 5
    assert stored["owned_partners"][0]["partner_id"] == "maple_sprite"
    assert "owned_spirits" not in stored
