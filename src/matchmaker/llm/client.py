"""LLM client abstraction supporting OpenRouter and local LLMs."""

import logging
from typing import Optional

from openai import OpenAI

from matchmaker.config import LLMProvider, settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client for OpenRouter and local LLMs."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = provider or settings.llm_provider
        self.model = model or settings.active_llm_model
        self.base_url = base_url or settings.active_llm_base_url
        self.api_key = api_key or settings.active_llm_api_key

        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            extra_headers = {}
            if self.provider == LLMProvider.OPENROUTER:
                extra_headers = {
                    "HTTP-Referer": "https://matchmaker-agent.local",
                    "X-Title": "Matchmaker Agent",
                }

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers=extra_headers if extra_headers else None,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a chat completion request."""
        full_messages = []

        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})

        full_messages.extend(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate text from a single prompt."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )


_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the default LLM client instance."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
