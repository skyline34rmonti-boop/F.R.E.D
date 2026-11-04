"""Text adapters contain terminal-specific behavior, never assistant reasoning."""
import getpass
import re
import warnings
from typing import Protocol


class TextInput(Protocol):
    def read(self, prompt: str = '') -> str:
        """Return a complete input, or raise EOFError/KeyboardInterrupt."""
        ...

    def read_secret(self, prompt: str = '') -> str:
        """Read a credential without echoing or recording it."""
        ...


class TextOutput(Protocol):
    def write(self, text: str) -> None: ...


class KeyboardInput:
    def read(self, prompt: str = '') -> str:
        return input(prompt)

    def read_secret(self, prompt: str = '') -> str:
        # Refuse getpass's echoing fallback when a private terminal is unavailable.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass(prompt)


class ConsoleOutput:
    def write(self, text: str) -> None:
        # Provider responses and stored records are untrusted terminal data.
        text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
        text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
        text = ''.join(char for char in text if char in '\n\t' or (char.isprintable() and char != '\x7f'))
        print(text)
