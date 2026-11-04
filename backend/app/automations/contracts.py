"""Scheduling contracts only; V1 never runs unattended device/computer actions."""
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RoutineStep(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    device_id: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=80)


class RoutineDefinition(BaseModel):
    """Future routines must authorize every exact device/action at execution time."""
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    steps: tuple[RoutineStep, ...] = Field(min_length=1, max_length=100)


class Scheduler(Protocol):
    async def schedule_reminder(self, owner: str, text: str, run_at: datetime) -> str: ...
    async def cancel(self, owner: str, task_id: str) -> None: ...
    async def close(self) -> None: ...
