import argparse
import json

import httpx
import pytest

from app.cli import FredClient, TerminalSession, main, validate_url
from app.io.text import ConsoleOutput

SESSION = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
MEMORY = '33333333-3333-4333-8333-333333333333'


class Input:
    def __init__(self, lines, password='private-test-password'):
        self.lines = iter(lines)
        self.password = password

    def read(self, prompt=''):
        item = next(self.lines, EOFError())
        if isinstance(item, BaseException):
            raise item
        return item

    def read_secret(self, prompt=''):
        return self.password


class Output:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)


class Server:
    def __init__(self):
        self.calls = []
        self.messages = []
        self.memories = []

    def __call__(self, request):
        data = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, data, dict(request.headers)))
        if path == '/api/auth/login':
            assert data == {'username': 'owner', 'password': 'private-test-password'}
            return httpx.Response(200, json={'csrf_token': 'private-csrf'}, headers={'set-cookie': 'fred_session=private-cookie; Path=/api; HttpOnly'})
        assert request.headers['cookie'] == 'fred_session=private-cookie'
        if request.method != 'GET':
            assert request.headers['x-csrf-token'] == 'private-csrf'
        if path == '/api/auth/logout':
            return httpx.Response(204)
        if path == '/api/conversations':
            if request.method == 'POST':
                return httpx.Response(201, json={'id': SESSION})
            return httpx.Response(200, json=[{'id': SESSION, 'title': 'Saved chat'}, {'id': OTHER, 'title': 'Other chat'}])
        if path.endswith('/messages'):
            return httpx.Response(200, json=self.messages)
        if path == '/api/chat':
            self.messages.extend([{'role': 'user', 'content': data['message']}, {'role': 'assistant', 'content': 'Mock response'}])
            return httpx.Response(200, json={'conversation_id': data['conversation_id'], 'provider': 'mock', 'message': self.messages[-1]})
        if path == '/api/memories':
            if request.method == 'POST':
                self.memories.append({'id': MEMORY, **data})
                return httpx.Response(201, json=self.memories[-1])
            return httpx.Response(200, json=self.memories)
        if path == f'/api/memories/{MEMORY}':
            if request.method == 'PATCH':
                self.memories[0]['content'] = data['content']
                return httpx.Response(200, json=self.memories[0])
            self.memories.clear()
            return httpx.Response(204)
        if path.startswith('/api/conversations/') and request.method == 'DELETE':
            return httpx.Response(204)
        if path == '/api/settings':
            return httpx.Response(200, json=data)
        if path == '/api/system':
            return httpx.Response(200, json={'provider': 'mock', 'model': 'test-model', 'database': 'connected'})
        raise AssertionError(f'Unexpected request: {request.method} {path}')


def run(lines, server=None):
    server = server or Server()
    output = Output()
    with httpx.Client(base_url='http://127.0.0.1:8000', transport=httpx.MockTransport(server)) as client:
        api = FredClient(client)
        session = TerminalSession(api, Input(lines), output)
        status = session.run('owner')
        assert not api.csrf_token
        assert not client.cookies
    return status, output.lines, server, session


def test_chat_reuses_selected_session_and_logs_out_without_disclosing_credentials():
    status, lines, server, session = run(['Hello FRED', 'Continue this conversation', '/history', '/quit'])
    assert status == 0
    chats = [call[2] for call in server.calls if call[1] == '/api/chat']
    assert chats == [
        {'message': 'Hello FRED', 'conversation_id': SESSION},
        {'message': 'Continue this conversation', 'conversation_id': SESSION},
    ]
    assert len([call for call in server.calls if call[:2] == ('POST', '/api/conversations')]) == 1
    assert 'FRED: Mock response' in lines
    assert any('user: Hello FRED' in line and 'assistant: Mock response' in line for line in lines)
    assert server.calls[-1][1] == '/api/auth/logout'
    assert 'Signed out.' in lines
    assert 'private-' not in '\n'.join(lines)


def test_session_selection_and_explicit_deletion_confirmation():
    status, lines, server, session = run(['/sessions', f'/use {OTHER}', 'Selected conversation', f'/delete-session {OTHER}', 'no', f'/delete-session {OTHER}', 'DELETE', '/quit'])
    assert status == 0
    assert any(OTHER in line for line in lines)
    assert next(call for call in server.calls if call[1] == '/api/chat')[2]['conversation_id'] == OTHER
    assert len([call for call in server.calls if call[:2] == ('DELETE', f'/api/conversations/{OTHER}')]) == 1
    assert 'Deletion cancelled.' in lines
    assert session.conversation_id is None


def test_user_approved_memory_create_inspect_correct_and_delete():
    status, lines, server, _ = run([
        '/remember personal Prefer concise answers', '/memories concise',
        f'/memory-edit {MEMORY} Prefer detailed answers', '/memories',
        f'/forget {MEMORY}', 'cancel', f'/forget {MEMORY}', 'DELETE', '/quit',
    ])
    assert status == 0
    assert any('Prefer concise answers' in line for line in lines)
    assert any('Prefer detailed answers' in line for line in lines)
    assert 'Memory corrected.' in lines
    assert 'Memory deleted.' in lines
    assert server.memories == []


def test_modes_model_status_and_unknown_commands_do_not_become_chat():
    _, lines, server, _ = run(['/help', '/mode focus', '/model test-model', '/status', '/bin/sh', '/quit'])
    assert 'Mode: focus' in lines
    assert 'Model: test-model' in lines
    assert any('Provider: mock' in line for line in lines)
    assert any('no shell commands' in line for line in lines)
    assert not any(call[1] == '/api/chat' for call in server.calls)


@pytest.mark.parametrize('bad_input', [
    '/use ../../auth/logout', '/forget not-a-uuid', '/mode dangerous',
    '/remember invalid text', '/remember personal ', '/memory-edit not-an-id value',
    'x' * 8001,
])
def test_invalid_input_does_not_make_mutating_request(bad_input):
    _, lines, server, _ = run([bad_input, '/quit'])
    assert len(server.calls) == 2
    assert len(lines) >= 3


@pytest.mark.parametrize('interruption', [EOFError(), KeyboardInterrupt()])
def test_eof_and_ctrl_c_gracefully_revoke_session(interruption):
    status, lines, server, _ = run([interruption])
    assert status == 0
    assert server.calls[-1][1] == '/api/auth/logout'
    assert any('Stopped.' in line for line in lines)


def test_interrupt_during_sensitive_confirmation_does_not_delete():
    status, lines, server, _ = run([f'/forget {MEMORY}', KeyboardInterrupt()])
    assert status == 0
    assert not any(call[0] == 'DELETE' for call in server.calls)
    assert server.calls[-1][1] == '/api/auth/logout'


def test_http_failures_are_sanitized_and_prompt_can_continue():
    server = Server()

    def fail_chat(request):
        if request.url.path == '/api/chat':
            return httpx.Response(502, json={'detail': 'private-provider-key and traceback'})
        return server(request)

    status, lines, _, _ = run(['hello', '/status', '/quit'], fail_chat)
    assert status == 0
    assert any('HTTP 502' in line for line in lines)
    assert any('Provider: mock' in line for line in lines)
    assert 'private-provider-key' not in '\n'.join(lines)


def test_connection_timeout_does_not_leak_exception_contents():
    def timeout(request):
        raise httpx.ReadTimeout('private-cookie or sensitive endpoint', request=request)

    status, lines, _, _ = run([], timeout)
    assert status == 1
    assert any('timed out' in line for line in lines)
    assert 'private-cookie' not in '\n'.join(lines)


@pytest.mark.parametrize('value', ['http://example.com', 'http://localhost.evil', 'https://u:secret@host', 'https://host/path', 'https://host?token=secret', 'file:///tmp/socket', 'https://host:bad', 'https://host#fragment'])
def test_url_validation_prevents_cleartext_remote_credentials(value):
    with pytest.raises(argparse.ArgumentTypeError):
        validate_url(value)


@pytest.mark.parametrize('value', ['http://127.0.0.1:8000', 'http://localhost:8000', 'http://[::1]:8000', 'https://fred.example.com'])
def test_valid_service_urls(value):
    assert validate_url(value) == value


def test_main_never_accepts_password_in_arguments():
    with pytest.raises(SystemExit) as exc:
        main(['--password', 'secret'])
    assert exc.value.code == 2


def test_terminal_output_removes_control_sequences(capsys):
    ConsoleOutput().write('Hello\x1b[2J\x1b]0;malicious title\x07 world\x08!\nNext line')
    assert capsys.readouterr().out == 'Hello world!\nNext line\n'
