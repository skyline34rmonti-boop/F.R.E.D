"""Authenticated keyboard client for the headless FRED service.

Run from backend: python -m app.cli. No browser, Node.js, or desktop is needed.
The client uses the same HTTP conversation pipeline as the optional dashboard.
"""
import argparse
import getpass
import ipaddress
import os
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.io import ConsoleOutput, KeyboardInput, TextInput, TextOutput

HELP = '''Enter text to converse. Commands:
/help                       Show commands
/new                        Start a new persistent conversation
/sessions                   List saved conversations
/use ID                     Select a saved conversation
/history                    Inspect selected conversation messages
/delete-session ID          Delete a conversation after confirmation
/memories [SEARCH]           Inspect approved memories
/remember CATEGORY TEXT     Approve and save a memory
/memory-edit ID TEXT         Correct a saved memory
/forget ID                  Delete a memory after confirmation
/mode MODE                  standard, executive, casual, focus, briefing
/model MODEL                Select the configured provider's model
/status                     Show provider and storage status
/quit                       Sign out and exit
Memory categories: personal, operational, conversation, system.'''


class ClientError(Exception):
    """A sanitized client-facing error; HTTP bodies and credentials are omitted."""


def validate_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        parsed.port  # Validate port syntax and bounds.
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
            raise ValueError
        if parsed.scheme == 'http' and not is_loopback(parsed.hostname):
            raise ValueError
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            'Use a root service URL; HTTP is allowed only for loopback hosts. Remote connections require HTTPS.'
        ) from exc
    return value.rstrip('/')


def is_loopback(host: str) -> bool:
    if host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def record_id(value: str) -> str:
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise ClientError('Supply the full record ID shown by /sessions or /memories.') from exc


class FredClient:
    """HTTP adapter; inject a Client with MockTransport for independent tests."""
    def __init__(self, client: httpx.Client):
        self.client = client
        self.csrf_token: str | None = None

    def request(self, method: str, path: str, data: dict | None = None, **kwargs):
        headers = {}
        if method != 'GET' and self.csrf_token:
            headers['X-CSRF-Token'] = self.csrf_token
        try:
            response = self.client.request(method, path, json=data, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise ClientError('Request timed out. A submitted message may still finish; check /history before retrying.') from exc
        except httpx.RequestError as exc:
            raise ClientError('Cannot reach FRED. Check that the service is running and the URL is correct.') from exc
        if not response.is_success:
            messages = {
                401: 'Sign-in failed or your session expired. Check your credentials and sign in again.',
                403: 'Permission denied. Sign in again if your session changed.',
                404: 'Record not found. Refresh /sessions or /memories.',
                409: 'FRED is busy. Wait for the current response before retrying.',
                422: 'Invalid input. Check /help, record IDs, categories, and text length.',
                429: 'Rate limit reached. Wait a minute before retrying.',
            }
            raise ClientError(messages.get(response.status_code,
                f'FRED returned HTTP {response.status_code}. Check service diagnostics; submitted messages may be saved.'))
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ClientError('FRED returned an invalid response. Check service diagnostics.') from exc

    def login(self, username: str, password: str) -> None:
        response = self.request('POST', '/api/auth/login', {'username': username, 'password': password})
        try:
            csrf = response['csrf_token']
            if not isinstance(csrf, str) or not csrf:
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise ClientError('FRED returned an invalid sign-in response.') from exc
        self.csrf_token = csrf

    def logout(self) -> None:
        try:
            if self.csrf_token:
                self.request('POST', '/api/auth/logout')
        finally:
            self.csrf_token = None
            self.client.cookies.clear()


class TerminalSession:
    """Adapter-independent keyboard workflow, with explicit memory approval."""
    def __init__(self, api: FredClient, source: TextInput, output: TextOutput):
        self.api = api
        self.source = source
        self.output = output
        self.conversation_id: str | None = None

    def write(self, text: str) -> None:
        self.output.write(text)

    def new_session(self) -> None:
        response = self.api.request('POST', '/api/conversations', {})
        self.conversation_id = response['id']
        self.write(f'Conversation: {self.conversation_id}')

    def confirm(self, label: str) -> bool:
        return self.source.read(f'{label} Type DELETE to confirm: ').strip() == 'DELETE'

    def execute(self, line: str) -> bool:
        """Process one complete input. Future transcription can call this boundary."""
        line = line.strip()
        if not line:
            return True
        if not line.startswith('/'):
            if len(line) > 8000:
                raise ClientError('Messages must contain at most 8000 characters.')
            if self.conversation_id is None:
                self.new_session()
            response = self.api.request('POST', '/api/chat', {
                'message': line, 'conversation_id': self.conversation_id,
            })
            self.conversation_id = response['conversation_id']
            self.write(f"FRED: {response['message']['content']}")
            return True
        command, _, argument = line.partition(' ')
        argument = argument.strip()
        match command.lower():
            case '/quit' | '/exit':
                return False
            case '/help':
                self.write(HELP)
            case '/new':
                self.new_session()
            case '/sessions':
                records = self.api.request('GET', '/api/conversations')
                self.write('\n'.join(f"{item['id']}  {item['title']}" for item in records) or 'No saved conversations.')
            case '/use':
                selected = record_id(argument)
                self.api.request('GET', f'/api/conversations/{selected}/messages')
                self.conversation_id = selected
                self.write(f'Conversation: {selected}')
            case '/history':
                if self.conversation_id is None:
                    self.write('No conversation selected. Use /sessions and /use ID, or enter a message.')
                else:
                    records = self.api.request('GET', f'/api/conversations/{self.conversation_id}/messages')
                    self.write('\n'.join(f"{item['role']}: {item['content']}" for item in records) or 'No messages yet.')
            case '/delete-session':
                selected = record_id(argument)
                if self.confirm(f'Delete conversation {selected}?'):
                    self.api.request('DELETE', f'/api/conversations/{selected}')
                    if self.conversation_id == selected:
                        self.conversation_id = None
                    self.write('Conversation deleted.')
                else:
                    self.write('Deletion cancelled.')
            case '/memories':
                records = self.api.request('GET', '/api/memories', params={'q': argument})
                self.write('\n'.join(f"{item['id']}  [{item['category']}] {item['content']}" for item in records) or 'No approved memories found.')
            case '/remember':
                category, _, content = argument.partition(' ')
                if category not in {'personal', 'operational', 'conversation', 'system'} or not content.strip() or len(content.strip()) > 4000:
                    raise ClientError('Use /remember CATEGORY TEXT; text must be 1–4000 characters. See /help for categories.')
                saved = self.api.request('POST', '/api/memories', {'category': category, 'content': content.strip()})
                self.write(f"Memory approved and saved: {saved['id']}")
            case '/memory-edit':
                selected, _, content = argument.partition(' ')
                selected = record_id(selected)
                if not content.strip() or len(content.strip()) > 4000:
                    raise ClientError('Use /memory-edit ID TEXT; text must be 1–4000 characters.')
                self.api.request('PATCH', f'/api/memories/{selected}', {'content': content.strip()})
                self.write('Memory corrected.')
            case '/forget':
                selected = record_id(argument)
                if self.confirm(f'Delete memory {selected}?'):
                    self.api.request('DELETE', f'/api/memories/{selected}')
                    self.write('Memory deleted.')
                else:
                    self.write('Deletion cancelled.')
            case '/mode':
                if argument not in {'standard', 'executive', 'casual', 'focus', 'briefing'}:
                    raise ClientError('Choose standard, executive, casual, focus, or briefing.')
                prefs = self.api.request('PUT', '/api/settings', {'mode': argument})
                self.write(f"Mode: {prefs['mode']}")
            case '/model':
                if not argument or len(argument) > 120:
                    raise ClientError('Use /model MODEL with a supported provider model name.')
                prefs = self.api.request('PUT', '/api/settings', {'model': argument})
                self.write(f"Model: {prefs['model']}")
            case '/status':
                system = self.api.request('GET', '/api/system')
                self.write(f"Provider: {system['provider']} | Model: {system['model']} | Database: {system['database']}")
            case _:
                raise ClientError('Unknown command. Use /help; no shell commands are supported.')
        return True

    def run(self, username: str) -> int:
        logged_in = False
        try:
            password = self.source.read_secret('FRED password (hidden): ')
            if not password:
                raise ClientError('A password is required. Read it privately from the server configuration.')
            try:
                self.api.login(username, password)
            finally:
                password = ''
            logged_in = True
            self.write('Signed in. Enter a message, /help for commands, or /quit to exit.')
            while True:
                try:
                    if not self.execute(self.source.read('You: ')):
                        break
                except ClientError as exc:
                    self.write(str(exc))
                except (KeyError, TypeError, ValueError):
                    self.write('FRED returned an unexpected response. Check service diagnostics.')
            return 0
        except (EOFError, KeyboardInterrupt):
            self.write('Stopped. Any submitted request may still finish; use /history before retrying.')
            return 0
        except getpass.GetPassWarning:
            self.write('A private terminal is required for password input. Open an interactive terminal and retry.')
            return 1
        except ClientError as exc:
            self.write(str(exc))
            return 1
        finally:
            if logged_in:
                try:
                    self.api.logout()
                    self.write('Signed out.')
                except (ClientError, KeyboardInterrupt):
                    self.write('Could not revoke the session. It will expire automatically; no local token was retained.')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='FRED keyboard client. Start the Python service first.')
    parser.add_argument('--url', type=validate_url, default='http://127.0.0.1:8000', help='Service root URL; remote hosts require HTTPS.')
    parser.add_argument('--username', default=os.environ.get('FRED_OWNER_USERNAME', 'owner'), help='Configured owner username; password is prompted privately.')
    args = parser.parse_args(argv)
    if not args.username.strip() or len(args.username) > 80:
        parser.error('Username must contain 1–80 characters.')
    parsed = urlsplit(args.url)
    with httpx.Client(base_url=args.url, timeout=httpx.Timeout(120, connect=5),
                      follow_redirects=False, trust_env=not is_loopback(parsed.hostname or '')) as client:
        return TerminalSession(FredClient(client), KeyboardInput(), ConsoleOutput()).run(args.username.strip())


if __name__ == '__main__':
    raise SystemExit(main())
