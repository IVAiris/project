import re
from pathlib import Path

import db

PROJECT_ROOT = Path(__file__).resolve().parent

SERVICES = [
    {
        "key": "contracts",
        "name": "Консультация о порядке согласования договоров",
        "short_name": "Согласование договоров",
        "description": (
            "Порядок согласования договора в компании, обязательные "
            "(существенные) условия, которые должны быть в документе"
        ),
        "deadline": "не более 1 рабочего дня на каждом этапе визирования",
        "result": "Разъяснение порядка согласования и перечня обязательных условий договора",
    },
    {
        "key": "pdn",
        "name": "Консультация об обработке персональных данных (по 152-ФЗ)",
        "short_name": "152-ФЗ (персональные данные)",
        "description": "Разъяснения по 152-ФЗ о персональных данных в понятной формулировке",
        "deadline": "до 3 рабочих дней",
        "result": "Ответ с цитатой нормы закона и пояснением простыми словами",
    },
    {
        "key": "deals",
        "name": "Получение корпоративного одобрения сделки",
        "short_name": "Согласование сделок",
        "description": (
            "Когда сделка подлежит согласованию по корпоративным документам, "
            "что готовить для принятия решения"
        ),
        "deadline": "до 14 рабочих дней",
        "result": "Разъяснение, требуется ли корпоративное согласование, и что подготовить",
    },
]

_SERVICES_BY_KEY = {service["key"]: service for service in SERVICES}

FAQ_CATEGORIES = {
    "Услуги": [
        (
            "Какие условия обязательно должны быть в договоре?",
            "Предмет, цена с НДС, сроки исполнения, ответственность сторон "
            "(включая конфиденциальность), форс-мажор, претензионный порядок, "
            "порядок изменения и расторжения, срок действия договора.",
        ),
        (
            "Нужно ли согласие сотрудника на передачу его данных подрядчику?",
            "Да, по общему правилу требуется согласие субъекта персональных "
            "данных на поручение обработки другому лицу (ст. 6 152-ФЗ).",
        ),
    ],
    "SLA, сроки и приоритет обращения": [
        (
            "Сколько времени бот отвечает на вопрос?",
            "До 2 минут — зависит от сложности обращения и типа консультации.",
        ),
        (
            "Что делать, если бот не может ответить на вопрос?",
            "Обращение эскалируется на консультацию к юристу; бот не заменяет "
            "юридическое заключение по нестандартным ситуациям.",
        ),
    ],
    "Формат работы": [
        ("В каком канале доступен бот?", "Внутренний портал."),
        (
            "Бот сам согласовывает договор или сделку?",
            "Нет, бот только консультирует по процедуре, условиям и нормам "
            "закона — решение принимают ответственные сотрудники и "
            "уполномоченные органы.",
        ),
    ],
    "Правила и контакты": [
        (
            "Можно ли использовать ответ бота как юридическое заключение?",
            "Нет, бот разъясняет норму закона и общий порядок, но не "
            "подменяет консультацию юриста при спорных ситуациях.",
        ),
        (
            "К кому обращаться, если ответ бота требует уточнения?",
            "Работник юридического отдела — Иванов Иван Иванович. Написать "
            "письмо или направить сообщение в «Обратной связи».",
        ),
    ],
}

_MAIN_MENU_HINT = (
    "Не удалось распознать запрос. Выберите один из режимов: «Услуги», "
    "«FAQ», «Оставить заявку», «ИИ-консультант», «Обратная связь»."
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_services() -> list[dict]:
    return SERVICES


def get_service_card(service_key: str) -> dict:
    if service_key not in _SERVICES_BY_KEY:
        raise ValueError(f"Неизвестная услуга: {service_key}")
    return _SERVICES_BY_KEY[service_key]


def get_faq() -> dict:
    return FAQ_CATEGORIES


def handle_unknown_input() -> str:
    return _MAIN_MENU_HINT


def _empty_data() -> dict:
    return {
        "service": None,
        "problem_text": None,
        "contact_name": None,
        "contact_email": None,
        "feedback_message": None,
    }


def _new_state(step: str | None) -> dict:
    return {"step": step, "data": _empty_data()}


def start_lead_flow(service_key: str | None) -> dict:
    if service_key is not None:
        get_service_card(service_key)  # выбросит ValueError на неизвестном ключе
        state = _new_state("lead_problem")
        state["data"]["service"] = service_key
        return state
    return _new_state("lead_service")


def _lead_confirmation_message(state: dict, lead_id: int) -> str:
    service = _SERVICES_BY_KEY[state["data"]["service"]]["name"]
    return (
        f'От: {state["data"]["contact_name"]} | {state["data"]["contact_email"]}\n'
        f"Тема: {service}\n"
        f'Заявка на предоставление консультации по вопросу: {state["data"]["problem_text"]}\n\n'
        f"Ваша заявка направлена в Юридическую службу. Ей присвоен номер {lead_id}."
    )


def handle_lead_input(state: dict, session_id: str, user_input: str) -> tuple[dict, str]:
    step = state["step"]
    data = dict(state["data"])  # копия — не мутируем входной state (контракт: чистая функция)

    if step == "lead_service":
        try:
            get_service_card(user_input)
        except ValueError:
            return state, "Пожалуйста, выберите одну из предложенных услуг."
        data["service"] = user_input
        return {"step": "lead_problem", "data": data}, "Опишите суть вопроса."

    if step == "lead_problem":
        if not user_input.strip():
            return state, "Описание задачи не может быть пустым. Опишите суть вопроса."
        data["problem_text"] = user_input.strip()
        if data["contact_name"] and data["contact_email"]:
            # Возврат сюда был через "refine" — контакт уже есть, сразу к подтверждению.
            new_state = {"step": "lead_confirm", "data": data}
            return new_state, _build_summary(new_state)
        return {"step": "lead_name", "data": data}, "Как к Вам обращаться?"

    if step == "lead_name":
        if len(user_input.strip()) < 2:
            return state, "Имя должно содержать не менее 2 символов. Как к Вам обращаться?"
        data["contact_name"] = user_input.strip()
        return {"step": "lead_email", "data": data}, "Укажите корпоративную почту."

    if step == "lead_email":
        if not _EMAIL_RE.match(user_input.strip()):
            return state, "Некорректный формат почты. Укажите корпоративную почту."
        data["contact_email"] = user_input.strip()
        new_state = {"step": "lead_confirm", "data": data}
        return new_state, _build_summary(new_state)

    if step == "lead_confirm":
        if user_input == "submit":
            contact = f'{data["contact_name"]} | {data["contact_email"]}'
            lead_id = db.insert_lead(
                session_id=session_id,
                source="bot_flow",
                service=data["service"],
                contact=contact,
                problem_text=data["problem_text"],
                agent_summary=None,
                missing_info=None,
            )
            message = _lead_confirmation_message(state, lead_id)
            return _new_state(None), message
        if user_input == "refine":
            data["problem_text"] = None
            return {"step": "lead_problem", "data": data}, "Опишите суть вопроса ещё раз."
        if user_input == "back":
            return _new_state(None), "Заявка отменена. Черновик не сохранён."
        return state, "Выберите одно из действий: «Оставить заявку», «Уточнить вопрос», «Вернуться на предыдущий экран»."

    return state, handle_unknown_input()


def _build_summary(state: dict) -> str:
    data = state["data"]
    service = _SERVICES_BY_KEY[data["service"]]["name"]
    return (
        f'От: {data["contact_name"]} | {data["contact_email"]}\n'
        f"Тема: {service}\n"
        f'Заявка на предоставление консультации по вопросу: {data["problem_text"]}'
    )


def start_feedback_flow() -> dict:
    return _new_state("feedback_name")


def handle_feedback_input(state: dict, session_id: str, user_input: str) -> tuple[dict, str]:
    step = state["step"]
    data = dict(state["data"])  # копия — не мутируем входной state (контракт: чистая функция)

    if step == "feedback_name":
        if len(user_input.strip()) < 2:
            return state, "Имя должно содержать не менее 2 символов. Как к Вам обращаться?"
        data["contact_name"] = user_input.strip()
        return {"step": "feedback_email", "data": data}, "Укажите эл. почту."

    if step == "feedback_email":
        if not _EMAIL_RE.match(user_input.strip()):
            return state, "Некорректный формат почты. Укажите эл. почту."
        data["contact_email"] = user_input.strip()
        return {"step": "feedback_message", "data": data}, "Оставьте Ваш отзыв."

    if step == "feedback_message":
        if not user_input.strip():
            return state, "Отзыв не может быть пустым. Оставьте Ваш отзыв."
        data["feedback_message"] = user_input.strip()
        db.insert_feedback(
            session_id=session_id,
            contact_name=data["contact_name"],
            contact_email=data["contact_email"],
            message_text=data["feedback_message"],
        )
        return _new_state(None), "Ваш отзыв направлен и будет рассмотрен."

    return state, handle_unknown_input()


if __name__ == "__main__":
    TEST_DB_PATH = PROJECT_ROOT / "data" / "_selftest_bot_flow.sqlite3"

    original_insert_lead = db.insert_lead
    original_insert_feedback = db.insert_feedback

    def insert_lead(*args, **kwargs):
        kwargs["db_path"] = TEST_DB_PATH
        return original_insert_lead(*args, **kwargs)

    def insert_feedback(*args, **kwargs):
        kwargs["db_path"] = TEST_DB_PATH
        return original_insert_feedback(*args, **kwargs)

    db.insert_lead = insert_lead
    db.insert_feedback = insert_feedback

    try:
        db.init_db(TEST_DB_PATH)

        print("[selftest] services:", [s["key"] for s in get_services()])
        print("[selftest] faq categories:", list(get_faq().keys()))
        print("[selftest] unknown input:", handle_unknown_input())

        # Happy path: с предвыбором услуги через карточку
        state = start_lead_flow("contracts")
        state, _ = handle_lead_input(state, "s1", "Нужно ли согласовывать доп. соглашение?")
        state, _ = handle_lead_input(state, "s1", "Тест Тестов")
        state, msg = handle_lead_input(state, "s1", "test@example.com")
        state, msg = handle_lead_input(state, "s1", "submit")
        print("[selftest] lead submit:", msg.splitlines()[-1])
        assert state["step"] is None and state["data"]["service"] is None

        # back: полный сброс без сохранения
        state = start_lead_flow(None)
        state, _ = handle_lead_input(state, "s2", "pdn")
        state, _ = handle_lead_input(state, "s2", "Вопрос про согласие")
        state, _ = handle_lead_input(state, "s2", "Имя Имя")
        state, _ = handle_lead_input(state, "s2", "imya@example.com")
        state, msg = handle_lead_input(state, "s2", "back")
        print("[selftest] lead back:", msg)
        assert state["step"] is None and state["data"]["service"] is None

        # refine: меняется только описание задачи
        state = start_lead_flow("deals")
        state, _ = handle_lead_input(state, "s3", "Старое описание")
        state, _ = handle_lead_input(state, "s3", "Другое Имя")
        state, _ = handle_lead_input(state, "s3", "another@example.com")
        state, msg = handle_lead_input(state, "s3", "refine")
        assert state["step"] == "lead_problem"
        assert state["data"]["contact_name"] == "Другое Имя"
        state, _ = handle_lead_input(state, "s3", "Новое описание")
        state, _ = handle_lead_input(state, "s3", "submit")
        print("[selftest] lead refine+submit:", state["step"] is None)

        # feedback: полный путь
        state = start_feedback_flow()
        state, _ = handle_feedback_input(state, "s4", "Тест Тестов")
        state, _ = handle_feedback_input(state, "s4", "test@example.com")
        state, msg = handle_feedback_input(state, "s4", "Отличный бот!")
        print("[selftest] feedback:", msg)
        assert state["step"] is None

        conn = db.get_connection(TEST_DB_PATH)
        try:
            leads_count = conn.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
            feedback_count = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
        finally:
            conn.close()
        print(f"[selftest] leads count={leads_count} feedback count={feedback_count}")
        assert leads_count == 2  # happy path + refine path; "back" не создал запись
        assert feedback_count == 1
    finally:
        db.insert_lead = original_insert_lead
        db.insert_feedback = original_insert_feedback
        TEST_DB_PATH.unlink(missing_ok=True)
