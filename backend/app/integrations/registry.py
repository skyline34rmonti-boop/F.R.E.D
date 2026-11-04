"""Configuration-backed device catalog. Declarations never imply live connectivity."""
from collections.abc import Sequence

from app.integrations.contracts import DeviceDefinition, DeviceStatus, RoomDefinition

# Action names define the future supported surface, not an installed executor.
DEVICE_ACTIONS = {
    'light': frozenset({'device.turn_on', 'device.turn_off', 'device.set_brightness'}),
    'plug': frozenset({'device.turn_on', 'device.turn_off'}),
    'sensor': frozenset({'device.status'}),
    'thermostat': frozenset({'device.status', 'device.set_temperature'}),
    'computer': frozenset({'computer.status', 'computer.lock', 'computer.shutdown'}),
}


class DeviceRegistry:
    def __init__(self, rooms: Sequence[RoomDefinition] = (), devices: Sequence[DeviceDefinition] = ()) -> None:
        self.rooms = {room.id: room for room in rooms}
        self.devices = {device.id: device for device in devices}
        if len(self.rooms) != len(rooms):
            raise ValueError('Room IDs must be unique.')
        if len(self.devices) != len(devices):
            raise ValueError('Device IDs must be unique.')
        for device in devices:
            if device.room_id is not None and device.room_id not in self.rooms:
                raise ValueError('Every device room_id must reference a configured room.')
            if len(set(device.actions)) != len(device.actions):
                raise ValueError('Device action names must be unique.')
            if not set(device.actions) <= DEVICE_ACTIONS[device.kind.value]:
                raise ValueError('Unsupported action for this device kind; arbitrary commands are unavailable.')

    def in_room(self, room_id: str) -> tuple[DeviceDefinition, ...]:
        if room_id not in self.rooms:
            raise KeyError('Room is not registered.')
        return tuple(device for device in self.devices.values() if device.room_id == room_id)

    def status(self, device_id: str) -> DeviceStatus:
        if device_id not in self.devices:
            raise KeyError('Device is not registered.')
        return DeviceStatus(device_id, False, {}, 'Configured only; no device adapter is installed in V1.')


INTEGRATIONS = [
    {'id': 'calendar', 'name': 'Calendar', 'status': 'planned', 'detail': 'Provider authorization is not implemented.'},
    {'id': 'email', 'name': 'Email', 'status': 'planned', 'detail': 'Read and draft workflows are not connected.'},
    {'id': 'weather', 'name': 'Weather', 'status': 'planned', 'detail': 'No location or weather provider configured.'},
    {'id': 'search', 'name': 'Search', 'status': 'planned', 'detail': 'External search is not connected.'},
    {'id': 'home_assistant', 'name': 'Home Assistant', 'status': 'planned', 'detail': 'Room/device configuration contracts only; no adapter is installed.'},
    {'id': 'computer', 'name': 'Computer control', 'status': 'planned', 'detail': 'Authenticated named-action contracts only; no remote executor is installed.'},
    {'id': 'spotify', 'name': 'Spotify', 'status': 'planned', 'detail': 'Official OAuth and playback capabilities are not connected.'},
]
