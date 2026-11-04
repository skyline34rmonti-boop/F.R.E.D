from dataclasses import replace

import pytest

from app.permissions.policy import (
    ActionRequest, Authorization, ConfirmationAuthority, Principal, Risk,
    ToolDefinition, authorize_action, authorize_tool,
)


def principal(username='owner', authenticated=True):
    return Principal(username, authenticated, frozenset({
        ('office.light', 'device.status'), ('office.light', 'device.turn_on'),
        ('office.light', 'device.turn_off'), ('office.plug', 'device.turn_on'),
        ('gaming-pc', 'computer.shutdown'), ('gaming-pc', 'shell.execute'),
    }))


def test_status_requires_authentication_and_exact_explicit_grant():
    request = ActionRequest('device.status', 'office.light')
    authorize_action(request, principal())
    for denied in [Principal('owner'), principal(authenticated=False), principal(username=' '),
                   Principal('owner', True, frozenset({('office.plug', 'device.status')}))]:
        with pytest.raises(PermissionError):
            authorize_action(request, denied)


def test_sensitive_action_requires_real_single_use_receipt():
    request = ActionRequest('device.turn_on', 'office.light', {'brightness': 30})
    authority = ConfirmationAuthority()
    with pytest.raises(PermissionError):
        authorize_action(request, principal())
    receipt = authority.issue_after_confirmation(principal(), request)
    authorize_action(request, principal(), authority, receipt)
    with pytest.raises(PermissionError, match='already been used'):
        authorize_action(request, principal(), authority, receipt)


@pytest.mark.parametrize('change', [
    {'action': 'device.turn_off'}, {'target': 'office.plug'},
    {'parameters': {'brightness': 100}},
])
def test_confirmation_is_bound_to_exact_action_target_and_parameters(change):
    request = ActionRequest('device.turn_on', 'office.light', {'brightness': 30})
    authority = ConfirmationAuthority()
    receipt = authority.issue_after_confirmation(principal(), request)
    with pytest.raises(PermissionError, match='does not match'):
        authorize_action(replace(request, **change), principal(), authority, receipt)
    # A mismatch cannot spend the original user's valid confirmation.
    authorize_action(request, principal(), authority, receipt)


def test_confirmation_is_bound_to_user_and_not_transferable_between_authorities():
    request = ActionRequest('device.turn_on', 'office.light')
    authority = ConfirmationAuthority()
    receipt = authority.issue_after_confirmation(principal(), request)
    with pytest.raises(PermissionError):
        authorize_action(request, principal(username='other'), authority, receipt)
    with pytest.raises(PermissionError, match='Invalid confirmation'):
        authorize_action(request, principal(), ConfirmationAuthority(), receipt)


def test_forged_tampered_and_expired_receipts_fail():
    now = [1000.0]
    authority = ConfirmationAuthority(clock=lambda: now[0])
    request = ActionRequest('device.turn_on', 'office.light')
    receipt = authority.issue_after_confirmation(principal(), request, ttl_seconds=10)
    for tampered in [replace(receipt, signature='0' * 64), replace(receipt, signature=None),
                     replace(receipt, expires_at=9999999.0),
                     replace(receipt, nonce='invented')]:
        with pytest.raises(PermissionError, match='Invalid confirmation'):
            authorize_action(request, principal(), authority, tampered)
    now[0] = 1010.0
    with pytest.raises(PermissionError, match='expired'):
        authorize_action(request, principal(), authority, receipt)


def test_parameters_are_canonicalized_but_modification_invalidates_confirmation():
    authority = ConfirmationAuthority()
    request = ActionRequest('device.turn_on', 'office.light', {'brightness': 30, 'transition': 1})
    receipt = authority.issue_after_confirmation(principal(), request)
    reordered = ActionRequest('device.turn_on', 'office.light', {'transition': 1, 'brightness': 30})
    authorize_action(reordered, principal(), authority, receipt)


@pytest.mark.parametrize('action', ['shell.execute', 'os.system', 'computer.shutdown'])
def test_shell_and_unavailable_destructive_actions_are_never_enabled(action):
    request = ActionRequest(action, 'gaming-pc', {'command': 'arbitrary'})
    with pytest.raises(PermissionError):
        authorize_action(request, principal())
    with pytest.raises(PermissionError):
        ConfirmationAuthority().issue_after_confirmation(principal(), request)


@pytest.mark.parametrize('parameters', [{1: 'ambiguous'}, {'value': float('nan')}, {'value': object()}])
def test_action_parameters_must_be_bounded_json(parameters):
    with pytest.raises(ValueError):
        ActionRequest('device.turn_on', 'office.light', parameters)


def test_legacy_boolean_cannot_approve_sensitive_actions_and_blank_identity_denied():
    for risk in (Risk.YELLOW, Risk.RED):
        with pytest.raises(PermissionError):
            authorize_tool(ToolDefinition('light', risk), Authorization('owner', frozenset({'light'})), confirmed=True)
    with pytest.raises(PermissionError):
        authorize_tool(ToolDefinition('light', Risk.GREEN), Authorization('', frozenset({'light'})))
