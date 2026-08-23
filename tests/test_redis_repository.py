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
    assert loaded.schema_version == 9
    assert loaded.owned_partners[0].partner_id == "maple_sprite"

    repository.update(player_id, lambda player: None)
    stored = json.loads(repository.redis.get(repository._player_key(player_id)))
    assert stored["schema_version"] == 9
    assert stored["owned_partners"][0]["partner_id"] == "maple_sprite"
    assert "owned_spirits" not in stored


def test_gathering_assignment_and_task_snapshot_persist(repository):
    service = GameService(load_content(), repository, clock=lambda: 1_700_000_000)
    player = service.ensure_player("redis-gathering-sub", "林间居民")
    service.admin_grant_partner(player.player_id, "sprite_001")
    service.snapshot_by_sub("redis-gathering-sub")
    service.assign_gathering_partner("redis-gathering-sub", "maple_forest", "sprite_001")
    service.start_gathering("redis-gathering-sub", "maple_forest", "collect_maple_wood")

    reloaded = repository.get(player.player_id)
    assert reloaded.schema_version == 9
    assert reloaded.gathering_sites[0].assigned_partner_ids == ["sprite_001"]
    assert reloaded.gathering_sites[0].task_snapshot.industry == "gathering"
    assert reloaded.gathering_sites[0].task_snapshot.quality_parameters.ability == 40


def test_crafting_inputs_and_task_snapshot_persist_atomically(repository):
    from red_leaf_town.domain.economy import add_item

    service = GameService(load_content(), repository, clock=lambda: 1_700_000_000)
    player = service.ensure_player("redis-crafting-sub", "工坊居民")
    repository.update(player.player_id, lambda state: setattr(state, "experience", 60))
    repository.update(player.player_id, lambda state: add_item(state, "maple_wood", 2, 2))
    service.start_crafting("redis-crafting-sub", "town_workbench", "saw_maple_plank")

    reloaded = repository.get(player.player_id)
    assert reloaded.schema_version == 9
    assert "maple_wood" not in reloaded.inventory
    task = reloaded.crafting_stations[0].task_snapshot
    assert task.industry == "crafting"
    assert [entry.model_dump() for entry in task.consumed_inputs] == [
        {"item_id": "maple_wood", "quality": 2, "quantity": 2},
    ]


def test_mining_site_and_task_snapshot_persist(repository):
    service = GameService(load_content(), repository, clock=lambda: 1_700_000_000)
    player = service.ensure_player("redis-mining-sub", "矿山居民")
    repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    service.start_mining("redis-mining-sub", "copper_foothill", "mine_red_copper")

    reloaded = repository.get(player.player_id)
    assert reloaded.schema_version == 9
    assert reloaded.mining_sites[0].site_id == "copper_foothill"
    assert reloaded.mining_sites[0].task_snapshot.industry == "mining"
