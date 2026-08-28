from __future__ import annotations

import copy
import secrets
from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

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


class InMemoryPlayerRepository:
    def __init__(self, content: GameContent):
        self.content = content
        self.players: dict[str, PlayerState] = {}
        self.oauth_index: dict[str, str] = {}
        self.identity_index: dict[str, str] = {}
        self.bindings: dict[str, set[str]] = {}
        self.binding_codes: dict[str, str] = {}

    def ensure_player(self, oauth_sub: str, display_name: str, now: int) -> PlayerState:
        existing = self.get_by_sub(oauth_sub)
        if existing:
            if existing.display_name != display_name:
                self.update(existing.player_id, lambda player: setattr(player, "display_name", display_name))
            return self.get(existing.player_id)
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
            inventory=copy.deepcopy(self.content.game.initial_inventory),
            plots=[PlotState(slot=slot) for slot in range(level.plot_slots)],
            created_at=now,
            updated_at=now,
        )
        self.players[player.player_id] = copy.deepcopy(player)
        self.oauth_index[oauth_sub] = player.player_id
        return copy.deepcopy(player)

    def get_by_sub(self, oauth_sub: str) -> PlayerState | None:
        player_id = self.oauth_index.get(oauth_sub)
        return self.get(player_id) if player_id else None

    def get(self, player_id: str) -> PlayerState | None:
        player = self.players.get(player_id)
        return copy.deepcopy(player) if player else None

    def search(self, query: str, limit: int = 50) -> list[PlayerState]:
        normalized = str(query or "").strip().casefold()
        matches = [
            player
            for player in self.players.values()
            if not normalized
            or normalized in player.player_id.casefold()
            or normalized in player.display_name.casefold()
        ]
        matches.sort(key=lambda player: (-player.updated_at, player.player_id))
        return [copy.deepcopy(player) for player in matches[:limit]]

    def update(self, player_id: str, mutation: Callable[[PlayerState], T]) -> tuple[PlayerState, T]:
        current = self.players.get(player_id)
        if not current:
            raise KeyError(player_id)
        candidate = copy.deepcopy(current)
        result = mutation(candidate)
        candidate.version += 1
        candidate.updated_at += 1
        candidate = PlayerState.model_validate(candidate.model_dump())
        self.players[player_id] = copy.deepcopy(candidate)
        return candidate, result

    def delete(self, player_id: str) -> bool:
        player = self.players.pop(player_id, None)
        if not player:
            return False
        self.oauth_index.pop(player.oauth_sub, None)
        self.bindings.pop(player_id, None)
        for key in [key for key, owner in self.identity_index.items() if owner == player_id]:
            del self.identity_index[key]
        for code in [code for code, owner in self.binding_codes.items() if owner == player_id]:
            del self.binding_codes[code]
        return True

    def create_binding_code(self, player_id: str, ttl_seconds: int = 600) -> str:
        if player_id not in self.players:
            raise KeyError(player_id)
        code = secrets.token_hex(4).upper()
        self.binding_codes[code] = player_id
        return code

    def consume_binding_code(self, code: str, identity: QQIdentity) -> str | None:
        player_id = self.binding_codes.pop(code, None)
        if not player_id:
            return None
        key = self._identity_key(identity)
        old_player_id = self.identity_index.get(key)
        if old_player_id:
            self.bindings.setdefault(old_player_id, set()).discard(identity.public_label)
        self.identity_index[key] = player_id
        self.bindings.setdefault(player_id, set()).add(identity.public_label)
        return player_id

    def player_id_for_identity(self, identity: QQIdentity) -> str | None:
        return self.identity_index.get(self._identity_key(identity))

    def binding_labels(self, player_id: str) -> list[str]:
        return sorted(self.bindings.get(player_id, set()))

    @staticmethod
    def _identity_key(identity: QQIdentity) -> str:
        return f"{identity.platform}:{identity.bot_id}:{identity.subject}"


class InMemoryCommissionBoard:
    def __init__(self):
        self.entries: dict[tuple[str, str], CommissionBoardEntry] = {}
        self.taken: dict[tuple[str, str], str] = {}
        self.payouts: dict[str, list[CommissionPayout]] = {}

    def publish(self, entry: CommissionBoardEntry) -> None:
        self.entries[(entry.day, entry.commission_id)] = entry.model_copy(deep=True)

    def get(self, day: str, commission_id: str) -> CommissionBoardEntry | None:
        entry = self.entries.get((day, commission_id))
        return entry.model_copy(deep=True) if entry else None

    def list_open(self, day: str, exclude_player_id: str = "", limit: int = 30) -> list[CommissionBoardEntry]:
        open_entries = [
            entry.model_copy(deep=True)
            for (entry_day, commission_id), entry in self.entries.items()
            if entry_day == day
            and (entry_day, commission_id) not in self.taken
            and entry.owner_id != exclude_player_id
        ]
        open_entries.sort(key=lambda entry: (entry.forwarded_at, entry.commission_id))
        return open_entries[:limit]

    def withdraw(self, day: str, commission_id: str, owner_id: str) -> CommissionBoardEntry | None:
        key = (day, commission_id)
        entry = self.entries.get(key)
        if not entry or entry.owner_id != owner_id or key in self.taken:
            return None
        return self.entries.pop(key)

    def take(self, day: str, commission_id: str, taker_id: str, payout: CommissionPayout) -> CommissionBoardEntry | None:
        key = (day, commission_id)
        entry = self.entries.get(key)
        if not entry or entry.owner_id == taker_id or key in self.taken:
            return None
        self.taken[key] = taker_id
        self.payouts.setdefault(entry.owner_id, []).append(payout.model_copy(deep=True))
        return entry.model_copy(deep=True)

    def release(self, day: str, commission_id: str, taker_id: str, payout: CommissionPayout) -> None:
        key = (day, commission_id)
        if self.taken.get(key) != taker_id:
            return
        del self.taken[key]
        entry = self.entries.get(key)
        if not entry:
            return
        queued = self.payouts.get(entry.owner_id)
        if queued is None:
            return
        self.payouts[entry.owner_id] = [item for item in queued if item.commission_id != payout.commission_id]

    def drain_payouts(self, player_id: str) -> list[CommissionPayout]:
        return self.payouts.pop(player_id, [])

    def restore_payouts(self, player_id: str, payouts: list[CommissionPayout]) -> None:
        self.payouts.setdefault(player_id, [])[:0] = [payout.model_copy(deep=True) for payout in payouts]


class InMemoryMailbox:
    def __init__(self):
        self.letters: dict[tuple[str, str], MailMessage] = {}

    def publish(self, mail: MailMessage) -> None:
        self.letters[(mail.recipient_id, mail.mail_id)] = mail.model_copy(deep=True)

    def get(self, mail_id: str, recipient_id: str = "") -> MailMessage | None:
        mail = self.letters.get((recipient_id, mail_id))
        return mail.model_copy(deep=True) if mail else None

    def list_global(self) -> list[MailMessage]:
        return self._list("")

    def list_for_player(self, player_id: str) -> list[MailMessage]:
        return self._list(player_id)

    def delete(self, mail_id: str, recipient_id: str = "") -> bool:
        return self.letters.pop((recipient_id, mail_id), None) is not None

    def _list(self, recipient_id: str) -> list[MailMessage]:
        return sorted(
            (mail.model_copy(deep=True) for (bucket, _), mail in self.letters.items() if bucket == recipient_id),
            key=lambda mail: (-mail.created_at, mail.mail_id),
        )


class InMemoryRedemptionCodes:
    def __init__(self):
        self.codes: dict[str, RedemptionCode] = {}

    def create(self, codes: list[RedemptionCode]) -> int:
        created = 0
        for entry in codes:
            if entry.code in self.codes:
                continue
            self.codes[entry.code] = entry.model_copy(deep=True)
            created += 1
        return created

    def get(self, code: str) -> RedemptionCode | None:
        entry = self.codes.get(code)
        return entry.model_copy(deep=True) if entry else None

    def claim(self, code: str, player_id: str, now: int) -> RedemptionCode | None:
        entry = self.codes.get(code)
        if entry is None or entry.redeemed:
            return None
        entry.redeemed_by = player_id
        entry.redeemed_at = now
        return entry.model_copy(deep=True)

    def release(self, code: str, player_id: str) -> None:
        entry = self.codes.get(code)
        if entry is None or entry.redeemed_by != player_id:
            return
        entry.redeemed_by = ""
        entry.redeemed_at = 0

    def list_recent(self, limit: int = 200) -> list[RedemptionCode]:
        entries = sorted(
            (entry.model_copy(deep=True) for entry in self.codes.values()),
            key=lambda entry: (-entry.created_at, entry.code),
        )
        return entries[:limit]
