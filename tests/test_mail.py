from __future__ import annotations

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryMailbox, InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog


class Clock:
    def __init__(self, now: int):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def world():
    content = load_content().model_copy(deep=True)
    clock = Clock(1_700_000_000)
    service = GameService(
        content,
        InMemoryPlayerRepository(content),
        mailbox=InMemoryMailbox(),
        clock=clock,
        partner_catalog_loader=lambda: PartnerCatalog(partners=[]),
    )
    return service, clock


def letter(**overrides) -> dict:
    payload = {
        "scope": "global",
        "title": "红叶镇邮局开张",
        "sender": "镇长",
        "body": "从今天起，山下的信件可以直接送到你手上了。",
        "attachments": {"coins": 500},
    }
    payload.update(overrides)
    return payload


def inbox(service: GameService, sub: str) -> dict:
    return service.mailbox(sub)


def summary(service: GameService, sub: str) -> dict:
    return service.snapshot_by_sub(sub)["mail"]


# ------------------------------------------------------------------ 投递范围

def test_global_mail_reaches_players_registered_before_the_cutoff(world):
    service, clock = world
    service.ensure_player("old-hand", "老居民")
    cutoff = clock.now
    clock.now += 60
    service.ensure_player("newcomer", "新居民")

    service.admin_send_mail(letter(registered_before=cutoff))

    assert [entry["title"] for entry in inbox(service, "old-hand")["entries"]] == ["红叶镇邮局开张"]
    assert inbox(service, "newcomer")["entries"] == []


def test_global_mail_defaults_its_cutoff_to_the_moment_it_is_sent(world):
    service, clock = world
    service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter())
    assert inbox(service, "resident")["total"] == 1

    clock.now += 60
    service.ensure_player("latecomer", "迟到的人")
    assert inbox(service, "latecomer")["total"] == 0


def test_personal_mail_only_reaches_its_recipient(world):
    service, _ = world
    target = service.ensure_player("target", "收件人")
    service.ensure_player("bystander", "路人")

    service.admin_send_mail(letter(scope="player", recipient_id=target.player_id, title="给你的信"))

    assert [entry["title"] for entry in inbox(service, "target")["entries"]] == ["给你的信"]
    assert inbox(service, "bystander")["entries"] == []


def test_personal_mail_requires_an_existing_recipient(world):
    service, _ = world
    with pytest.raises(GameError) as caught:
        service.admin_send_mail(letter(scope="player", recipient_id="nobody"))
    assert caught.value.code == "player_not_found"


def test_expired_mail_leaves_the_inbox(world):
    service, clock = world
    service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter(expires_at=clock.now + 100))
    assert inbox(service, "resident")["total"] == 1

    clock.now += 100
    assert inbox(service, "resident")["total"] == 0


def test_mail_rejects_attachments_that_reference_unknown_items(world):
    service, _ = world
    service.ensure_player("resident", "小枫")
    with pytest.raises(GameError) as caught:
        service.admin_send_mail(letter(attachments={"items": [{"item_id": "ghost_item", "quantity": 1}]}))
    assert caught.value.code == "invalid_mail"


# ------------------------------------------------------------------ 已读与领取

def test_reading_a_letter_clears_the_unread_badge(world):
    service, _ = world
    service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter())
    mail_id = inbox(service, "resident")["entries"][0]["mail_id"]

    assert summary(service, "resident")["unread"] == 1
    state = service.read_mail("resident", mail_id)["state"]
    assert state["mail"] == {"total": 1, "unread": 0, "unclaimed": 1}
    assert inbox(service, "resident")["entries"][0]["read"] is True


def test_claiming_grants_the_attachment_exactly_once(world):
    service, _ = world
    player = service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter(attachments={"coins": 500, "items": [{"item_id": "carrot_seed", "quantity": 3}]}))
    mail_id = inbox(service, "resident")["entries"][0]["mail_id"]

    result = service.claim_mail("resident", mail_id)
    assert result["result"]["granted"]["coins"] == 500
    assert result["state"]["player"]["coins"] == player.coins + 500
    assert result["state"]["mail"] == {"total": 1, "unread": 0, "unclaimed": 0}

    with pytest.raises(GameError) as caught:
        service.claim_mail("resident", mail_id)
    assert caught.value.code == "mail_already_claimed"
    assert service.snapshot_by_sub("resident")["player"]["coins"] == player.coins + 500


def test_claiming_a_letter_without_attachments_is_refused(world):
    service, _ = world
    service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter(attachments={}))
    mail_id = inbox(service, "resident")["entries"][0]["mail_id"]

    with pytest.raises(GameError) as caught:
        service.claim_mail("resident", mail_id)
    assert caught.value.code == "mail_without_attachment"
    assert inbox(service, "resident")["entries"][0]["claimable"] is False


def test_a_letter_addressed_to_someone_else_cannot_be_claimed(world):
    service, _ = world
    target = service.ensure_player("target", "收件人")
    service.ensure_player("thief", "路人")
    service.admin_send_mail(letter(scope="player", recipient_id=target.player_id))
    mail_id = inbox(service, "target")["entries"][0]["mail_id"]

    with pytest.raises(GameError) as caught:
        service.claim_mail("thief", mail_id)
    assert caught.value.code == "mail_not_found"


# ------------------------------------------------------------------ 后台与清理

def test_withdrawing_a_letter_removes_it_and_its_receipt(world):
    service, _ = world
    player = service.ensure_player("resident", "小枫")
    service.admin_send_mail(letter())
    mail_id = inbox(service, "resident")["entries"][0]["mail_id"]
    service.read_mail("resident", mail_id)
    assert service.repository.get(player.player_id).mail_receipts

    service.admin_delete_mail(mail_id)

    assert inbox(service, "resident")["entries"] == []
    assert service.repository.get(player.player_id).mail_receipts == []


def test_admin_listing_separates_global_and_personal_mail(world):
    service, _ = world
    target = service.ensure_player("target", "收件人")
    service.admin_send_mail(letter(title="全服公告"))
    service.admin_send_mail(letter(scope="player", recipient_id=target.player_id, title="私信"))

    assert [entry["title"] for entry in service.admin_list_mail()["entries"]] == ["全服公告"]
    personal = service.admin_list_mail("player", target.player_id)["entries"]
    assert [entry["title"] for entry in personal] == ["私信"]
    assert personal[0]["recipient_name"] == "收件人"


def test_deleting_a_player_takes_their_mailbox_with_them(world):
    service, _ = world
    target = service.ensure_player("target", "收件人")
    service.admin_send_mail(letter(scope="player", recipient_id=target.player_id))

    service.admin_delete_player(target.player_id)

    assert service.mailbox_repository.list_for_player(target.player_id) == []


def test_a_town_without_a_post_office_reports_an_empty_inbox(world):
    service, _ = world
    service.mailbox_repository = None
    service.ensure_player("resident", "小枫")

    assert summary(service, "resident") == {"total": 0, "unread": 0, "unclaimed": 0}
    # 收件箱本身照常打开，只是空的；真正需要信箱的写操作才报错。
    assert service.mailbox("resident") == {"available": False, "entries": [], "total": 0, "unread": 0, "unclaimed": 0}
    with pytest.raises(GameError) as caught:
        service.read_mail("resident", "deadbeefcafe")
    assert caught.value.status == 503
