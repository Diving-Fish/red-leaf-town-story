from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from red_leaf_town.content import RewardDefinition

from .models import PlayerState


MailScope = Literal["global", "player"]


class MailMessage(BaseModel):
    """一封信。全服信按注册时间投递，个人信只投给一个人，正文和附件结构两者完全一样。"""

    mail_id: str = Field(min_length=8, max_length=64)
    scope: MailScope
    recipient_id: str = ""
    registered_before: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=60)
    sender: str = Field(min_length=1, max_length=30)
    body: str = Field(min_length=1, max_length=4000)
    attachments: RewardDefinition = Field(default_factory=RewardDefinition)
    created_at: int = Field(ge=0)
    expires_at: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_mail(self):
        if self.scope == "player":
            if not self.recipient_id:
                raise ValueError("personal mail must name a recipient")
            if self.registered_before:
                raise ValueError("personal mail cannot carry a registration cutoff")
        else:
            if self.recipient_id:
                raise ValueError("global mail cannot name a recipient")
            if not self.registered_before:
                raise ValueError("global mail must carry a registration cutoff")
        if self.expires_at and self.expires_at <= self.created_at:
            raise ValueError("mail expiry must be later than when it was written")
        return self

    def expired(self, now: int) -> bool:
        return bool(self.expires_at) and self.expires_at <= now

    def deliverable_to(self, player: PlayerState, now: int) -> bool:
        """全服信只发给截止时刻之前就在镇上的人，后来的新居民看不到旧公告。"""
        if self.expired(now):
            return False
        if self.scope == "player":
            return self.recipient_id == player.player_id
        return player.created_at <= self.registered_before
