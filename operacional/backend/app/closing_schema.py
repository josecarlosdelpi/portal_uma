"""Validated 7-slide closing narrative; fully independent from sales importer."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DURATIONS = [1, 3, 5, 3, 2, 2, 4]
assert len(DURATIONS) == 7 and sum(DURATIONS) == 20


class StoreNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    JOINVILLE: str = Field(default="", max_length=1600)
    TUBARAO: str = Field(default="", max_length=1600)
    ITAJAI: str = Field(default="", max_length=1600)


class Priority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    what: str = Field(min_length=1, max_length=300)
    owner: str = Field(min_length=1, max_length=150)
    scope: Literal["all", "JOINVILLE", "TUBARAO", "ITAJAI"] = "all"
    due: date
    status: Literal["pendente", "andamento", "concluida"] = "pendente"


class ClosingContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening: str = Field(default="", max_length=2000)
    stores: StoreNotes = Field(default_factory=StoreNotes)
    opportunities: str = Field(default="", max_length=3000)
    wins: str = Field(default="", max_length=3000)
    improvements: str = Field(default="", max_length=3000)
    notices: str = Field(default="", max_length=3000)
    notes: StoreNotes = Field(default_factory=StoreNotes)
    priorities: list[Priority] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def ensure_unique_priorities(self):
        ids = [priority.id for priority in self.priorities]
        if len(set(ids)) != len(ids):
            raise ValueError("Prioridades repetidas")
        return self
