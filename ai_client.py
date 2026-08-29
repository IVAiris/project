import os
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_MODEL_URI = os.getenv("YANDEX_MODEL_URI")
YANDEX_BASE_URL = os.getenv("YANDEX_BASE_URL")
YANDEX_TEMPERATURE = float(os.getenv("YANDEX_TEMPERATURE", "0.4"))
YANDEX_MAX_TOKENS = int(os.getenv("YANDEX_MAX_TOKENS", "10000"))

_client = openai.OpenAI(
    api_key=YANDEX_API_KEY,
    base_url=YANDEX_BASE_URL,
    project=YANDEX_FOLDER_ID,
)


class AIStudioError(Exception):
    """Сбой вызова AI Studio API (сеть, таймаут, квота, ключ)."""


def call_model(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    """Вызывает модель через chat.completions.create и возвращает полный
    объект message (с .content и .tool_calls), а не только текст ответа."""
    try:
        kwargs: dict[str, Any] = {
            "model": YANDEX_MODEL_URI,
            "messages": messages,
            "temperature": YANDEX_TEMPERATURE,
            "max_tokens": YANDEX_MAX_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = _client.chat.completions.create(**kwargs)
        return response.choices[0].message
    except Exception as exc:
        raise AIStudioError(type(exc).__name__) from exc
