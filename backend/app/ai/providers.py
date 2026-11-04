"""Chained conversation boundary; future real-time voice uses a separate transport."""
from typing import Protocol

from openai import (
    APIConnectionError, APIError, APITimeoutError, AsyncOpenAI,
    AuthenticationError, BadRequestError, NotFoundError, PermissionDeniedError, RateLimitError,
)


class ProviderError(Exception):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ConversationProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], model: str) -> str: ...


class MockProvider:
    async def complete(self, messages: list[dict[str, str]], model: str) -> str:
        latest = next((item['content'] for item in reversed(messages) if item['role'] == 'user'), '')
        lowered = latest.lower()
        if any(word in lowered for word in ('briefing', 'calendar', 'weather', 'email', 'spotify', 'lights', 'reserve')):
            return ('[Mock AI · local demonstration] This deployment has no connected calendar, '
                    'email, weather, business records or home controls. I can organize a plan from information '
                    'you provide. Connect an authorized provider in a later phase for live information or actions.')
        if 'remember' in lowered or 'memory' in lowered:
            return ('[Mock AI · local demonstration] Use the Memory panel to save approved details, review them, '
                    'or remove them. I do not automatically store personal facts from our conversation.')
        return ('[Mock AI · local demonstration] Ready. Your conversation is saved locally. '
                'This is a deterministic connectivity response; configure the OpenAI provider for reasoning and natural conversation.')


class OpenAIProvider:
    def __init__(self, api_key: str, timeout: float = 45) -> None:
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=1)

    async def complete(self, messages: list[dict[str, str]], model: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=model, messages=messages, max_completion_tokens=1600,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ProviderError('OpenAI returned no text. Please retry or choose a text-capable model.')
            return content.strip()
        except AuthenticationError as exc:
            raise ProviderError('OpenAI authentication failed. Check the server-side OPENAI_API_KEY.', 502) from exc
        except RateLimitError as exc:
            raise ProviderError('OpenAI usage or rate limit reached. Check your account quota and retry later.', 429) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ProviderError('OpenAI is temporarily unreachable. Your message is saved; please retry later.', 503) from exc
        except (BadRequestError, NotFoundError, PermissionDeniedError) as exc:
            raise ProviderError('OpenAI rejected this model or request. Check the configured model and account access.', 502) from exc
        except APIError as exc:
            raise ProviderError('OpenAI could not complete the request. Your message is saved; please retry later.', 502) from exc

    async def close(self) -> None:
        await self.client.close()
