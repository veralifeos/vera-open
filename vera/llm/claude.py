"""ClaudeProvider — wrapper Anthropic API com retry tenacity."""

import json
import logging
import os

from anthropic import Anthropic, APIConnectionError, RateLimitError
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
    "wait": wait_exponential(multiplier=2, min=2, max=30),
    "retry": retry_if_exception_type((APIConnectionError, RateLimitError)),
    "reraise": True,
}


class ClaudeProvider(LLMProvider):
    """Provider Claude via Anthropic API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
    ):
        self._model = model
        key = api_key or os.environ.get(api_key_env, "")
        if not key:
            raise ValueError(
                f"API key Anthropic não encontrada. Defina '{api_key_env}' "
                "ou passe api_key diretamente."
            )
        self._client = Anthropic(api_key=key)

    @retry(**_RETRY_KWARGS)
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Gera texto via Claude."""
        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()

    @retry(**_RETRY_KWARGS)
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        max_tokens: int = 1000,
    ) -> dict:
        """Gera resposta JSON estruturada via Claude."""
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        full_prompt = (
            f"{user_prompt}\n\nResponda APENAS com JSON válido no seguinte schema:\n{schema_str}"
        )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": full_prompt}],
        )

        text = message.content[0].text.strip()

        # Tenta extrair JSON do texto
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        return json.loads(text)
