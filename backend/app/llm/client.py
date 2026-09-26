"""LLM abstraction — the app depends on LLMClient.generate_structured(...),
never on one vendor's SDK.

First implementation: OpenAI-compatible chat completions (OpenRouter,
OpenAI, Ollama, ...). Structured output is enforced by asking for strict
JSON and validating against a Pydantic model; malformed output raises.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("backend.llm.client")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Provider failure (network, HTTP, malformed output)."""


class LLMUnconfiguredError(LLMError):
    """No LLM provider configured (LLM_API_KEY / LLM_MODEL missing)."""


class LLMClient(ABC):
    """Provider-agnostic interface used by guidance and report extraction services."""

    @abstractmethod
    def generate_structured(self, system: str, user: str, schema: type[T]) -> T:
        """Generate a response validated against the Pydantic schema."""

    @abstractmethod
    def generate_structured_multimodal(
        self,
        system: str,
        user_prompt: str,
        images_base64: list[dict[str, str]],
        schema: type[T],
    ) -> T:
        """Generate a structured response given text prompt and images (data URIs / base64)."""



class OpenAICompatibleLLM(LLMClient):
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_base = (api_base or settings.llm_api_base).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.temperature = (
            settings.llm_temperature if temperature is None else temperature
        )
        self.timeout = timeout or settings.llm_timeout_seconds

    def generate_structured(self, system: str, user: str, schema: type[T]) -> T:
        if not self.api_key or not self.model:
            raise LLMUnconfiguredError(
                "LLM provider not configured (set LLM_API_KEY and LLM_MODEL)."
            )
        content = self._chat(system, user)
        return self._validate(content, schema)

    def generate_structured_multimodal(
        self,
        system: str,
        user_prompt: str,
        images_base64: list[dict[str, str]],
        schema: type[T],
    ) -> T:
        if not self.api_key or not self.model:
            raise LLMUnconfiguredError(
                "LLM provider not configured (set LLM_API_KEY and LLM_MODEL)."
            )
        content = self._chat_multimodal(system, user_prompt, images_base64)
        return self._validate(content, schema)

    # ------------------------------------------------------------------ #
    def _chat(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        return self._send_request(payload)

    def _chat_multimodal(
        self,
        system: str,
        user_prompt: str,
        images: list[dict[str, str]],
    ) -> str:
        # Build multimodal OpenAI user content parts:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for img in images:
            mime = img.get("mime_type", "image/png")
            b64 = img.get("data", "")
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}",
                },
            })

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        }
        return self._send_request(payload)

    def _send_request(self, payload: dict[str, Any]) -> str:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"LLM provider returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider request failed: {exc}") from exc

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("LLM provider returned malformed JSON.") from exc


    def _validate(self, content: str, schema: type[T]) -> T:
        """Parse the model's JSON and validate. Raises LLMError on garbage."""
        text = content.strip()
        # Tolerate ```json fences some models wrap around JSON.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM output is not valid JSON.") from exc
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LLMError(
                f"LLM output failed schema validation: {exc.errors()[:3]}"
            ) from exc


def get_llm_client() -> LLMClient:
    return OpenAICompatibleLLM()
