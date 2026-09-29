"""Summer milestone data; narrative rewards are claimed independently of playback."""
import json
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from red_leaf_town.content import RewardDefinition

SUMMER_ID = "summer_tide_festival"
POINT_UNITS = 1800

class SummerMilestone(BaseModel):
    points: int = Field(gt=0)
    reward: RewardDefinition

class SummerChapter(BaseModel):
    story_id: str
    title: str
    points: int = Field(ge=0)
    previous_story_id: str = ""

class SummerEvent(BaseModel):
    season_id: str
    claim_grace_days: int = Field(ge=0, le=30)
    milestones: list[SummerMilestone] = Field(min_length=1)
    chapters: list[SummerChapter]

    @model_validator(mode="after")
    def validate_order(self):
        points = [m.points for m in self.milestones]
        if points != sorted(set(points)):
            raise ValueError("summer thresholds must be unique and increasing")
        seen = set()
        for chapter in self.chapters:
            if chapter.story_id in seen or (chapter.previous_story_id and chapter.previous_story_id not in seen):
                raise ValueError("summer chapters must have unique ids and earlier prerequisites")
            seen.add(chapter.story_id)
        return self

@lru_cache(maxsize=1)
def load_summer_event():
    return SummerEvent.model_validate(json.loads((Path(__file__).resolve().parents[2] / "data/summer_event.json").read_text()))
