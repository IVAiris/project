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


def _back_button(value: str = "services") -> dict:
    # is_back — фронтенд ограничивает ширину этой кнопки ~1/3 строки
    # (как если бы в ряду было 3 равные кнопки), а не растягивает её на
    # всю доступную ширину наравне с остальными (см. static/style.css).
    return {"label": "Вернуться на предыдущий экран", "value": value, "is_back": True}


AI_UNAVAILABLE_REPLY = (
    "Сейчас ИИ-консультант временно недоступен. Пожалуйста, воспользуйтесь "
    "меню услуг или попробуйте повторить ввод через пару минут."
)
AI_UNAVAILABLE_BUTTONS = [
    {"label": "Повторить ввод", "value": "ai"},
    _back_button("services"),
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
    payload: dict[str, str] | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    buttons: list[dict]
    is_error: bool = False
    faq: list[dict] | None = None
    mode: str
    form: str | None = None
    form_errors: dict[str, str] | None = None


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
    # Отдельная широкая кнопка (docs/maket/, Страница 1) — не в общем ряду услуг.
    buttons.append({"label": "Перейти к ИИ-консультанту", "value": "ai", "wide": True})
    return reply, buttons


def _service_card_buttons(key: str, active: str | None) -> list[dict]:
    return [
        _back_button("services"),
        {
            "label": "Регламентный срок",
            "value": f"service:{key}:deadline",
            "is_active": active == "deadline",
        },
        {
            "label": "Ожидаемый результат",
            "value": f"service:{key}:result",
            "is_active": active == "result",
        },
        {"label": "Получить услугу", "value": f"lead:{key}"},
    ]


def _render_service_card(key: str, tab: str | None) -> tuple[str, list[dict]]:
    service = bot_flow.get_service_card(key)  # ValueError на неизвестном key — обрабатывает вызывающий код
    if tab == "deadline":
        reply = f'Регламентный срок: {service["deadline"]}'
    elif tab == "result":
        reply = f'Ожидаемый результат: {service["result"]}'
    else:
        reply = f'{service["name"]}\n\n{service["description"]}'
    return reply, _service_card_buttons(key, tab)


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
    buttons = [_back_button("services")]
    return reply, buttons, items


def _buttons_for_lead_step(step: str | None) -> list[dict]:
    # "Вернуться на предыдущий экран" доступна на каждом шаге визарда (docs/maket/),
    # не только на финальном подтверждении — полный сброс через уже единый токен "back".
    if step == "lead_confirm":
        return [
            {"label": "Оставить заявку", "value": "submit"},
            {"label": "Уточнить вопрос", "value": "refine"},
            _back_button("back"),
        ]
    return [_back_button("back")]


def _handle_main_menu(
    session: dict, session_id: str, user_input: str
) -> tuple[str, list[dict], bool, list[dict] | None, str | None]:
    if user_input == "services":
        reply, buttons = _render_services()
        return reply, buttons, False, None, None
    if user_input.startswith("service:"):
        parts = user_input.split(":")
        key = parts[1]
        tab = parts[2] if len(parts) > 2 else None
        try:
            reply, buttons = _render_service_card(key, tab)
            return reply, buttons, False, None, None
        except ValueError:
            return "Неизвестная услуга.", [], True, None, None
    if user_input == "faq":
        reply, buttons, items = _render_faq()
        return reply, buttons, False, items, None
    if user_input == "lead":
        session["mode"] = "lead_flow"
        session["flow_state"] = bot_flow.start_lead_flow(None)
        buttons = [
            {"label": service["short_name"], "value": service["key"]}
            for service in bot_flow.get_services()
        ]
        buttons.append(_back_button("back"))
        return "Выберите услугу.", buttons, False, None, None
    if user_input.startswith("lead:"):
        key = user_input.split(":", 1)[1]
        try:
            session["flow_state"] = bot_flow.start_lead_flow(key)
        except ValueError:
            return "Неизвестная услуга.", [], True, None, None
        session["mode"] = "lead_flow"
        return "Опишите суть вопроса.", _buttons_for_lead_step("lead_problem"), False, None, None
    if user_input == "feedback":
        return (
            "Здесь можно оставить обратную связь о работе сервиса: указать на "
            "ошибки, написать предложения и пожелания и даже похвалить. Для "
            "этого заполните форму.",
            [],
            False,
            None,
            "feedback",
        )
    if user_input == "ai":
        return AI_UNAVAILABLE_REPLY, AI_UNAVAILABLE_BUTTONS, True, None, None
    return bot_flow.handle_unknown_input(), [], False, None, None


def _handle_lead_flow(
    session: dict, session_id: str, user_input: str
) -> tuple[str, list[dict], bool, None, None]:
    old_step = session["flow_state"]["step"]
    new_state, reply = bot_flow.handle_lead_input(session["flow_state"], session_id, user_input)
    session["flow_state"] = new_state
    is_error = new_state["step"] == old_step
    if new_state["step"] is None:
        session["mode"] = "main_menu"
        return reply, [], is_error, None, None
    return reply, _buttons_for_lead_step(new_state["step"]), is_error, None, None


def _handle_feedback_submit(
    payload: dict[str, str] | None, session_id: str
) -> tuple[str, list[dict], bool, None, str, dict[str, str] | None]:
    payload = payload or {}
    ok, errors = bot_flow.submit_feedback(
        session_id=session_id,
        contact_name=payload.get("contact_name", ""),
        contact_email=payload.get("contact_email", ""),
        message_text=payload.get("message_text", ""),
    )
    if not ok:
        return "Проверки не пройдены.", [], True, None, "feedback", errors
    return "Ваш отзыв направлен и будет рассмотрен.", [], False, None, None, None


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id, session = _get_session(request.session_id)
    form_errors = None

    if request.input == "feedback_submit":
        reply, buttons, is_error, faq, form, form_errors = _handle_feedback_submit(
            request.payload, session_id
        )
    elif session["mode"] == "lead_flow":
        reply, buttons, is_error, faq, form = _handle_lead_flow(session, session_id, request.input)
    else:
        reply, buttons, is_error, faq, form = _handle_main_menu(session, session_id, request.input)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        buttons=buttons,
        is_error=is_error,
        faq=faq,
        mode=session["mode"],
        form=form,
        form_errors=form_errors,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
