"""Future action authorization contracts; no executor or confirmation endpoint exists.

The conversation provider is never given these objects. A future authenticated
transport must create principals and issue receipts *after* explicit human
confirmation. Authorization is distinct from implementation availability: V1
installs no device or computer adapter and cannot execute these actions.
"""
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from typing import Callable, Mapping


class Risk(str, Enum):
    GREEN = 'green'
    YELLOW = 'yellow'
    RED = 'red'


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    risk: Risk


@dataclass(frozen=True)
class Authorization:
    username: str
    allowed_tools: frozenset[str]


def authorize_tool(tool: ToolDefinition, authorization: Authorization, confirmed: bool = False) -> None:
    """Legacy capability check. No boolean can enable sensitive V1 actions."""
    if not authorization.username.strip():
        raise PermissionError('An authenticated identity is required.')
    if tool.risk is Risk.RED:
        raise PermissionError('RED actions are unavailable in this deployment.')
    if tool.name not in authorization.allowed_tools:
        raise PermissionError('This identity is not authorized for that tool.')
    if tool.risk is Risk.YELLOW:
        raise PermissionError('YELLOW actions require a separately authenticated, server-issued confirmation workflow; unavailable in V1.')


# Server-owned vocabulary and risk classification. Model-provided risk levels,
# command strings and executable paths are not accepted. Shutdown remains denied
# even with a valid receipt until a separate reviewed implementation exists.
_ACTION_RISKS = {
    'device.status': Risk.GREEN,
    'device.turn_on': Risk.YELLOW,
    'device.turn_off': Risk.YELLOW,
    'device.set_brightness': Risk.YELLOW,
    'device.set_temperature': Risk.YELLOW,
    'computer.status': Risk.GREEN,
    'computer.lock': Risk.YELLOW,
    'computer.shutdown': Risk.RED,
}


def _parameters_digest(parameters: Mapping[str, object]) -> str:
    def check(value: object) -> None:
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ValueError('Action parameter keys must be strings.')
            for nested in value.values():
                check(nested)
        elif isinstance(value, list):
            for nested in value:
                check(nested)
        elif value is not None and type(value) not in (str, bool, int, float):
            raise ValueError('Action parameters must contain only JSON data.')

    data = dict(parameters)
    check(data)
    try:
        encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError('Action parameters must contain valid JSON data.') from exc
    if len(encoded) > 16_000:
        raise ValueError('Action parameters exceed the supported size.')
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ActionRequest:
    action: str
    target: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}', self.target):
            raise ValueError('A configured target identifier is required.')
        _parameters_digest(self.parameters)


@dataclass(frozen=True)
class Principal:
    """Built by a trusted authentication boundary, never deserialized from AI text.

    Grants are exact (target identifier, action name) pairs. Empty grants and
    unauthenticated principals have no access, including to read-only status.
    """
    username: str
    authenticated: bool = False
    allowed_actions: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class ConfirmationReceipt:
    username: str
    action: str
    target: str
    parameters_digest: str
    expires_at: float
    nonce: str
    signature: str


def _receipt_payload(receipt: ConfirmationReceipt) -> bytes:
    return json.dumps([
        receipt.username, receipt.action, receipt.target, receipt.parameters_digest,
        receipt.expires_at, receipt.nonce,
    ], separators=(',', ':'), allow_nan=False).encode()


def _check_grant(principal: Principal, request: ActionRequest) -> Risk:
    if not principal.authenticated or not principal.username.strip():
        raise PermissionError('An authenticated principal is required.')
    risk = _ACTION_RISKS.get(request.action)
    if risk is None:
        raise PermissionError('This action is not in the server action vocabulary.')
    if risk is Risk.RED:
        raise PermissionError('This action is unavailable in V1.')
    if (request.target, request.action) not in principal.allowed_actions:
        raise PermissionError('This principal is not authorized for this target and action.')
    return risk


class ConfirmationAuthority:
    """Process-local receipt issuer for a future human-confirmation transport.

    Do not expose ``issue_after_confirmation`` to an AI tool, request body or
    integration. Only a separately authenticated UI, after showing the exact
    target/action/parameters and receiving human approval, may call it. V1 has
    no such endpoint and installs no executors. Restart invalidates all receipts.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._key = secrets.token_bytes(32)
        self._clock = clock
        self._issued: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue_after_confirmation(self, principal: Principal, request: ActionRequest,
                                 ttl_seconds: int = 60) -> ConfirmationReceipt:
        _check_grant(principal, request)
        if not 1 <= ttl_seconds <= 300:
            raise ValueError('Confirmation lifetime must be between 1 and 300 seconds.')
        now = self._clock()
        unsigned = ConfirmationReceipt(
            principal.username, request.action, request.target,
            _parameters_digest(request.parameters), now + ttl_seconds,
            secrets.token_urlsafe(24), '',
        )
        signature = hmac.new(self._key, _receipt_payload(unsigned), hashlib.sha256).hexdigest()
        receipt = ConfirmationReceipt(**{**unsigned.__dict__, 'signature': signature})
        with self._lock:
            self._issued = {nonce: expiry for nonce, expiry in self._issued.items() if expiry > now}
            self._issued[receipt.nonce] = receipt.expires_at
        return receipt

    def consume(self, principal: Principal, request: ActionRequest, receipt: ConfirmationReceipt) -> None:
        _check_grant(principal, request)
        if not isinstance(receipt, ConfirmationReceipt):
            raise PermissionError('A server-issued confirmation receipt is required.')
        if (receipt.username, receipt.action, receipt.target, receipt.parameters_digest) != (
            principal.username, request.action, request.target, _parameters_digest(request.parameters),
        ):
            raise PermissionError('Confirmation does not match the principal and exact action.')
        try:
            expected = hmac.new(self._key, _receipt_payload(receipt), hashlib.sha256).hexdigest()
        except (TypeError, ValueError):
            raise PermissionError('Invalid confirmation receipt.') from None
        if not isinstance(receipt.signature, str) or not hmac.compare_digest(expected, receipt.signature):
            raise PermissionError('Invalid confirmation receipt.')
        with self._lock:
            expires_at = self._issued.get(receipt.nonce)
            if expires_at is None or expires_at != receipt.expires_at or expires_at <= self._clock():
                self._issued.pop(receipt.nonce, None)
                raise PermissionError('Confirmation expired, was revoked, or has already been used.')
            del self._issued[receipt.nonce]


def authorize_action(request: ActionRequest, principal: Principal,
                     authority: ConfirmationAuthority | None = None,
                     receipt: ConfirmationReceipt | None = None) -> None:
    """Validate policy only; success does not install or invoke an adapter."""
    risk = _check_grant(principal, request)
    if risk is Risk.YELLOW:
        if authority is None or receipt is None:
            raise PermissionError('This action requires explicit human confirmation.')
        authority.consume(principal, request, receipt)
