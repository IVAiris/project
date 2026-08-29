import json
from pathlib import Path
from typing import Any

from ai_client import call_model

PROJECT_ROOT = Path(__file__).resolve().parent
MAX_STEPS = 6

KNOWN_TOOLS = {
    "search_knowledge",
    "read_knowledge_file",
    "prepare_lead_draft",
    "save_confirmed_lead",
}


class ToolError(Exception):
    """Ошибка вызова инструмента или разбора его аргументов."""


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Заглушка диспетчера tools. Реальные реализации появятся в фазе
    «Безопасные tools» (agent/tools.py). Whitelist уже проверяется здесь."""
    if name not in KNOWN_TOOLS:
        raise ToolError(f"Неизвестный tool: {name}")
    raise NotImplementedError(f"Tool '{name}' ещё не реализован (следующая фаза).")


def _get_messages(
    system_prompt: str,
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if conversation_history is None:
        return [{"role": "system", "content": system_prompt}]

    if not conversation_history:
        conversation_history.append({"role": "system", "content": system_prompt})
    elif conversation_history[0].get("role") != "system":
        conversation_history.insert(0, {"role": "system", "content": system_prompt})

    return conversation_history


def _tool_call_to_dict(tool_call: Any) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.content,
    }

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        result["tool_calls"] = [_tool_call_to_dict(tool_call) for tool_call in tool_calls]

    return result


def _parse_arguments(raw_arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ToolError("Модель вернула аргументы tool не в JSON.") from exc

    if not isinstance(parsed, dict):
        raise ToolError("Аргументы tool должны быть JSON-объектом.")

    return parsed


def run_agent(
    user_task: str,
    system_prompt: str,
    conversation_history: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    print(f"[task] {user_task}")

    messages = _get_messages(system_prompt, conversation_history)
    messages.append({"role": "user", "content": user_task})

    for step_number in range(1, MAX_STEPS + 1):
        print(f"[loop] step {step_number}")

        message = call_model(messages, tools=tools)
        messages.append(_assistant_message_to_dict(message))

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content or ""

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            print(f"[tool] selected: {tool_name}")

            try:
                arguments = _parse_arguments(tool_call.function.arguments)
                print(f"[tool] arguments: {json.dumps(arguments, ensure_ascii=True)}")
                result = call_tool(tool_name, arguments)
                content = json.dumps(result, ensure_ascii=True)
            except (ToolError, NotImplementedError) as exc:
                print(f"[refusal] {exc}")
                content = json.dumps({"error": str(exc)}, ensure_ascii=True)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": content,
                }
            )

    print(f"[refusal] Достигнут MAX_STEPS={MAX_STEPS}, остановка.")
    return "Не удалось завершить обработку запроса за отведённое число шагов."


if __name__ == "__main__":
    soul_path = PROJECT_ROOT / "agent" / "soul.md"
    system_prompt = soul_path.read_text(encoding="utf-8")

    answer = run_agent(
        user_task="Ответь одним словом: тест",
        system_prompt=system_prompt,
    )
    print(f"[final] {answer}")
