from pydantic import BaseModel, Field, model_validator


class SailingDrop(BaseModel):
    item_id: str
    quantity: int = Field(gt=0)


class SailingLog(BaseModel):
    event_id: str
    name: str
    text: str
    success: bool
    roll: int = Field(ge=1, le=20)
    modifier: int
    attribute: str
    actor_id: str


class SailingRun(BaseModel):
    run_id: str
    rule_version: int = 1
    route_id: str
    route_name: str
    partner_ids: list[str] = Field(min_length=1, max_length=3)
    started_at: int
    ready_at: int
    trial: bool = False
    supply_id: str
    coins: int = Field(gt=0)
    stamina: int = Field(gt=0)
    experience: int = Field(gt=0)
    partner_experience: int = Field(gt=0)
    ability: int = Field(ge=0)
    cargo_level: int = Field(ge=0, le=3)
    nets_level: int = Field(ge=0, le=3)
    consumed_inputs: list[dict] = Field(default_factory=list)
    drops: list[SailingDrop] = Field(min_length=1)
    logs: list[SailingLog] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def validate_run(self):
        if len(set(self.partner_ids)) != len(self.partner_ids):
            raise ValueError('duplicate sailing partner')
        if self.ready_at <= self.started_at:
            raise ValueError('sailing must finish after departure')
        return self


class SailingState(BaseModel):
    ship_built: bool = False
    active_run: SailingRun | None = None
    last_run: SailingRun | None = None
    completed_voyages: int = Field(default=0, ge=0)
    cargo_level: int = Field(default=0, ge=0, le=3)
    nets_level: int = Field(default=0, ge=0, le=3)
    discoveries: list[str] = Field(default_factory=list)
    collected_items: dict[str, int] = Field(default_factory=dict)
    start_requests: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode='before')
    @classmethod
    def preserve_existing_ship(cls, value):
        if isinstance(value, dict) and 'ship_built' not in value:
            value = dict(value)
            value['ship_built'] = bool(value.get('active_run') or value.get('last_run')
                                       or value.get('completed_voyages') or value.get('cargo_level')
                                       or value.get('nets_level'))
        return value
