"""OpenAI-compatible LLM client interface for local/remote models."""

from typing import Any

from fastapi import Depends
from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.core.logging import logger


class LLMService:
    """Wrapper around AsyncOpenAI for interchangeable OpenAI-compatible endpoints."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(
            base_url=self.settings.OPENAI_BASE_URL,
            api_key=self.settings.OPENAI_API_KEY,
        )
        self.model = self.settings.LLM_MODEL

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        """Generates a text completion using the configured OpenAI-compatible backend."""
        target_model = model or self.model
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            logger.debug(
                "Calling LLM endpoint at %s with model %s",
                self.settings.OPENAI_BASE_URL,
                target_model,
            )
            response = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            choice = response.choices[0]
            return choice.message.content or ""
        except Exception as e:
            logger.error("LLM completion failed: %s", e)
            raise


_llm_service: LLMService | None = None


def get_llm_service(settings: Settings = Depends(get_settings)) -> LLMService:
    """Dependency provider / singleton accessor for LLMService."""
    global _llm_service
    if _llm_service is None or settings is not None:
        _llm_service = LLMService(settings=settings)
    return _llm_service
