from __future__ import annotations

import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain.monthly_card import extend_expiry, remaining_days
from red_leaf_town.domain.redemption import normalize_code
from red_leaf_town.infrastructure import InMemoryPlayerRepository, InMemoryRedemptionCodes


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
    codes = InMemoryRedemptionCodes()
    clock = Clock()
    service = GameService(
        content,
        repository,
        redemption_codes=codes,
        clock=clock,
        rng=random.Random(7),
    )
    player = service.ensure_player("oauth-sub-1", "枫糖")
    return service, repository, codes, clock, player


def issue(service, count=1):
    return service.generate_redemption_codes(count, batch="test")


# ------------------------------------------------------------------ 天数计算


def test_expiry_covers_the_activation_day_itself():
    expires = extend_expiry("", "2026-08-28", 30)
    assert expires == "2026-09-26"
    assert remaining_days(expires, "2026-08-28") == 30
    assert remaining_days(expires, "2026-09-26") == 1
    assert remaining_days(expires, "2026-09-27") == 0


def test_renewal_stacks_onto_the_existing_expiry():
    first = extend_expiry("", "2026-08-28", 30)
    assert remaining_days(extend_expiry(first, "2026-08-28", 30), "2026-08-28") == 60


def test_renewal_after_a_lapse_restarts_from_today():
    lapsed = extend_expiry("2026-01-01", "2026-08-28", 30)
    assert remaining_days(lapsed, "2026-08-28") == 30


# -------------------------------------------------------------------- 兑换码


def test_codes_are_normalized_so_players_can_paste_anything():
    assert normalize_code("abcd efgh-ijkl mnpq") == "ABCD-EFGH-IJKL-MNPQ"
    assert normalize_code("  ") == ""


def test_redeeming_grants_maple_flame_and_thirty_days(game):
    service, _, _, _, _ = game
    code = issue(service)[0]
    before = service.snapshot_by_sub("oauth-sub-1")["player"]["maple_flame"]

    result = service.redeem_code("oauth-sub-1", code.lower())

    assert result["result"]["maple_flame"] == 300
    card = result["state"]["monthly_card"]
    assert card["active"] is True
    assert card["days_left"] == 30
    assert card["claimable"] is True
    assert result["state"]["player"]["maple_flame"] == before + 300


def test_a_code_cannot_be_redeemed_twice(game):
    service, _, _, _, _ = game
    code = issue(service)[0]
    service.redeem_code("oauth-sub-1", code)

    with pytest.raises(GameError) as error:
        service.redeem_code("oauth-sub-1", code)
    assert error.value.code == "code_already_redeemed"


def test_another_player_cannot_reuse_a_spent_code(game):
    service, _, _, _, _ = game
    service.ensure_player("oauth-sub-2", "邻居")
    code = issue(service)[0]
    service.redeem_code("oauth-sub-1", code)

    with pytest.raises(GameError):
        service.redeem_code("oauth-sub-2", code)


def test_unknown_codes_are_rejected(game):
    service, _, _, _, _ = game
    with pytest.raises(GameError) as error:
        service.redeem_code("oauth-sub-1", "ZZZZ-ZZZZ-ZZZZ-ZZZZ")
    assert error.value.code == "invalid_code"


def test_renewal_past_the_cap_is_refused_and_keeps_the_code(game):
    """180 天上限：第七张续期码要报错，而且这张码不能被吞掉。"""
    service, _, codes, _, _ = game
    issued = issue(service, 7)
    for code in issued[:6]:
        service.redeem_code("oauth-sub-1", code)
    assert service.snapshot_by_sub("oauth-sub-1")["monthly_card"]["days_left"] == 180

    with pytest.raises(GameError) as error:
        service.redeem_code("oauth-sub-1", issued[6])
    assert error.value.code == "monthly_card_capped"
    assert codes.get(issued[6]).redeemed is False

    # 上限的钱也不能扣：失败的兑换不该发 300 枫火。
    assert service.snapshot_by_sub("oauth-sub-1")["player"]["maple_flame"] == 6 * 300


# ---------------------------------------------------------------- 每日领取


def test_daily_claim_gives_maple_flame_and_two_tonics(game):
    service, _, _, _, _ = game
    service.redeem_code("oauth-sub-1", issue(service)[0])
    before = service.snapshot_by_sub("oauth-sub-1")["player"]["maple_flame"]

    result = service.claim_monthly_card("oauth-sub-1")

    assert result["result"]["maple_flame"] == 50
    assert result["result"]["item_amount"] == 2
    assert result["state"]["player"]["maple_flame"] == before + 50
    assert result["state"]["stamina_supply"]["potion_owned"] == 2
    assert result["state"]["monthly_card"]["claimable"] is False


def test_daily_claim_is_once_per_day_and_does_not_backfill(game):
    service, _, _, clock, _ = game
    service.redeem_code("oauth-sub-1", issue(service)[0])
    service.claim_monthly_card("oauth-sub-1")

    with pytest.raises(GameError) as error:
        service.claim_monthly_card("oauth-sub-1")
    assert error.value.code == "monthly_card_claimed"

    clock.advance(3 * 24 * 3600)
    result = service.claim_monthly_card("oauth-sub-1")
    assert result["result"]["maple_flame"] == 50
    assert result["state"]["stamina_supply"]["potion_owned"] == 4


def test_claiming_without_a_card_is_refused(game):
    service, _, _, _, _ = game
    with pytest.raises(GameError) as error:
        service.claim_monthly_card("oauth-sub-1")
    assert error.value.code == "monthly_card_inactive"


def test_an_expired_card_stops_paying_out(game):
    service, _, _, clock, _ = game
    service.redeem_code("oauth-sub-1", issue(service)[0])
    clock.advance(30 * 24 * 3600)

    assert service.snapshot_by_sub("oauth-sub-1")["monthly_card"]["active"] is False
    with pytest.raises(GameError):
        service.claim_monthly_card("oauth-sub-1")


# ------------------------------------------------------------------ 体力补给


def test_tonic_restores_forty_stamina_and_may_overflow_the_cap(game):
    service, repository, _, _, player = game
    repository.update(player.player_id, lambda entry: setattr(entry, "stamina", entry.stamina))
    service.redeem_code("oauth-sub-1", issue(service)[0])
    service.claim_monthly_card("oauth-sub-1")
    cap = service.snapshot_by_sub("oauth-sub-1")["player"]["stamina_cap"]

    result = service.use_stamina_potion("oauth-sub-1")

    assert result["result"]["stamina_gained"] == 40
    assert result["state"]["player"]["stamina"] == cap + 40
    assert result["state"]["stamina_supply"]["potion_owned"] == 1


def test_overflowed_stamina_survives_a_later_settle(game):
    service, _, _, clock, _ = game
    service.redeem_code("oauth-sub-1", issue(service)[0])
    service.claim_monthly_card("oauth-sub-1")
    overflowed = service.use_stamina_potion("oauth-sub-1")["state"]["player"]["stamina"]

    clock.advance(6 * 3600)
    assert service.snapshot_by_sub("oauth-sub-1")["player"]["stamina"] == overflowed


def test_using_a_tonic_without_one_is_refused(game):
    service, _, _, _, _ = game
    with pytest.raises(GameError) as error:
        service.use_stamina_potion("oauth-sub-1")
    assert error.value.code == "resource_insufficient"


def test_buying_stamina_walks_the_price_ladder_then_stops(game):
    service, repository, _, _, player = game
    repository.update(player.player_id, lambda entry: setattr(entry, "maple_flame", 1000))
    cap = service.snapshot_by_sub("oauth-sub-1")["player"]["stamina_cap"]

    spent = []
    for _ in range(4):
        spent.append(service.buy_stamina("oauth-sub-1")["result"]["maple_flame_spent"])
    assert spent == [50, 100, 150, 200]

    state = service.snapshot_by_sub("oauth-sub-1")
    assert state["player"]["maple_flame"] == 1000 - 500
    assert state["player"]["stamina"] == cap + 160
    assert state["stamina_supply"]["purchase_next_price"] is None

    with pytest.raises(GameError) as error:
        service.buy_stamina("oauth-sub-1")
    assert error.value.code == "stamina_purchase_limit"


def test_stamina_purchases_reset_the_next_day(game):
    service, repository, _, clock, player = game
    repository.update(player.player_id, lambda entry: setattr(entry, "maple_flame", 2000))
    for _ in range(4):
        service.buy_stamina("oauth-sub-1")

    clock.advance(24 * 3600)
    assert service.snapshot_by_sub("oauth-sub-1")["stamina_supply"]["purchase_used_today"] == 0
    assert service.buy_stamina("oauth-sub-1")["result"]["maple_flame_spent"] == 50


def test_buying_stamina_without_maple_flame_is_refused(game):
    service, _, _, _, _ = game
    with pytest.raises(GameError) as error:
        service.buy_stamina("oauth-sub-1")
    assert error.value.code == "resource_insufficient"


# -------------------------------------------------------------- 管理侧造码


def test_generated_codes_are_unique_and_listed(game):
    service, _, _, _, _ = game
    issued = issue(service, 25)
    assert len(set(issued)) == 25

    listed = service.list_redemption_codes()
    assert {entry["code"] for entry in listed} == set(issued)
    assert all(entry["batch"] == "test" for entry in listed)


def test_listing_shows_who_spent_a_code(game):
    service, _, _, _, player = game
    code = issue(service)[0]
    service.redeem_code("oauth-sub-1", code)

    entry = next(record for record in service.list_redemption_codes() if record["code"] == code)
    assert entry["redeemed_by"] == player.player_id
    assert entry["redeemed_by_name"] == "枫糖"


def test_batch_size_is_bounded(game):
    service, _, _, _, _ = game
    with pytest.raises(GameError):
        service.generate_redemption_codes(0)
    with pytest.raises(GameError):
        service.generate_redemption_codes(501)
