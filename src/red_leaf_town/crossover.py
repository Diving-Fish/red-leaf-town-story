"""联动活动登记表。

红叶镇本身不认识任何一款联动的游戏。宿主（或任何别的产品）在启动时把一个
:class:`CrossoverCampaign` 注册进来，说明「这个活动叫什么、达成条件怎么判、领什么」，
红叶镇只负责两件事：把它展示出来，以及**按 OAuth 账号**发一次奖。

达成条件由 ``eligible(oauth_sub) -> bool`` 回调判定：判定逻辑住在联动那一方，
它才知道自己的存档长什么样。回调抛异常一律当作「尚未达成」处理，联动方挂掉不能
把红叶镇的招募页一起带下水。

「只能领一次」记在 ``PlayerState.crossover_claims`` 上——红叶镇存档和 OAuth 账号
一一对应，所以这个标记天然是账号级的，联动那一方有几个角色都不影响。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from red_leaf_town.content import RewardDefinition


@dataclass(frozen=True)
class CrossoverCampaign:
    campaign_id: str
    title: str
    source: str
    description: str
    requirement: str
    reward: RewardDefinition
    eligible: Callable[[str], bool]
    home_url: str = ""
    locked_hint: str = ""
    # 领过之后就不再出现在列表里（一次性的联动礼物领完即撤，不留一张灰卡片占位）。
    hide_after_claim: bool = False
    extra: dict = field(default_factory=dict)

    def is_eligible(self, oauth_sub: str) -> bool:
        try:
            return bool(self.eligible(str(oauth_sub or "")))
        except Exception:
            return False


_CAMPAIGNS: dict[str, CrossoverCampaign] = {}


def register_crossover_campaign(campaign: CrossoverCampaign) -> None:
    """登记一个联动活动。同 id 重复注册会覆盖，便于开发期热重载。"""
    if not campaign.campaign_id:
        raise ValueError("crossover campaign must carry an id")
    _CAMPAIGNS[campaign.campaign_id] = campaign


def unregister_crossover_campaign(campaign_id: str) -> None:
    _CAMPAIGNS.pop(campaign_id, None)


def list_crossover_campaigns() -> list[CrossoverCampaign]:
    """按注册顺序返回全部联动活动。"""
    return list(_CAMPAIGNS.values())


def get_crossover_campaign(campaign_id: str) -> CrossoverCampaign | None:
    return _CAMPAIGNS.get(str(campaign_id or ""))
