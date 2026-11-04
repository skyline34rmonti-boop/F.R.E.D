"""Future contracts fail closed and never claim configured hardware is connected."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.contracts import DeviceDefinition, RoomDefinition
from app.integrations.registry import DeviceRegistry, INTEGRATIONS
from app.voice.contracts import VoiceSettings


def configuration(**overrides):
    return Settings(_env_file=None, owner_password='test-only-password', **overrides)


def test_default_configuration_is_mock_and_has_no_hardware_requirements():
    settings = configuration()
    settings.validate_startup()
    assert settings.owner_username == 'owner'
    assert settings.owner_name == 'Owner'
    assert settings.ai_provider == 'mock'
    assert settings.memory_enabled
    assert settings.feature_flags == {'memory': True, 'voice': False, 'smart_home': False, 'remote_control': False, 'automations': False}
    assert settings.device_registry.devices == {}
    assert all(item['status'] == 'planned' for item in INTEGRATIONS)


@pytest.mark.parametrize('feature', ['voice_enabled', 'smart_home_enabled', 'remote_control_enabled', 'automations_enabled'])
def test_unsupported_feature_cannot_silently_enable_itself(feature):
    with pytest.raises(RuntimeError, match='Unavailable in V1'):
        configuration(**{feature: True}).validate_startup()


def test_feature_configuration_and_devices_load_from_environment(monkeypatch):
    monkeypatch.setenv('FRED_MEMORY_ENABLED', 'false')
    monkeypatch.setenv('FRED_VOICE', '{"microphone_id":"usb-mic","speaker_id":"usb-speaker","echo_cancellation":"required"}')
    monkeypatch.setenv('FRED_ROOMS', '[{"id":"office","name":"Office"}]')
    monkeypatch.setenv('FRED_DEVICES', '[{"id":"desk","name":"Desk lamp","kind":"light","room_id":"office","actions":["device.turn_on"]}]')
    settings = configuration()
    settings.validate_startup()
    assert not settings.memory_enabled
    assert settings.voice.microphone_id == 'usb-mic'
    assert settings.voice.echo_cancellation == 'required'
    registry = settings.device_registry
    assert registry.in_room('office')[0].id == 'desk'
    assert not registry.status('desk').available
    assert registry.status('desk').state == {}
    with pytest.raises(KeyError):
        registry.status('unregistered')
    with pytest.raises(KeyError):
        registry.in_room('unregistered')


def test_registry_validates_unique_identifiers_and_room_references():
    room = RoomDefinition(id='office', name='Office')
    device = DeviceDefinition(id='desk', name='Desk', kind='light', room_id='office')
    with pytest.raises(ValueError, match='Room IDs must be unique'):
        DeviceRegistry([room, room])
    with pytest.raises(ValueError, match='Device IDs must be unique'):
        DeviceRegistry([room], [device, device])
    with pytest.raises(ValueError, match='room_id'):
        DeviceRegistry([], [device])
    with pytest.raises(ValidationError, match='room_id'):
        configuration(devices=[device])


def test_registry_rejects_arbitrary_shell_commands_and_invalid_capabilities():
    for action in ['shell', 'rm -rf /', 'device.set_temperature']:
        device = DeviceDefinition(id='light', name='Light', kind='light', actions=[action])
        with pytest.raises(ValueError, match='Unsupported action'):
            DeviceRegistry(devices=[device])
    with pytest.raises(ValueError, match='unique'):
        DeviceRegistry(devices=[DeviceDefinition(id='sensor', name='Sensor', kind='sensor', actions=['device.status', 'device.status'])])


@pytest.mark.parametrize('overrides', [
    {'wake_word_local_only': False}, {'listening_timeout_seconds': 0},
    {'conversation_timeout_seconds': 3600}, {'echo_cancellation': 'pretend-supported'},
])
def test_voice_configuration_preserves_local_wakeword_and_bounded_timeouts(overrides):
    with pytest.raises(ValidationError):
        VoiceSettings(**overrides)


@pytest.mark.parametrize('origin', ['*', 'https://*.example.com', 'https://example.com/path', 'https://user:secret@example.com', 'javascript:example.com'])
def test_browser_origins_are_explicit_and_do_not_accept_credentials_or_wildcards(origin):
    with pytest.raises(ValidationError):
        configuration(allowed_origins=[origin])


def test_personality_is_configuration_not_provider_selection():
    settings = configuration(personality_instruction='Use brief, professional language.')
    assert settings.personality_instruction == 'Use brief, professional language.'
    assert settings.ai_provider == 'mock'
