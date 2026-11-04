import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger('fred.events')


class EventHub:
    def __init__(self) -> None:
        self.clients: dict[str, set[WebSocket]] = {}
        self.statuses: dict[str, dict] = {}

    def connect(self, owner: str, socket: WebSocket) -> None:
        self.clients.setdefault(owner, set()).add(socket)

    def disconnect(self, owner: str, socket: WebSocket) -> None:
        self.clients.get(owner, set()).discard(socket)

    async def emit(self, owner: str, status: str, conversation_id: str | None = None) -> None:
        event = {'type': 'status', 'status': status, 'conversation_id': conversation_id}
        self.statuses[owner] = event
        for socket in list(self.clients.get(owner, set())):
            try:
                await asyncio.wait_for(socket.send_json(event), timeout=1)
            except Exception:
                self.disconnect(owner, socket)
