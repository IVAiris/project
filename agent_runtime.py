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
}


class ToolError(Exception):
    """Ошибка вызова инструмента или разбора его аргументов."""


import agent.tools as agent_tools

TOOL_ARGUMENT_SPECS: dict[str, tuple[set[str], set[str]]] = {
    "search_knowledge": ({"query"}, set()),
    "read_knowledge_file": ({"filename"}, set()),
    "prepare_lead_draft": ({"service", "problem_text", "agent_summary"}, {"missing_info"}),
}


def _require_arguments(name: str, arguments: dict[str, Any]) -> None:
    required, optional = TOOL_ARGUMENT_SPECS[name]
    provided = set(arguments)

    missing = required - provided
    if missing:
        raise ToolError(f"Не хватает аргументов tool `{name}`: {', '.join(sorted(missing))}.")

    extra = provided - required - optional
    if extra:
        raise ToolError(f"Лишние аргументы tool `{name}`: {', '.join(sorted(extra))}.")


def call_tool(
    name: str,
    arguments: dict[str, Any],
    session_id: str,
    session: dict[str, Any],
) -> Any:
    if name not in KNOWN_TOOLS:
        raise ToolError(f"Неизвестный tool: {name}")

    _require_arguments(name, arguments)

    if name == "search_knowledge":
        return agent_tools.search_knowledge(arguments["query"])
    if name == "read_knowledge_file":
        return agent_tools.read_knowledge_file(arguments["filename"])
    if name == "prepare_lead_draft":
        return agent_tools.prepare_lead_draft(
            session,
            arguments["service"],
            arguments["problem_text"],
            arguments["agent_summary"],
            arguments.get("missing_info"),
        )

    raise ToolError(f"Tool `{name}` не имеет диспетчеризации.")


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
    session_id: str,
    session: dict[str, Any],
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
                result = call_tool(tool_name, arguments, session_id, session)
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
        user_task="Расскажи, какие условия обязательно должны быть в договоре?",
        system_prompt=system_prompt,
        session_id="selftest",
        session={},
        tools=agent_tools.TOOL_SCHEMAS,
    )
    print(f"[final] {answer}")
