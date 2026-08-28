from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import uuid4

from redis.exceptions import WatchError

from red_leaf_town.content import GameContent
from red_leaf_town.domain import (
    CommissionBoardEntry,
    CommissionPayout,
    MailMessage,
    PlayerState,
    PlotState,
    QQIdentity,
    RedemptionCode,
)

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
            maple_flame=self.content.game.starting_maple_flame,
            guide_leaves=self.content.game.starting_guide_leaves,
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

    def search(self, query: str, limit: int = 50) -> list[PlayerState]:
        normalized = str(query or "").strip().casefold()
        matches: list[PlayerState] = []
        for key in self.redis.scan_iter(match=f"{self.PREFIX}player:*", count=100):
            raw = self.redis.get(key)
            if not raw:
                continue
            try:
                player = PlayerState.model_validate_json(raw)
            except (TypeError, ValueError):
                continue
            if (
                normalized
                and normalized not in player.player_id.casefold()
                and normalized not in player.display_name.casefold()
            ):
                continue
            matches.append(player)
        matches.sort(key=lambda player: (-player.updated_at, player.player_id))
        return matches[:limit]

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
                    player = PlayerState.model_validate(player.model_dump())
                    pipe.multi()
                    pipe.set(key, player.model_dump_json())
                    pipe.execute()
                    return player, result
                except WatchError:
                    continue
        raise RuntimeError("player update conflict")

    def delete(self, player_id: str) -> bool:
        """删号：存档、OAuth 索引、绑定标签，以及指向这个角色的 QQ 绑定都要一起清掉。"""
        player = self.get(player_id)
        if not player:
            return False
        keys = [
            self._player_key(player_id),
            self._oauth_key(player.oauth_sub),
            f"{self._bindings_prefix()}{player_id}",
        ]
        # identity key 里只存了 player_id，反查只能扫一遍；删号是管理员操作，这点代价可以接受。
        keys.extend(
            key
            for key in self.redis.scan_iter(match=f"{self.PREFIX}identity:*", count=100)
            if str(self.redis.get(key) or "") == player_id
        )
        keys.extend(
            key
            for key in self.redis.scan_iter(match=f"{self.PREFIX}binding-code:*", count=100)
            if str(self.redis.get(key) or "") == player_id
        )
        self.redis.delete(*keys)
        return True

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


_TAKE_COMMISSION_LUA = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 0 then return 0 end
if redis.call('HSETNX', KEYS[2], ARGV[1], ARGV[2]) == 0 then return 0 end
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[4]))
redis.call('RPUSH', KEYS[3], ARGV[3])
redis.call('EXPIRE', KEYS[3], tonumber(ARGV[5]))
return 1
"""

_RELEASE_COMMISSION_LUA = """
if redis.call('HGET', KEYS[1], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('HDEL', KEYS[1], ARGV[1])
redis.call('LREM', KEYS[2], 1, ARGV[3])
return 1
"""

_WITHDRAW_COMMISSION_LUA = """
if redis.call('HEXISTS', KEYS[2], ARGV[1]) == 1 then return 0 end
if redis.call('HDEL', KEYS[1], ARGV[1]) == 0 then return 0 end
return 1
"""

_DRAIN_PAYOUTS_LUA = """
local queued = redis.call('LRANGE', KEYS[1], 0, -1)
redis.call('DEL', KEYS[1])
return queued
"""


class RedisCommissionBoard:
    """公共转发池。发布的内容不可变，接单靠一张单独的 taken 表用 HSETNX 抢占。"""

    PREFIX = "rlt:commission:"
    BOARD_TTL = 3 * 24 * 3600
    PAYOUT_TTL = 30 * 24 * 3600

    def __init__(self, redis_client: Any):
        self.redis = redis_client
        self._take_script = redis_client.register_script(_TAKE_COMMISSION_LUA)
        self._release_script = redis_client.register_script(_RELEASE_COMMISSION_LUA)
        self._withdraw_script = redis_client.register_script(_WITHDRAW_COMMISSION_LUA)
        self._drain_script = redis_client.register_script(_DRAIN_PAYOUTS_LUA)

    def publish(self, entry: CommissionBoardEntry) -> None:
        board_key = self._board_key(entry.day)
        self.redis.hset(board_key, entry.commission_id, entry.model_dump_json())
        self.redis.expire(board_key, self.BOARD_TTL)

    def get(self, day: str, commission_id: str) -> CommissionBoardEntry | None:
        raw = self.redis.hget(self._board_key(day), commission_id)
        return CommissionBoardEntry.model_validate_json(raw) if raw else None

    def list_open(self, day: str, exclude_player_id: str = "", limit: int = 30) -> list[CommissionBoardEntry]:
        raw_entries = self.redis.hgetall(self._board_key(day)) or {}
        taken = set(self.redis.hkeys(self._taken_key(day)) or [])
        entries = []
        for commission_id, raw in raw_entries.items():
            if commission_id in taken:
                continue
            try:
                entry = CommissionBoardEntry.model_validate_json(raw)
            except (TypeError, ValueError):
                continue
            if entry.owner_id == exclude_player_id:
                continue
            entries.append(entry)
        entries.sort(key=lambda entry: (entry.forwarded_at, entry.commission_id))
        return entries[:limit]

    def withdraw(self, day: str, commission_id: str, owner_id: str) -> CommissionBoardEntry | None:
        entry = self.get(day, commission_id)
        if not entry or entry.owner_id != owner_id:
            return None
        removed = self._withdraw_script(
            keys=[self._board_key(day), self._taken_key(day)],
            args=[commission_id],
        )
        return entry if int(removed or 0) else None

    def take(self, day: str, commission_id: str, taker_id: str, payout: CommissionPayout) -> CommissionBoardEntry | None:
        entry = self.get(day, commission_id)
        if not entry or entry.owner_id == taker_id:
            return None
        claimed = self._take_script(
            keys=[self._board_key(day), self._taken_key(day), self._payout_key(entry.owner_id)],
            args=[commission_id, taker_id, payout.model_dump_json(), self.BOARD_TTL, self.PAYOUT_TTL],
        )
        return entry if int(claimed or 0) else None

    def release(self, day: str, commission_id: str, taker_id: str, payout: CommissionPayout) -> None:
        entry = self.get(day, commission_id)
        if not entry:
            return
        self._release_script(
            keys=[self._taken_key(day), self._payout_key(entry.owner_id)],
            args=[commission_id, taker_id, payout.model_dump_json()],
        )

    def drain_payouts(self, player_id: str) -> list[CommissionPayout]:
        payouts = []
        for raw in self._drain_script(keys=[self._payout_key(player_id)]) or []:
            try:
                payouts.append(CommissionPayout.model_validate_json(raw))
            except (TypeError, ValueError):
                continue
        return payouts

    def restore_payouts(self, player_id: str, payouts: list[CommissionPayout]) -> None:
        if not payouts:
            return
        key = self._payout_key(player_id)
        self.redis.lpush(key, *[payout.model_dump_json() for payout in reversed(payouts)])
        self.redis.expire(key, self.PAYOUT_TTL)

    def _board_key(self, day: str) -> str:
        return f"{self.PREFIX}board:{day}"

    def _taken_key(self, day: str) -> str:
        return f"{self.PREFIX}taken:{day}"

    def _payout_key(self, player_id: str) -> str:
        return f"{self.PREFIX}payout:{player_id}"


class RedisMailbox:
    """公共信箱。全服信共用一个哈希，个人信一人一个哈希，已读/已领的状态不在这里。"""

    PREFIX = "rlt:mail:"

    def __init__(self, redis_client: Any):
        self.redis = redis_client

    def publish(self, mail: MailMessage) -> None:
        self.redis.hset(self._key(mail.recipient_id), mail.mail_id, mail.model_dump_json())

    def get(self, mail_id: str, recipient_id: str = "") -> MailMessage | None:
        raw = self.redis.hget(self._key(recipient_id), mail_id)
        return self._parse(raw)

    def list_global(self) -> list[MailMessage]:
        return self._list("")

    def list_for_player(self, player_id: str) -> list[MailMessage]:
        return self._list(player_id)

    def delete(self, mail_id: str, recipient_id: str = "") -> bool:
        return bool(self.redis.hdel(self._key(recipient_id), mail_id))

    def _list(self, recipient_id: str) -> list[MailMessage]:
        letters = [self._parse(raw) for raw in (self.redis.hvals(self._key(recipient_id)) or [])]
        return sorted(
            (letter for letter in letters if letter),
            key=lambda letter: (-letter.created_at, letter.mail_id),
        )

    @staticmethod
    def _parse(raw) -> MailMessage | None:
        if not raw:
            return None
        try:
            return MailMessage.model_validate_json(raw)
        except (TypeError, ValueError):
            return None

    def _key(self, recipient_id: str) -> str:
        return f"{self.PREFIX}player:{recipient_id}" if recipient_id else f"{self.PREFIX}global"


_CLAIM_CODE_LUA = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 0 then return 0 end
if redis.call('HSETNX', KEYS[2], ARGV[1], ARGV[2]) == 0 then return 0 end
return 1
"""

_RELEASE_CODE_LUA = """
if redis.call('HGET', KEYS[1], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('HDEL', KEYS[1], ARGV[1])
return 1
"""


class RedisRedemptionCodes:
    """激活码池。码本身存一个哈希，兑换人存另一个哈希，靠 HSETNX 保证一码一人。

    兑换是「先占码、再改存档」：存档那步失败（比如剩余天数已经顶到上限）就把占用释放掉，
    码留给玩家以后再用。反过来先改存档的话，占码失败就得回滚存档，那才是真正难写对的。
    """

    PREFIX = "rlt:code:"

    def __init__(self, redis_client: Any):
        self.redis = redis_client
        self._claim_script = redis_client.register_script(_CLAIM_CODE_LUA)
        self._release_script = redis_client.register_script(_RELEASE_CODE_LUA)

    def create(self, codes: list[RedemptionCode]) -> int:
        created = 0
        for entry in codes:
            if self.redis.hsetnx(self._pool_key(), entry.code, entry.model_dump_json()):
                created += 1
        return created

    def get(self, code: str) -> RedemptionCode | None:
        entry = self._parse(self.redis.hget(self._pool_key(), code))
        if entry is None:
            return None
        return self._with_claim(entry)

    def claim(self, code: str, player_id: str, now: int) -> RedemptionCode | None:
        claimed = self._claim_script(
            keys=[self._pool_key(), self._claim_key()],
            args=[code, f"{player_id}|{now}"],
        )
        if not claimed:
            return None
        entry = self._parse(self.redis.hget(self._pool_key(), code))
        if entry is None:
            self.release(code, player_id)
            return None
        entry.redeemed_by = player_id
        entry.redeemed_at = now
        return entry

    def release(self, code: str, player_id: str) -> None:
        raw = self.redis.hget(self._claim_key(), code)
        marker = raw.decode() if isinstance(raw, bytes) else raw
        if not marker or marker.split("|", 1)[0] != player_id:
            return
        self._release_script(keys=[self._claim_key()], args=[code, marker])

    def list_recent(self, limit: int = 200) -> list[RedemptionCode]:
        entries = [self._parse(raw) for raw in (self.redis.hvals(self._pool_key()) or [])]
        claims = self.redis.hgetall(self._claim_key()) or {}
        claims = {
            (key.decode() if isinstance(key, bytes) else key): (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in claims.items()
        }
        resolved = []
        for entry in entries:
            if entry is None:
                continue
            resolved.append(self._apply_claim(entry, claims.get(entry.code)))
        resolved.sort(key=lambda entry: (-entry.created_at, entry.code))
        return resolved[:limit]

    def _with_claim(self, entry: RedemptionCode) -> RedemptionCode:
        raw = self.redis.hget(self._claim_key(), entry.code)
        marker = raw.decode() if isinstance(raw, bytes) else raw
        return self._apply_claim(entry, marker)

    @staticmethod
    def _apply_claim(entry: RedemptionCode, marker: str | None) -> RedemptionCode:
        if not marker:
            return entry
        player_id, _, redeemed_at = marker.partition("|")
        entry.redeemed_by = player_id
        entry.redeemed_at = int(redeemed_at or 0)
        return entry

    @staticmethod
    def _parse(raw) -> RedemptionCode | None:
        if not raw:
            return None
        try:
            return RedemptionCode.model_validate_json(raw)
        except (TypeError, ValueError):
            return None

    def _pool_key(self) -> str:
        return f"{self.PREFIX}pool"

    def _claim_key(self) -> str:
        return f"{self.PREFIX}claim"
