from pathlib import Path, PurePosixPath
from typing import Any

import bot_flow
import db
from agent_runtime import ToolError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
ALLOWED_KNOWLEDGE_FILES = {"services.md", "faq.md", "rules.md"}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Ищет подстроку в базе знаний (services.md, faq.md, rules.md) "
                "и возвращает список совпадений с указанием файла и фрагмента текста."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Поисковый запрос — короткое ключевое слово или "
                            "фраза, а не целый вопрос пользователя."
                        ),
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_knowledge_file",
            "description": "Читает полный текст одного файла базы знаний целиком.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "enum": ["services.md", "faq.md", "rules.md"],
                        "description": "Точное имя файла базы знаний.",
                    },
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_lead_draft",
            "description": (
                "Готовит черновик заявки на основе диалога. Не принимает "
                "контакт пользователя и не сохраняет заявку."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "enum": ["contracts", "pdn", "deals"],
                        "description": "Ключ подходящей услуги из каталога.",
                    },
                    "problem_text": {
                        "type": "string",
                        "description": "Краткое описание вопроса пользователя своими словами.",
                    },
                    "agent_summary": {
                        "type": "string",
                        "description": "Краткое резюме того, что уже выяснено в диалоге.",
                    },
                    "missing_info": {
                        "type": "string",
                        "description": (
                            "Сведения, которых не хватило для полного ответа. "
                            "Опустить, если данных достаточно."
                        ),
                    },
                },
                "required": ["service", "problem_text", "agent_summary"],
                "additionalProperties": False,
            },
        },
    },
]


def _validate_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ToolError(f"`{field_name}` должен быть строкой.")

    stripped = value.strip()
    if not stripped:
        raise ToolError(f"`{field_name}` не должен быть пустым.")

    return stripped


def _resolve_knowledge_path(raw_filename: str) -> Path:
    filename = _validate_string(raw_filename, "filename")

    normalized = filename.replace("\\", "/")
    posix_path = PurePosixPath(normalized)

    if posix_path.is_absolute() or ":" in normalized:
        raise ToolError("Абсолютные пути запрещены.")

    parts = [part for part in posix_path.parts if part not in {"", "."}]
    if not parts:
        raise ToolError("Путь не должен быть пустым.")

    if ".." in parts:
        raise ToolError("Выход через `..` запрещён.")

    if len(parts) != 1:
        raise ToolError("Файл должен быть указан именем без подпапок.")

    relative_path = Path(parts[0])
    if relative_path.suffix.lower() != ".md":
        raise ToolError("Разрешены только Markdown-файлы с расширением `.md`.")

    candidate = (KNOWLEDGE_DIR / relative_path).resolve()
    try:
        candidate.relative_to(KNOWLEDGE_DIR)
    except ValueError as exc:
        raise ToolError("Путь должен оставаться внутри `knowledge/`.") from exc

    if candidate.name not in ALLOWED_KNOWLEDGE_FILES:
        raise ToolError(
            f"Файл `{candidate.name}` не входит в разрешённый список: "
            f"{sorted(ALLOWED_KNOWLEDGE_FILES)}."
        )

    return candidate


EXCERPT_RADIUS = 150


def _extract_excerpt(content: str, start: int, end: int, radius: int = EXCERPT_RADIUS) -> str:
    window_start = max(0, start - radius)
    window_end = min(len(content), end + radius)

    if window_start > 0:
        space = content.find(" ", window_start)
        if 0 <= space < start:
            window_start = space + 1

    if window_end < len(content):
        space = content.rfind(" ", end, window_end)
        if space > end:
            window_end = space

    excerpt = content[window_start:window_end].strip()
    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(content) else ""
    return f"{prefix}{excerpt}{suffix}"


def search_knowledge(query: str) -> list[dict[str, str]]:
    normalized_query = _validate_string(query, "query")
    lowered_query = normalized_query.lower()

    matches: list[dict[str, str]] = []
    for filename in sorted(ALLOWED_KNOWLEDGE_FILES):
        content = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        lowered_content = content.lower()
        index = lowered_content.find(lowered_query)
        if index == -1:
            continue

        excerpt = _extract_excerpt(content, index, index + len(normalized_query))
        matches.append({"file": filename, "excerpt": excerpt})

    return matches


def _validate_optional_string(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ToolError(f"`{field_name}` должен быть строкой или отсутствовать.")
    return value.strip()


def prepare_lead_draft(
    session: dict[str, Any],
    service: str,
    problem_text: str,
    agent_summary: str,
    missing_info: str | None = None,
) -> dict[str, Any]:
    service_key = _validate_string(service, "service")
    try:
        bot_flow.get_service_card(service_key)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    draft = {
        "service": service_key,
        "problem_text": _validate_string(problem_text, "problem_text"),
        "agent_summary": _validate_string(agent_summary, "agent_summary"),
        "missing_info": _validate_optional_string(missing_info, "missing_info"),
        "contact": None,
    }

    session["lead_draft"] = draft
    return draft


def save_confirmed_lead(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    draft = session.get("lead_draft")
    if not draft:
        return {"already_sent": True}

    contact = draft.get("contact")
    if not contact:
        raise ToolError("Черновик не готов: не хватает контакта.")

    lead_id = db.insert_lead(
        session_id=session_id,
        source="ai_consultant",
        service=draft["service"],
        contact=contact,
        problem_text=draft["problem_text"],
        agent_summary=draft["agent_summary"],
        missing_info=draft["missing_info"] or None,
    )

    session["lead_draft"] = None
    return {"lead_id": lead_id}


def read_knowledge_file(filename: str) -> dict[str, str]:
    file_path = _resolve_knowledge_path(filename)

    if not file_path.exists():
        raise ToolError(f"Файл не найден: {file_path.name}")
    if not file_path.is_file():
        raise ToolError("Путь должен указывать на файл.")

    return {
        "file": file_path.name,
        "content": file_path.read_text(encoding="utf-8"),
    }


if __name__ == "__main__":
    TEST_DB_PATH = PROJECT_ROOT / "data" / "_selftest_tools.sqlite3"

    original_insert_lead = db.insert_lead

    def insert_lead(*args, **kwargs):
        kwargs["db_path"] = TEST_DB_PATH
        return original_insert_lead(*args, **kwargs)

    db.insert_lead = insert_lead

    try:
        db.init_db(TEST_DB_PATH)

        matches = search_knowledge("форс-мажор")
        print("[selftest] search_knowledge matches:", [m["file"] for m in matches])
        assert matches, "ожидалось хотя бы одно совпадение"

        for filename in sorted(ALLOWED_KNOWLEDGE_FILES):
            result = read_knowledge_file(filename)
            print(f"[selftest] read_knowledge_file({filename}) length:", len(result["content"]))
            assert result["content"]

        session = {}
        draft = prepare_lead_draft(
            session, "pdn", "Нужно ли согласие на обработку данных сотрудника?",
            "Вопрос про согласие на обработку персональных данных", None,
        )
        print("[selftest] prepare_lead_draft:", draft["service"])
        assert session["lead_draft"] is draft

        session["lead_draft"]["contact"] = "Тест Тестов | test@example.com"
        result = save_confirmed_lead("selftest-session", session)
        print("[selftest] save_confirmed_lead:", result)
        assert "lead_id" in result
        assert session["lead_draft"] is None

        repeat = save_confirmed_lead("selftest-session", session)
        print("[selftest] repeat save_confirmed_lead:", repeat)
        assert repeat == {"already_sent": True}

        conn = db.get_connection(TEST_DB_PATH)
        try:
            leads_count = conn.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
        finally:
            conn.close()
        print(f"[selftest] leads count={leads_count}")
        assert leads_count == 1
    finally:
        db.insert_lead = original_insert_lead
        TEST_DB_PATH.unlink(missing_ok=True)
