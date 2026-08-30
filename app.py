import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bot_flow
import db

PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static"

db.init_db()

app = FastAPI()

SESSIONS: dict[str, dict] = {}

AI_UNAVAILABLE_REPLY = (
    "Сейчас ИИ-консультант временно недоступен. Пожалуйста, воспользуйтесь "
    "меню услуг или попробуйте повторить ввод через пару минут."
)
AI_UNAVAILABLE_BUTTONS = [
    {"label": "Повторить ввод", "value": "ai"},
    {"label": "Вернуться на предыдущий экран", "value": "services"},
]

FAQ_SERVICE_HOWTO = (
    "Через кнопку «Получить услугу» на карточке — описать суть вопроса и "
    "оставить контакт."
)
FAQ_SERVICE_DOCS = {
    "contracts": (
        "Проект договора и Лист согласования — через папку «Для юридической "
        "службы» на диске P:\\, не через бота."
    ),
    "pdn": "Документы не требуются — опишите вопрос или ситуацию в диалоге.",
    "deals": (
        "Пояснительную записку и проект договора — через папку «Для "
        "юридической службы» на диске P:\\, не через бота."
    ),
}


class ChatRequest(BaseModel):
    session_id: str | None = None
    input: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    buttons: list[dict]
    is_error: bool = False
    faq: list[dict] | None = None
    mode: str


def _new_session() -> dict:
    return {"mode": "main_menu", "flow_state": None}


def _get_session(session_id: str | None) -> tuple[str, dict]:
    if session_id and session_id in SESSIONS:
        return session_id, SESSIONS[session_id]
    new_id = uuid.uuid4().hex
    session = _new_session()
    SESSIONS[new_id] = session
    return new_id, session


def _render_services() -> tuple[str, list[dict]]:
    services = bot_flow.get_services()
    lines = ["Здравствуйте! Я бот ЮрСправочника. Чем могу помочь?", ""]
    for service in services:
        lines.append(f'— {service["name"]}: {service["description"]}')
    reply = "\n".join(lines)
    buttons = [
        {"label": service["short_name"], "value": f'service:{service["key"]}'}
        for service in services
    ]
    buttons.append({"label": "Перейти к ИИ-консультанту", "value": "ai"})
    return reply, buttons


def _render_service_card(key: str) -> tuple[str, list[dict]]:
    service = bot_flow.get_service_card(key)
    reply = (
        f'{service["name"]}\n\n'
        f'Регламентный срок: {service["deadline"]}\n'
        f'Ожидаемый результат: {service["result"]}'
    )
    buttons = [
        {"label": "Получить услугу", "value": f"lead:{key}"},
        {"label": "Вернуться на предыдущий экран", "value": "services"},
    ]
    return reply, buttons


def _render_faq() -> tuple[str, list[dict], list[dict]]:
    items = []
    for service in bot_flow.get_services():
        body = (
            f'Название услуги: {service["name"]}\n'
            f'Сроки предоставления результата: {service["deadline"]}\n'
            f"Как подать заявку: {FAQ_SERVICE_HOWTO}\n"
            f'Что представить: {FAQ_SERVICE_DOCS[service["key"]]}'
        )
        items.append({"title": service["short_name"], "body": body})

    rules = bot_flow.get_faq()["Правила и контакты"]
    rules_body = "\n\n".join(f"{question}\n{answer}" for question, answer in rules)
    items.append({"title": "Правила и контакты", "body": rules_body})

    reply = "FAQ — выберите раздел ниже."
    buttons = [{"label": "Вернуться на предыдущий экран", "value": "services"}]
    return reply, buttons, items


def _buttons_for_lead_step(step: str | None) -> list[dict]:
    if step == "lead_confirm":
        return [
            {"label": "Оставить заявку", "value": "submit"},
            {"label": "Уточнить вопрос", "value": "refine"},
            {"label": "Вернуться на предыдущий экран", "value": "back"},
        ]
    return []


def _handle_main_menu(
    session: dict, session_id: str, user_input: str
) -> tuple[str, list[dict], bool, list[dict] | None]:
    if user_input == "services":
        reply, buttons = _render_services()
        return reply, buttons, False, None
    if user_input.startswith("service:"):
        key = user_input.split(":", 1)[1]
        try:
            reply, buttons = _render_service_card(key)
            return reply, buttons, False, None
        except ValueError:
            return "Неизвестная услуга.", [], True, None
    if user_input == "faq":
        reply, buttons, items = _render_faq()
        return reply, buttons, False, items
    if user_input == "lead":
        session["mode"] = "lead_flow"
        session["flow_state"] = bot_flow.start_lead_flow(None)
        buttons = [
            {"label": service["short_name"], "value": service["key"]}
            for service in bot_flow.get_services()
        ]
        return "Выберите услугу.", buttons, False, None
    if user_input.startswith("lead:"):
        key = user_input.split(":", 1)[1]
        try:
            session["flow_state"] = bot_flow.start_lead_flow(key)
        except ValueError:
            return "Неизвестная услуга.", [], True, None
        session["mode"] = "lead_flow"
        return "Опишите суть вопроса.", [], False, None
    if user_input == "feedback":
        session["mode"] = "feedback_flow"
        session["flow_state"] = bot_flow.start_feedback_flow()
        return "Как к Вам обращаться?", [], False, None
    if user_input == "ai":
        return AI_UNAVAILABLE_REPLY, AI_UNAVAILABLE_BUTTONS, True, None
    return bot_flow.handle_unknown_input(), [], False, None


def _handle_lead_flow(
    session: dict, session_id: str, user_input: str
) -> tuple[str, list[dict], bool, None]:
    old_step = session["flow_state"]["step"]
    new_state, reply = bot_flow.handle_lead_input(session["flow_state"], session_id, user_input)
    session["flow_state"] = new_state
    is_error = new_state["step"] == old_step
    if new_state["step"] is None:
        session["mode"] = "main_menu"
        return reply, [], is_error, None
    return reply, _buttons_for_lead_step(new_state["step"]), is_error, None


def _handle_feedback_flow(
    session: dict, session_id: str, user_input: str
) -> tuple[str, list[dict], bool, None]:
    old_step = session["flow_state"]["step"]
    new_state, reply = bot_flow.handle_feedback_input(session["flow_state"], session_id, user_input)
    session["flow_state"] = new_state
    is_error = new_state["step"] == old_step
    if new_state["step"] is None:
        session["mode"] = "main_menu"
        return reply, [], is_error, None
    return reply, [], is_error, None


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id, session = _get_session(request.session_id)

    if session["mode"] == "lead_flow":
        reply, buttons, is_error, faq = _handle_lead_flow(session, session_id, request.input)
    elif session["mode"] == "feedback_flow":
        reply, buttons, is_error, faq = _handle_feedback_flow(session, session_id, request.input)
    else:
        reply, buttons, is_error, faq = _handle_main_menu(session, session_id, request.input)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        buttons=buttons,
        is_error=is_error,
        faq=faq,
        mode=session["mode"],
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
