from __future__ import annotations

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import RewardDefinition, load_content
from red_leaf_town.crossover import (
    CrossoverCampaign,
    register_crossover_campaign,
    unregister_crossover_campaign,
)
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog


CAMPAIGN_ID = "test_campaign"


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
        clock=clock,
        partner_catalog_loader=lambda: PartnerCatalog(partners=[]),
    )
    yield service, clock
    unregister_crossover_campaign(CAMPAIGN_ID)


def listed(service: GameService, sub: str) -> dict:
    """按 id 挑出本用例注册的那个活动——注册表是全局的，宿主可能还登记了真实联动。"""
    campaigns = service.crossover_campaigns(sub)["campaigns"]
    return next(entry for entry in campaigns if entry["campaign_id"] == CAMPAIGN_ID)


def leaves(service: GameService, sub: str) -> int:
    return service.snapshot_by_sub(sub)["player"]["guide_leaves"]


def campaign(eligible_subs: set[str], **overrides) -> CrossoverCampaign:
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "title": "测试联动",
        "source": "测试游戏",
        "description": "隔壁游戏的玩家可以来领一份见面礼。",
        "requirement": "在隔壁游戏通关某段剧情",
        "reward": RewardDefinition(guide_leaves=10),
        "eligible": lambda sub: sub in eligible_subs,
        "home_url": "/somewhere/",
        "locked_hint": "还没通关那段剧情",
    }
    payload.update(overrides)
    return CrossoverCampaign(**payload)


def test_campaign_listing_reflects_eligibility(world):
    service, _ = world
    register_crossover_campaign(campaign({"ready"}))
    service.ensure_player("ready", "达成的居民")
    service.ensure_player("not-ready", "还没达成的居民")

    ready = listed(service, "ready")
    assert (ready["eligible"], ready["claimed"], ready["claimable"]) == (True, False, True)
    assert ready["reward"]["guide_leaves"] == 10

    blocked = listed(service, "not-ready")
    assert (blocked["eligible"], blocked["claimable"]) == (False, False)


def test_claim_grants_the_reward_once_per_account(world):
    service, clock = world
    register_crossover_campaign(campaign({"ready"}))
    service.ensure_player("ready", "达成的居民")
    before = leaves(service, "ready")

    result = service.claim_crossover("ready", CAMPAIGN_ID)
    assert result["result"]["granted"]["guide_leaves"] == 10
    assert result["state"]["player"]["guide_leaves"] == before + 10

    with pytest.raises(GameError) as exc:
        service.claim_crossover("ready", CAMPAIGN_ID)
    assert exc.value.code == "crossover_already_claimed"
    assert leaves(service, "ready") == before + 10

    entry = listed(service, "ready")
    assert (entry["claimed"], entry["claimable"], entry["claimed_at"]) == (True, False, clock.now)


def test_a_hidden_campaign_leaves_the_list_for_good_once_claimed(world):
    service, _ = world
    register_crossover_campaign(campaign({"ready"}, hide_after_claim=True))
    service.ensure_player("ready", "达成的居民")

    assert listed(service, "ready")["claimable"] is True
    service.claim_crossover("ready", CAMPAIGN_ID)

    ids = [entry["campaign_id"] for entry in service.crossover_campaigns("ready")["campaigns"]]
    assert CAMPAIGN_ID not in ids
    # 撤下的只是展示，领取记录还在——再点一次仍然是「已经领过了」。
    assert service.crossover_claim_record("ready", CAMPAIGN_ID)["claimed_at"] > 0
    with pytest.raises(GameError) as exc:
        service.claim_crossover("ready", CAMPAIGN_ID)
    assert exc.value.code == "crossover_already_claimed"


def test_claim_is_refused_before_the_requirement_is_met(world):
    service, _ = world
    register_crossover_campaign(campaign({"ready"}))
    service.ensure_player("not-ready", "还没达成的居民")
    before = leaves(service, "not-ready")

    with pytest.raises(GameError) as exc:
        service.claim_crossover("not-ready", CAMPAIGN_ID)
    assert exc.value.code == "crossover_locked"
    assert exc.value.message == "还没通关那段剧情"
    assert leaves(service, "not-ready") == before


def test_a_claimed_campaign_stays_claimed_even_if_the_other_game_stops_answering(world):
    """联动那一方之后判定失败（存档回滚、服务挂了）也不该让已领的记录变回可领。"""
    service, _ = world

    def explode(sub: str) -> bool:
        raise RuntimeError("联动方不可用")

    register_crossover_campaign(campaign({"ready"}))
    service.ensure_player("ready", "达成的居民")
    service.claim_crossover("ready", CAMPAIGN_ID)

    register_crossover_campaign(campaign(set(), eligible=explode))
    entry = listed(service, "ready")
    assert (entry["eligible"], entry["claimed"], entry["claimable"]) == (True, True, False)


def test_a_broken_eligibility_check_reads_as_not_eligible(world):
    service, _ = world

    def explode(sub: str) -> bool:
        raise RuntimeError("联动方不可用")

    register_crossover_campaign(campaign(set(), eligible=explode))
    service.ensure_player("curious", "好奇的居民")

    entry = listed(service, "curious")
    assert (entry["eligible"], entry["claimable"]) == (False, False)
    with pytest.raises(GameError) as exc:
        service.claim_crossover("curious", CAMPAIGN_ID)
    assert exc.value.code == "crossover_locked"


def test_claim_record_answers_for_players_who_never_visited(world):
    service, clock = world
    register_crossover_campaign(campaign({"ready"}))

    assert service.crossover_claim_record("stranger", CAMPAIGN_ID) == {
        "registered": False,
        "claimed_at": 0,
        "display_name": "",
    }

    service.ensure_player("ready", "达成的居民")
    assert service.crossover_claim_record("ready", CAMPAIGN_ID) == {
        "registered": True,
        "claimed_at": 0,
        "display_name": "达成的居民",
    }

    service.claim_crossover("ready", CAMPAIGN_ID)
    assert service.crossover_claim_record("ready", CAMPAIGN_ID)["claimed_at"] == clock.now


def test_unknown_campaign_is_a_404(world):
    service, _ = world
    service.ensure_player("ready", "达成的居民")
    with pytest.raises(GameError) as exc:
        service.claim_crossover("ready", "no-such-campaign")
    assert exc.value.code == "crossover_not_found"
