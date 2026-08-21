from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import uuid4

from redis.exceptions import WatchError

from red_leaf_town.content import GameContent
from red_leaf_town.domain import PlayerState, PlotState, QQIdentity

T = TypeVar("T")


_ENSURE_PLAYER_LUA = """
local current = redis.call('GET', KEYS[1])
if current then return current end
if redis.call('EXISTS', KEYS[2]) == 1 then return '' end
redis.call('SET', KEYS[2], ARGV[1])
redis.call('SET', KEYS[1], ARGV[2])
return ARGV[2]
"""

_BIND_IDENTITY_LUA = """
local player_id = redis.call('GET', KEYS[1])
if not player_id then return '' end
redis.call('DEL', KEYS[1])
local old_player_id = redis.call('GET', KEYS[2])
if old_player_id then
  redis.call('SREM', ARGV[1] .. old_player_id, ARGV[2])
end
redis.call('SET', KEYS[2], player_id)
redis.call('SADD', ARGV[1] .. player_id, ARGV[2])
return player_id
"""


class RedisPlayerRepository:
    PREFIX = "rlt:"
    MAX_RETRIES = 5

    def __init__(self, redis_client: Any, content: GameContent):
        self.redis = redis_client
        self.content = content
        self._ensure_script = redis_client.register_script(_ENSURE_PLAYER_LUA)
        self._bind_script = redis_client.register_script(_BIND_IDENTITY_LUA)

    def ensure_player(self, oauth_sub: str, display_name: str, now: int) -> PlayerState:
        oauth_sub = str(oauth_sub or "").strip()
        if not oauth_sub:
            raise ValueError("oauth_sub is required")
        existing = self.get_by_sub(oauth_sub)
        if existing:
            if display_name and existing.display_name != display_name:
                existing, _ = self.update(
                    existing.player_id,
                    lambda player: setattr(player, "display_name", display_name),
                )
            return existing

        level = self.content.levels[0]
        player = PlayerState(
            player_id=str(uuid4()),
            oauth_sub=oauth_sub,
            display_name=display_name,
            coins=self.content.game.starting_coins,
            stamina=level.stamina_cap,
            stamina_updated_at=now,
            inventory=dict(self.content.game.initial_inventory),
            plots=[PlotState(slot=slot) for slot in range(level.plot_slots)],
            created_at=now,
            updated_at=now,
        )
        player_id = self._ensure_script(
            keys=[self._oauth_key(oauth_sub), self._player_key(player.player_id)],
            args=[player.model_dump_json(), player.player_id],
        )
        if not player_id:
            existing = self.get_by_sub(oauth_sub)
            if existing:
                return existing
            raise RuntimeError("failed to create player")
        loaded = self.get(str(player_id))
        if not loaded:
            raise RuntimeError("created player is missing")
        return loaded

    def get_by_sub(self, oauth_sub: str) -> PlayerState | None:
        player_id = self.redis.get(self._oauth_key(oauth_sub))
        return self.get(str(player_id)) if player_id else None

    def get(self, player_id: str) -> PlayerState | None:
        raw = self.redis.get(self._player_key(player_id))
        return PlayerState.model_validate_json(raw) if raw else None

    def update(self, player_id: str, mutation: Callable[[PlayerState], T]) -> tuple[PlayerState, T]:
        key = self._player_key(player_id)
        for _ in range(self.MAX_RETRIES):
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    if not raw:
                        raise KeyError(player_id)
                    player = PlayerState.model_validate_json(raw)
                    result = mutation(player)
                    player.version += 1
                    player.updated_at = max(player.updated_at + 1, player.stamina_updated_at)
                    pipe.multi()
                    pipe.set(key, player.model_dump_json())
                    pipe.execute()
                    return player, result
                except WatchError:
                    continue
        raise RuntimeError("player update conflict")

    def create_binding_code(self, player_id: str, ttl_seconds: int = 600) -> str:
        if not self.redis.exists(self._player_key(player_id)):
            raise KeyError(player_id)
        for _ in range(8):
            code = secrets.token_hex(4).upper()
            if self.redis.set(self._binding_code_key(code), player_id, ex=ttl_seconds, nx=True):
                return code
        raise RuntimeError("failed to allocate binding code")

    def consume_binding_code(self, code: str, identity: QQIdentity) -> str | None:
        descriptor = json.dumps(
            {"platform": identity.platform, "bot_id": identity.bot_id, "label": identity.public_label},
            ensure_ascii=False,
            sort_keys=True,
        )
        result = self._bind_script(
            keys=[self._binding_code_key(code), self._identity_key(identity)],
            args=[self._bindings_prefix(), descriptor],
        )
        return str(result) if result else None

    def player_id_for_identity(self, identity: QQIdentity) -> str | None:
        player_id = self.redis.get(self._identity_key(identity))
        return str(player_id) if player_id else None

    def binding_labels(self, player_id: str) -> list[str]:
        labels = set()
        for raw in self.redis.smembers(f"{self._bindings_prefix()}{player_id}"):
            try:
                labels.add(str(json.loads(raw).get("label") or "QQ Bot"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(labels)

    def _player_key(self, player_id: str) -> str:
        return f"{self.PREFIX}player:{player_id}"

    def _oauth_key(self, oauth_sub: str) -> str:
        digest = hashlib.sha256(str(oauth_sub).encode()).hexdigest()
        return f"{self.PREFIX}oauth:{digest}"

    def _binding_code_key(self, code: str) -> str:
        return f"{self.PREFIX}binding-code:{code}"

    def _identity_key(self, identity: QQIdentity) -> str:
        raw = f"{identity.platform}:{identity.bot_id}:{identity.subject}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}identity:{digest}"

    def _bindings_prefix(self) -> str:
        return f"{self.PREFIX}bindings:"
