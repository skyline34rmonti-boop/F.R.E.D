"""Future voice boundaries. V1 neither records audio nor installs speech dependencies.

Wake-word/VAD adapters must process ambient audio locally. Only an explicitly
activated utterance may reach a configured transcription service. A future voice
controller submits resulting text to the same core conversation pipeline as the
keyboard client, and cancels pending response/TTS tasks when interrupted.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class VoiceSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    wake_phrase: str = Field('Hey Fred', min_length=1, max_length=80)
    microphone_id: str | None = Field(None, max_length=200)
    speaker_id: str | None = Field(None, max_length=200)
    listening_timeout_seconds: float = Field(8, ge=1, le=120)
    conversation_timeout_seconds: float = Field(60, ge=1, le=1800)
    silence_timeout_seconds: float = Field(1.5, ge=0.1, le=30)
    echo_cancellation: Literal['off', 'if_supported', 'required'] = 'if_supported'
    # Cloud wake-word monitoring is intentionally not a configurable option.
    wake_word_local_only: Literal[True] = True


@dataclass(frozen=True)
class AudioFrame:
    samples: bytes
    sample_rate: int
    channels: int


class AudioInput(Protocol):
    supports_echo_cancellation: bool
    def frames(self) -> AsyncIterator[AudioFrame]: ...
    async def close(self) -> None: ...


class WakeWordDetector(Protocol):
    local_only: Literal[True]
    async def detected(self, frame: AudioFrame) -> bool: ...
    async def reset(self) -> None: ...


class VoiceActivityDetector(Protocol):
    async def contains_speech(self, frame: AudioFrame) -> bool: ...


class SpeechRecognizer(Protocol):
    async def transcribe(self, audio: bytes, content_type: str) -> str: ...


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str, voice: str) -> bytes: ...


class AudioOutput(Protocol):
    async def play(self, audio: bytes, content_type: str) -> None: ...
    async def stop(self) -> None: ...


class VoiceConversation(Protocol):
    """Controller boundary: cancel interrupts inference/playback, never permissions."""
    async def submit_transcript(self, text: str, session_id: str | None = None) -> str: ...
    async def cancel(self) -> None: ...
