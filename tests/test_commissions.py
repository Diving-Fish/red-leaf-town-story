from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.domain.commissions import commission_day, is_lucky_day, lucky_weekday
from red_leaf_town.domain.economy import add_item
from red_leaf_town.infrastructure import InMemoryCommissionBoard, InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog


def timestamp_for(day: str, hour: int, content) -> int:
    zone = ZoneInfo(content.commissions.timezone)
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=zone, hour=hour).timestamp())


class Clock:
    def __init__(self, now: int):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def world():
    content = load_content().model_copy(deep=True)
    repository = InMemoryPlayerRepository(content)
    board = InMemoryCommissionBoard()
    clock = Clock(timestamp_for("2026-08-24", 12, content))
    service = GameService(
        content,
        repository,
        commission_board=board,
        clock=clock,
        partner_catalog_loader=lambda: PartnerCatalog(partners=[]),
    )
    return service, board, clock


def set_level(service: GameService, player_id: str, level: int) -> None:
    total_xp = next(entry.total_xp for entry in service.content.levels if entry.level == level)
    service.repository.update(player_id, lambda state: setattr(state, "experience", total_xp))


def stock(service: GameService, player_id: str, item_id: str, quantity: int, quality: int = 0) -> None:
    service.repository.update(player_id, lambda state: add_item(state, item_id, quantity, quality))


def commissions_of(service: GameService, sub: str) -> dict:
    return service.snapshot_by_sub(sub)["commissions"]


def fulfil(service: GameService, player_id: str, commission: dict) -> None:
    stock(service, player_id, commission["item_id"], commission["quantity"])


# --------------------------------------------------------------------- 刷新规则

def test_commission_is_rolled_once_and_frozen_for_the_day(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")

    first = commissions_of(service, "owner")["commission"]
    assert first is not None
    assert first["day"] == "2026-08-24"
    assert first["status"] == "open"
    assert first["quantity"] >= 1
    assert "{item}" not in first["line"] and first["item"]["name"] in first["line"]

    # 中途升级不能把已经掷出来的委托换掉。
    set_level(service, player.player_id, 8)
    assert commissions_of(service, "owner")["commission"] == first


def test_commission_only_asks_for_items_the_player_can_already_produce(world):
    service, _, _ = world
    service.ensure_player("owner", "枫一")
    reachable = {"carrot", "maple_wood", "woodland_mushroom", "maple_resin", "amber_beeswax"}

    for offset in range(30):
        day = (datetime(2026, 8, 24) + timedelta(days=offset)).strftime("%Y-%m-%d")
        service.clock.now = timestamp_for(day, 12, service.content)
        assert commissions_of(service, "owner")["commission"]["item_id"] in reachable


def test_day_rolls_over_at_the_configured_reset_hour(world):
    service, _, clock = world
    service.ensure_player("owner", "枫一")
    reset_hour = service.content.commissions.reset_hour

    clock.now = timestamp_for("2026-08-25", reset_hour - 1, service.content)
    assert commissions_of(service, "owner")["commission"]["day"] == "2026-08-24"

    clock.now = timestamp_for("2026-08-25", reset_hour, service.content)
    assert commissions_of(service, "owner")["commission"]["day"] == "2026-08-25"


def test_lucky_day_follows_the_account_and_pays_the_lucky_reward(world):
    service, _, clock = world
    player = service.ensure_player("owner", "枫一")
    weekday = lucky_weekday(player.player_id)
    assert lucky_weekday(player.player_id) == weekday

    day = next(
        (datetime(2026, 8, 24) + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(7)
        if (datetime(2026, 8, 24) + timedelta(days=offset)).weekday() == weekday
    )
    clock.now = timestamp_for(day, 12, service.content)
    snapshot = commissions_of(service, "owner")

    assert snapshot["lucky_today"] is True
    assert is_lucky_day(player.player_id, day) is True
    assert snapshot["commission"]["lucky"] is True
    assert snapshot["commission"]["reward_maple_flame"] == service.content.commissions.lucky_reward_maple_flame


def test_lucky_day_asks_for_something_at_least_as_hard(world):
    """幸运日的权重表整体压向高难度档，同一个玩家一周里最难的那天应该就是幸运日。"""
    service, _, clock = world
    player = service.ensure_player("owner", "枫一")
    set_level(service, player.player_id, 8)
    tiers = {}
    for offset in range(28):
        moment = datetime(2026, 8, 24) + timedelta(days=offset)
        day = moment.strftime("%Y-%m-%d")
        clock.now = timestamp_for(day, 12, service.content)
        snapshot = commissions_of(service, "owner")["commission"]
        tiers.setdefault(snapshot["lucky"], []).append(snapshot["tier"])

    assert min(tiers[True]) >= 2
    assert sum(tiers[True]) / len(tiers[True]) > sum(tiers[False]) / len(tiers[False])


# ------------------------------------------------------------------------ 提交

def test_submitting_consumes_items_and_pays_the_full_reward(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    fulfil(service, player.player_id, commission)
    before = service.repository.get(player.player_id).maple_flame

    result = service.submit_commission("owner")["result"]

    assert result["maple_flame"] == commission["reward_maple_flame"]
    assert [entry["achievement_id"] for entry in result["achievements"]] == ["first_commission"]
    state = service.repository.get(player.player_id)
    assert state.maple_flame == before + commission["reward_maple_flame"]
    assert state.achievements[0].claimed_at == 0
    assert sum(state.inventory.get(commission["item_id"], {}).values()) == 0
    assert state.commission.status == "completed"


def test_submitting_without_the_goods_is_refused(world):
    service, _, _ = world
    service.ensure_player("owner", "枫一")

    with pytest.raises(GameError) as caught:
        service.submit_commission("owner")
    assert caught.value.code == "resource_insufficient"


def test_a_commission_cannot_be_submitted_twice(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    fulfil(service, player.player_id, commission)
    service.submit_commission("owner")
    fulfil(service, player.player_id, commission)

    with pytest.raises(GameError) as caught:
        service.submit_commission("owner")
    assert caught.value.code == "commission_not_open"


def test_lowest_quality_is_consumed_first(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    stock(service, player.player_id, commission["item_id"], commission["quantity"], quality=1)
    stock(service, player.player_id, commission["item_id"], commission["quantity"], quality=4)

    service.submit_commission("owner")

    remaining = service.repository.get(player.player_id).inventory[commission["item_id"]]
    assert remaining.get(1, 0) == 0
    assert remaining[4] == commission["quantity"]


# ------------------------------------------------------------------ 转发与接单

def test_forwarding_puts_the_commission_in_the_public_pool(world):
    service, board, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]

    result = service.forward_commission("owner")["result"]

    assert result["owner_reward"] == service.content.commissions.owner_share(commission["reward_maple_flame"])
    assert result["taker_reward"] == service.content.commissions.taker_share(commission["reward_maple_flame"])
    assert [entry.commission_id for entry in board.list_open("2026-08-24")] == [commission["commission_id"]]
    assert commissions_of(service, "owner")["commission"]["status"] == "forwarded"


def test_a_forwarded_commission_cannot_be_submitted_by_its_owner(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    fulfil(service, player.player_id, commission)
    service.forward_commission("owner")

    with pytest.raises(GameError) as caught:
        service.submit_commission("owner")
    assert caught.value.code == "commission_not_open"


def test_withdrawing_restores_the_full_reward(world):
    service, board, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    fulfil(service, player.player_id, commission)
    service.forward_commission("owner")

    service.withdraw_commission("owner")

    assert board.list_open("2026-08-24") == []
    assert commissions_of(service, "owner")["commission"]["status"] == "open"
    assert service.submit_commission("owner")["result"]["maple_flame"] == commission["reward_maple_flame"]


def test_taking_pays_both_sides_and_the_owner_is_credited_on_the_next_read(world):
    service, _, _ = world
    owner = service.ensure_player("owner", "枫一")
    helper = service.ensure_player("helper", "枫二")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")
    fulfil(service, helper.player_id, commission)
    owner_flame = service.repository.get(owner.player_id).maple_flame
    shares = service.content.commissions

    result = service.take_commission("helper", commission["commission_id"])["result"]

    assert result["maple_flame"] == shares.taker_share(commission["reward_maple_flame"])
    assert service.repository.get(helper.player_id).maple_flame == shares.taker_share(commission["reward_maple_flame"])
    assert sum(service.repository.get(helper.player_id).inventory.get(commission["item_id"], {}).values()) == 0

    # 委托人还没读档，枫火先挂在信箱里。
    assert service.repository.get(owner.player_id).maple_flame == owner_flame
    settled = commissions_of(service, "owner")
    assert settled["commission"]["status"] == "forward_completed"
    assert settled["commission"]["completed_by_name"] == "枫二"
    assert service.repository.get(owner.player_id).maple_flame == owner_flame + shares.owner_share(
        commission["reward_maple_flame"]
    )


def test_the_two_shares_add_up_to_the_configured_split(world):
    service, _, _ = world
    shares = service.content.commissions
    assert shares.owner_share(100) == 80
    assert shares.taker_share(100) == 40
    assert shares.owner_share(200) == 160
    assert shares.taker_share(200) == 80


def test_only_one_commission_can_be_taken_per_day(world):
    service, _, clock = world
    helper = service.ensure_player("helper", "枫二")
    owners = []
    for index in range(2):
        sub = f"owner-{index}"
        owner = service.ensure_player(sub, f"委托人{index}")
        commission = commissions_of(service, sub)["commission"]
        service.forward_commission(sub)
        fulfil(service, helper.player_id, commission)
        owners.append(commission)

    service.take_commission("helper", owners[0]["commission_id"])
    with pytest.raises(GameError) as caught:
        service.take_commission("helper", owners[1]["commission_id"])
    assert caught.value.code == "commission_take_limit"

    # 换日之后额度重置。
    clock.now = timestamp_for("2026-08-25", 12, service.content)
    service.snapshot_by_sub("helper")
    fulfil(service, helper.player_id, owners[1])
    board_entry = service.commission_board.entries.get(("2026-08-24", owners[1]["commission_id"]))
    assert board_entry is not None
    assert service.commission_board_snapshot("helper")["remaining_takes"] == 1


def test_a_commission_can_only_be_taken_once(world):
    service, _, _ = world
    service.ensure_player("owner", "枫一")
    first = service.ensure_player("helper-a", "枫二")
    second = service.ensure_player("helper-b", "枫三")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")
    fulfil(service, first.player_id, commission)
    fulfil(service, second.player_id, commission)

    service.take_commission("helper-a", commission["commission_id"])
    with pytest.raises(GameError) as caught:
        service.take_commission("helper-b", commission["commission_id"])
    assert caught.value.code == "commission_already_taken"


def test_taking_your_own_commission_is_refused(world):
    service, _, _ = world
    player = service.ensure_player("owner", "枫一")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")
    fulfil(service, player.player_id, commission)

    with pytest.raises(GameError) as caught:
        service.take_commission("owner", commission["commission_id"])
    assert caught.value.code == "commission_own"


def test_a_failed_take_releases_the_pool_entry(world):
    service, board, _ = world
    service.ensure_player("owner", "枫一")
    service.ensure_player("helper", "枫二")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")

    with pytest.raises(GameError):
        service.take_commission("helper", commission["commission_id"])

    assert [entry.commission_id for entry in board.list_open("2026-08-24")] == [commission["commission_id"]]
    assert board.payouts == {}


def test_withdrawing_after_someone_took_it_is_refused(world):
    service, _, _ = world
    service.ensure_player("owner", "枫一")
    helper = service.ensure_player("helper", "枫二")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")
    fulfil(service, helper.player_id, commission)
    service.take_commission("helper", commission["commission_id"])

    with pytest.raises(GameError) as caught:
        service.withdraw_commission("owner")
    assert caught.value.code == "commission_already_taken"


def test_the_board_hides_your_own_commission(world):
    service, _, _ = world
    service.ensure_player("owner", "枫一")
    helper = service.ensure_player("helper", "枫二")
    commission = commissions_of(service, "owner")["commission"]
    service.forward_commission("owner")
    service.forward_commission("helper")

    listing = service.commission_board_snapshot("helper")

    assert [entry["commission_id"] for entry in listing["entries"]] == [commission["commission_id"]]
    assert listing["entries"][0]["can_take"] is False
    fulfil(service, helper.player_id, commission)
    assert service.commission_board_snapshot("helper")["entries"][0]["can_take"] is True
    assert "owner_id" not in listing["entries"][0]


# ------------------------------------------------------------------ 存档与内容

def test_old_saves_migrate_to_the_commission_schema():
    legacy = {
        "schema_version": 15,
        "player_id": "legacy",
        "oauth_sub": "legacy-sub",
        "display_name": "旧存档",
        "stamina_updated_at": 0,
        "created_at": 0,
        "updated_at": 0,
    }
    player = PlayerState.model_validate(legacy)

    assert player.schema_version == PlayerState.model_fields["schema_version"].default
    assert player.commission is None
    assert player.commission_takes == []


def test_every_producible_item_is_graded():
    content = load_content()
    graded = {entry.item_id for entry in content.commissions.entries}
    excluded = set(content.commissions.excluded_item_ids)
    producible = {item.id for item in content.items if item.kind in ("produce", "material", "product")}

    assert producible <= graded | excluded
    assert not graded & excluded
    assert all(content.item_map[item_id].kind != "seed" for item_id in graded)


def test_commission_day_respects_the_reset_hour():
    content = load_content()
    reset_hour = content.commissions.reset_hour
    zone = content.commissions.timezone
    just_before = timestamp_for("2026-08-25", reset_hour, content) - 1

    assert commission_day(just_before, reset_hour, zone) == "2026-08-24"
    assert commission_day(just_before + 1, reset_hour, zone) == "2026-08-25"
