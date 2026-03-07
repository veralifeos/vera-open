"""OllamaProvider — chamada local via HTTP (localhost:11434)."""

import json
import logging

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from vera.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=10),
    "retry": retry_if_exception_type((aiohttp.ClientError,)),
    "reraise": True,
}


class OllamaProvider(LLMProvider):
    """Provider Ollama para LLMs locais."""

    def __init__(
        self,
        model: str = "llama3.2:3b",
        base_url: str = "http://localhost:11434",
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")

    @retry(**_RETRY_KWARGS)
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Gera texto via Ollama."""
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=120)
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"Ollama erro {resp.status}: {text[:200]}",
                    )
                data = await resp.json()
                return data["message"]["content"].strip()

    @retry(**_RETRY_KWARGS)
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        max_tokens: int = 1000,
    ) -> dict:
        """Gera resposta JSON estruturada via Ollama."""
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        full_prompt = (
            f"{user_prompt}\n\nResponda APENAS com JSON válido no seguinte schema:\n{schema_str}"
        )

        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.3,
            },
        }

        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=120)
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"Ollama erro {resp.status}: {text[:200]}",
                    )
                data = await resp.json()
                text = data["message"]["content"].strip()
                return json.loads(text)
