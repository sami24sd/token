"""لایهٔ ذخیره‌سازی داده روی SQLite (بدون وابستگی بیرونی)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    chat_id       INTEGER PRIMARY KEY,
    user_id       INTEGER,
    full_name     TEXT NOT NULL,
    grade         TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_schedule (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    grade      TEXT NOT NULL,
    weekday    INTEGER NOT NULL,
    period     INTEGER NOT NULL,
    subject    TEXT NOT NULL,
    teacher    TEXT DEFAULT '',
    start_time TEXT DEFAULT '',
    end_time   TEXT DEFAULT '',
    UNIQUE (grade, weekday, period)
);

CREATE TABLE IF NOT EXISTS homework (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grade       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    subject    TEXT NOT NULL,
    title      TEXT NOT NULL,
    score      REAL NOT NULL,
    max_score  REAL NOT NULL DEFAULT 20,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grade         TEXT NOT NULL,
    subject       TEXT NOT NULL,
    question      TEXT NOT NULL,
    options       TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    is_correct INTEGER NOT NULL,
    answered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Student:
    chat_id: int
    user_id: int | None
    full_name: str
    grade: str


def _today_iso() -> str:
    return date.today().isoformat()


class Storage:
    """دسترسی به دیتابیس مدرسه."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if self.db_path.parent and str(self.db_path.parent) != ".":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ KV
    def set_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_state(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def delete_state(self, key: str) -> None:
        self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self._conn.commit()

    # ------------------------------------------------------------ students
    def register_student(
        self, chat_id: int, full_name: str, grade: str, user_id: int | None = None
    ) -> None:
        self._conn.execute(
            "INSERT INTO students(chat_id, user_id, full_name, grade, registered_at) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET full_name = excluded.full_name, "
            "grade = excluded.grade",
            (chat_id, user_id, full_name, grade, datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()

    def get_student(self, chat_id: int) -> Student | None:
        row = self._conn.execute(
            "SELECT * FROM students WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if row is None:
            return None
        return Student(
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            full_name=row["full_name"],
            grade=row["grade"],
        )

    def all_students(self) -> list[Student]:
        rows = self._conn.execute("SELECT * FROM students ORDER BY grade, full_name").fetchall()
        return [
            Student(r["chat_id"], r["user_id"], r["full_name"], r["grade"]) for r in rows
        ]

    def students_of_grade(self, grade: str) -> list[Student]:
        rows = self._conn.execute(
            "SELECT * FROM students WHERE grade = ? ORDER BY full_name", (grade,)
        ).fetchall()
        return [
            Student(r["chat_id"], r["user_id"], r["full_name"], r["grade"]) for r in rows
        ]

    def count_students(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"])

    # ------------------------------------------------------------ schedule
    def add_lesson(
        self,
        grade: str,
        weekday: int,
        period: int,
        subject: str,
        teacher: str = "",
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT INTO weekly_schedule"
            "(grade, weekday, period, subject, teacher, start_time, end_time) "
            "VALUES(?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(grade, weekday, period) DO UPDATE SET subject = excluded.subject, "
            "teacher = excluded.teacher, start_time = excluded.start_time, "
            "end_time = excluded.end_time",
            (grade, weekday, period, subject, teacher, start_time, end_time),
        )
        self._conn.commit()

    def lessons_for(self, grade: str, weekday: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM weekly_schedule WHERE grade = ? AND weekday = ? "
            "ORDER BY period",
            (grade, weekday),
        ).fetchall()

    def week_schedule(self, grade: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM weekly_schedule WHERE grade = ? ORDER BY weekday, period",
            (grade,),
        ).fetchall()

    # ------------------------------------------------------------ homework
    def add_homework(
        self,
        grade: str,
        subject: str,
        title: str,
        due_date: str,
        description: str = "",
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO homework(grade, subject, title, description, due_date, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (grade, subject, title, description, due_date, datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def homework_for_grade(self, grade: str, due_on_or_after: str | None = None) -> list[sqlite3.Row]:
        due_on_or_after = due_on_or_after or _today_iso()
        return self._conn.execute(
            "SELECT * FROM homework WHERE grade = ? AND due_date >= ? "
            "ORDER BY due_date, subject",
            (grade, due_on_or_after),
        ).fetchall()

    def homework_due_on(self, grade: str, day: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM homework WHERE grade = ? AND due_date = ? ORDER BY subject",
            (grade, day),
        ).fetchall()

    # -------------------------------------------------------------- grades
    def add_grade(
        self, chat_id: int, subject: str, title: str, score: float, max_score: float = 20.0
    ) -> None:
        self._conn.execute(
            "INSERT INTO grades(chat_id, subject, title, score, max_score, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (chat_id, subject, title, score, max_score, datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()

    def grades_of(self, chat_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM grades WHERE chat_id = ? ORDER BY created_at DESC", (chat_id,)
        ).fetchall()

    def average_of(self, chat_id: int) -> float | None:
        row = self._conn.execute(
            "SELECT AVG(score * 20.0 / max_score) AS avg FROM grades WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return None if row["avg"] is None else float(row["avg"])

    # --------------------------------------------------------------- quiz
    def add_quiz_question(
        self, grade: str, subject: str, question: str, options: Iterable[str], correct_index: int
    ) -> int:
        options_list = list(options)
        if not 0 <= correct_index < len(options_list):
            raise ValueError("ایندکس پاسخ درست خارج از محدودهٔ گزینه‌هاست")
        cur = self._conn.execute(
            "INSERT INTO quiz_questions"
            "(grade, subject, question, options, correct_index, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (
                grade,
                subject,
                question,
                json.dumps(options_list, ensure_ascii=False),
                correct_index,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def get_question(self, question_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM quiz_questions WHERE id = ?", (question_id,)
        ).fetchone()

    def random_question(self, grade: str, subject: str | None = None) -> sqlite3.Row | None:
        if subject:
            sql = (
                "SELECT * FROM quiz_questions WHERE grade = ? AND subject = ? "
                "ORDER BY RANDOM() LIMIT 1"
            )
            params: tuple[Any, ...] = (grade, subject)
        else:
            sql = "SELECT * FROM quiz_questions WHERE grade = ? ORDER BY RANDOM() LIMIT 1"
            params = (grade,)
        return self._conn.execute(sql, params).fetchone()

    def count_questions(self, grade: str) -> int:
        return int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM quiz_questions WHERE grade = ?", (grade,)
            ).fetchone()["c"]
        )

    def record_attempt(self, chat_id: int, question_id: int, is_correct: bool) -> None:
        self._conn.execute(
            "INSERT INTO quiz_attempts(chat_id, question_id, is_correct, answered_at) "
            "VALUES(?, ?, ?, ?)",
            (chat_id, question_id, int(is_correct), datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()

    def quiz_stats(self, chat_id: int) -> tuple[int, int]:
        """(تعداد کل پاسخ‌ها, تعداد پاسخ‌های درست)"""
        row = self._conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_correct), 0) AS correct "
            "FROM quiz_attempts WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return int(row["total"]), int(row["correct"])
