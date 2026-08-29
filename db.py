import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data" / "bot.sqlite3"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                service TEXT NOT NULL,
                contact TEXT NOT NULL,
                problem_text TEXT NOT NULL,
                agent_summary TEXT,
                missing_info TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                contact_email TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_lead(
    session_id: str,
    source: str,
    service: str,
    contact: str,
    problem_text: str,
    agent_summary: str | None,
    missing_info: str | None,
    db_path: Path = DB_PATH,
) -> int:
    status = "needs_clarification" if missing_info else "new"
    created_at = datetime.now().isoformat()

    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO leads (
                session_id, source, service, contact, problem_text,
                agent_summary, missing_info, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                source,
                service,
                contact,
                problem_text,
                agent_summary,
                missing_info,
                status,
                created_at,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_feedback(
    session_id: str,
    contact_name: str,
    contact_email: str,
    message_text: str,
    db_path: Path = DB_PATH,
) -> int:
    created_at = datetime.now().isoformat()

    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO feedback (
                session_id, contact_name, contact_email, message_text, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, contact_name, contact_email, message_text, created_at),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


if __name__ == "__main__":
    TEST_DB_PATH = PROJECT_ROOT / "data" / "_selftest.sqlite3"

    try:
        init_db(TEST_DB_PATH)
        init_db(TEST_DB_PATH)  # повторный вызов не должен падать

        lead_id = insert_lead(
            session_id="selftest-session",
            source="bot_flow",
            service="Согласование договоров",
            contact="Тест Тестов | test@example.com",
            problem_text="Тестовый вопрос для self-test.",
            agent_summary=None,
            missing_info=None,
            db_path=TEST_DB_PATH,
        )
        feedback_id = insert_feedback(
            session_id="selftest-session",
            contact_name="Тест Тестов",
            contact_email="test@example.com",
            message_text="Тестовый отзыв для self-test.",
            db_path=TEST_DB_PATH,
        )

        conn = get_connection(TEST_DB_PATH)
        try:
            lead_row = conn.execute(
                "SELECT status FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()
            leads_count = conn.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
            feedback_count = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback"
            ).fetchone()["n"]
        finally:
            conn.close()

        print(f"[selftest] lead id={lead_id} status={lead_row['status']}")
        print(f"[selftest] feedback id={feedback_id}")
        print(f"[selftest] leads count={leads_count} feedback count={feedback_count}")
    finally:
        TEST_DB_PATH.unlink(missing_ok=True)
