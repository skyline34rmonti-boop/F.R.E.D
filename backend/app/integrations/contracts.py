"""Transport-independent smart-device contracts; no device driver is installed in V1."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.permissions.policy import ActionRequest, ConfirmationReceipt, Principal


class DeviceKind(str, Enum):
    LIGHT = 'light'
    PLUG = 'plug'
    SENSOR = 'sensor'
    THERMOSTAT = 'thermostat'
    COMPUTER = 'computer'


class RoomDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    name: str = Field(min_length=1, max_length=120)


class DeviceDefinition(BaseModel):
    """A declaration is not proof of connectivity or authority to act."""
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    name: str = Field(min_length=1, max_length=120)
    kind: DeviceKind
    room_id: str | None = Field(None, max_length=80)
    integration: str = Field('home_assistant', min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    external_id: str | None = Field(None, max_length=200)
    # Explicit supported names, never code or arbitrary shell commands.
    actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceStatus:
    device_id: str
    available: bool
    state: dict[str, Any]
    detail: str


class DeviceAdapter(Protocol):
    """A future adapter must verify connectivity and apply policy before any execution.

    No implementation is registered in V1. Keep transport credentials in server-only
    environment configuration, never in a DeviceDefinition or the AI prompt.
    """
    async def status(self, device: DeviceDefinition) -> DeviceStatus: ...
    async def perform(self, device: DeviceDefinition, request: ActionRequest, principal: Principal,
                      receipt: ConfirmationReceipt | None = None) -> DeviceStatus: ...
    async def close(self) -> None: ...


class ComputerAgent(Protocol):
    """Future authenticated peer; named actions only, never model-provided shell text."""
    async def status(self) -> DeviceStatus: ...
    async def request_action(self, action_id: str, parameters: dict[str, Any], authorization: str) -> str: ...
