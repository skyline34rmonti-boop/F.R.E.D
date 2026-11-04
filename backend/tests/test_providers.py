"""Exercise the official SDK adapter without live network calls or credentials."""
import asyncio
import json

import httpx
import openai
import pytest

import app.ai.providers as providers


def run_provider(monkeypatch, handler):
    original_client = openai.AsyncOpenAI

    def fake_client(**kwargs):
        kwargs["max_retries"] = 0
        return original_client(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )

    monkeypatch.setattr(providers, "AsyncOpenAI", fake_client)

    async def invoke():
        provider = providers.OpenAIProvider("test-key-not-a-real-credential")
        try:
            return await provider.complete([{"role": "user", "content": "Hello"}], "gpt-4.1-mini")
        finally:
            await provider.close()

    return asyncio.run(invoke())


def test_openai_adapter_returns_text_from_supported_chat_api(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["messages"] == [{"role": "user", "content": "Hello"}]
        assert body["model"] == "gpt-4.1-mini"
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 1,
            "model": "gpt-4.1-mini",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "  Ready, Owner.  "},
                         "finish_reason": "stop"}],
        })

    assert run_provider(monkeypatch, handler) == "Ready, Owner."


@pytest.mark.parametrize("upstream_status, expected_status, phrase", [
    (401, 502, "authentication"),
    (429, 429, "quota"),
    (400, 502, "model"),
    (403, 502, "access"),
    (404, 502, "model"),
    (500, 502, "could not complete"),
])
def test_openai_api_errors_are_clear_without_leaking_provider_details(
    monkeypatch, upstream_status, expected_status, phrase,
):
    def handler(request):
        return httpx.Response(upstream_status, json={"error": {
            "message": "sensitive upstream diagnostic test-key-not-a-real-credential",
            "type": "test_error", "code": "test_error",
        }})

    with pytest.raises(providers.ProviderError) as error:
        run_provider(monkeypatch, handler)
    assert error.value.status_code == expected_status
    assert phrase in error.value.detail.lower()
    assert "sensitive upstream" not in error.value.detail
    assert "test-key" not in error.value.detail


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_openai_network_failures_return_retryable_message(monkeypatch, failure):
    def handler(request):
        raise failure("Unavailable network", request=request)

    with pytest.raises(providers.ProviderError) as error:
        run_provider(monkeypatch, handler)
    assert error.value.status_code == 503
    assert "unreachable" in error.value.detail


def test_empty_openai_completion_does_not_appear_successful(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "id": "chatcmpl-empty", "object": "chat.completion", "created": 1,
            "model": "gpt-4.1-mini",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                         "finish_reason": "stop"}],
        })

    with pytest.raises(providers.ProviderError) as error:
        run_provider(monkeypatch, handler)
    assert "no text" in error.value.detail.lower()
